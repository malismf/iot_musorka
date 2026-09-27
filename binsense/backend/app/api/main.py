"""HTTP API BinSense (FastAPI).

Swagger: /api/docs, схема OpenAPI: /api/openapi.json
"""
from __future__ import annotations

import contextlib
import json
import logging
import time
from typing import AsyncIterator

from fastapi import APIRouter, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..config import settings
from ..db import create_pool, migrate
from ..devices import default_config
from ..mqtt import mqtt_admin
from ..schemas import PublicConfigOut
from ..security import hash_password
from .deps import user_from_token
from .routes import admin, auth, devices, events, stats
from .ws import hub

log = logging.getLogger("binsense.api")

VERSION = "1.0.0"


async def ensure_admin_user(pool) -> None:
    """Создаёт администратора из переменных окружения при первом запуске."""
    if not settings.admin_email or not settings.admin_password:
        return
    exists = await pool.fetchval(
        "SELECT 1 FROM users WHERE lower(email) = lower($1)", settings.admin_email
    )
    if exists:
        return
    await pool.execute(
        """INSERT INTO users(email, password_hash, name, role)
           VALUES (lower($1), $2, 'Администратор', 'admin')""",
        settings.admin_email,
        hash_password(settings.admin_password),
    )
    log.info("создан администратор %s", settings.admin_email)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    if len(settings.jwt_secret) < 32 or settings.jwt_secret.startswith("dev-secret"):
        log.warning(
            "JWT_SECRET слишком короткий или оставлен по умолчанию — "
            "сгенерируйте новый: openssl rand -hex 32"
        )
    app.state.pool = await create_pool()
    await migrate(app.state.pool)
    await ensure_admin_user(app.state.pool)
    try:
        await mqtt_admin.ensure_backend_role()
    except Exception as exc:  # noqa: BLE001 — API должен подниматься и без брокера
        log.warning("брокер недоступен при старте: %s", exc)
    await hub.start(app.state.pool)
    log.info("API запущен, версия %s", VERSION)
    try:
        yield
    finally:
        await hub.stop(app.state.pool)
        await app.state.pool.close()


app = FastAPI(
    title="BinSense API",
    version=VERSION,
    description=(
        "Система мониторинга заполненности мусорных контейнеров.\n\n"
        "Устройства общаются с сервером по MQTT (см. docs/asyncapi.yaml), "
        "приложение — по этому REST API и WebSocket `/api/ws`."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # фронтенд обслуживается тем же доменом через Caddy
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Пишет время ответа в api_requests — источник данных для Grafana."""
    started = time.perf_counter()
    response = await call_next(request)
    if settings.api_metrics and request.url.path.startswith("/api"):
        duration_ms = int((time.perf_counter() - started) * 1000)
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        pool = getattr(request.app.state, "pool", None)
        if pool is not None and path not in ("/api/health", "/api/ws"):
            with contextlib.suppress(Exception):
                await pool.execute(
                    """INSERT INTO api_requests(method, path, status, duration_ms, user_id)
                       VALUES ($1, $2, $3, $4, $5)""",
                    request.method,
                    path,
                    response.status_code,
                    duration_ms,
                    getattr(request.state, "user_id", None),
                )
    return response


api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(auth.me_router)
api.include_router(devices.router)
api.include_router(events.router)
api.include_router(stats.router)
api.include_router(admin.router)


@api.get("/health", tags=["service"])
async def health(request: Request) -> JSONResponse:
    pool = getattr(request.app.state, "pool", None)
    db_ok = False
    if pool is not None:
        with contextlib.suppress(Exception):
            db_ok = await pool.fetchval("SELECT 1") == 1
    return JSONResponse(
        {"status": "ok" if db_ok else "degraded", "db": db_ok, "version": VERSION},
        status_code=200 if db_ok else 503,
    )


@api.get("/config/public", response_model=PublicConfigOut, tags=["service"])
async def public_config() -> PublicConfigOut:
    lat, lon = settings.map_center_tuple
    return PublicConfigOut(
        map_center=[lat, lon],
        map_zoom=settings.map_zoom,
        public_url=settings.public_url,
        allow_registration=settings.allow_registration,
        version=VERSION,
    )


@api.get("/config/device-defaults", tags=["service"])
async def device_defaults() -> dict:
    """Настройки устройства по умолчанию — показываются в форме настроек."""
    return default_config()


app.include_router(api)


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = "") -> None:
    pool = websocket.app.state.pool
    user = await user_from_token(pool, token) if token else None
    if user is None:
        await websocket.close(code=4401)
        return
    await hub.connect(websocket)
    try:
        while True:
            # клиент присылает ping; сообщения нам не нужны, но держим соединение
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket)
