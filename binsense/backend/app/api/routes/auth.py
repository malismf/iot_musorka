"""Регистрация, вход, профиль, привязка Telegram."""
from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from ...config import settings
from ...devices import log_action
from ...schemas import (
    LoginIn,
    MeUpdateIn,
    RegisterIn,
    TelegramLinkOut,
    TokenOut,
    UserOut,
)
from ...security import create_token, generate_link_token, hash_password, verify_password
from ..deps import PoolDep, UserDep, client_ip

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(prefix="/me", tags=["me"])


def user_out(row) -> UserOut:
    return UserOut(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        role=row["role"],
        telegram_linked=row["telegram_chat_id"] is not None,
        notify_enabled=row["notify_enabled"],
        notify_info=row["notify_info"],
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
    )


async def _issue_token(pool, row, request: Request) -> TokenOut:
    await pool.execute("UPDATE users SET last_login_at = now() WHERE id = $1", row["id"])
    await log_action(pool, row["id"], "login", ip=client_ip(request))
    return TokenOut(access_token=create_token(row["id"], row["role"]), user=user_out(row))


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, pool: PoolDep, request: Request) -> TokenOut:
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Регистрация закрыта администратором")
    exists = await pool.fetchval("SELECT 1 FROM users WHERE lower(email) = lower($1)", body.email)
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с такой почтой уже есть")
    # первый пользователь системы становится администратором
    first = await pool.fetchval("SELECT count(*) = 0 FROM users")
    role = "admin" if first else settings.default_role
    row = await pool.fetchrow(
        """
        INSERT INTO users(email, password_hash, name, role)
        VALUES (lower($1), $2, $3, $4)
        RETURNING *
        """,
        body.email,
        hash_password(body.password),
        body.name or body.email.split("@")[0],
        role,
    )
    await log_action(pool, row["id"], "register", details={"role": role}, ip=client_ip(request))
    return await _issue_token(pool, row, request)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, pool: PoolDep, request: Request) -> TokenOut:
    row = await pool.fetchrow("SELECT * FROM users WHERE lower(email) = lower($1)", body.email)
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверная почта или пароль")
    return await _issue_token(pool, row, request)


@router.post("/token", response_model=TokenOut, include_in_schema=True)
async def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    pool: PoolDep,
    request: Request,
) -> TokenOut:
    """Тот же вход, но формой — чтобы работала кнопка Authorize в Swagger."""
    row = await pool.fetchrow("SELECT * FROM users WHERE lower(email) = lower($1)", form.username)
    if row is None or not verify_password(form.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверная почта или пароль")
    return await _issue_token(pool, row, request)


@me_router.get("", response_model=UserOut)
async def me(user: UserDep) -> UserOut:
    return user_out(user)


@me_router.patch("", response_model=UserOut)
async def update_me(body: MeUpdateIn, user: UserDep, pool: PoolDep) -> UserOut:
    row = await pool.fetchrow(
        """
        UPDATE users
           SET name = COALESCE($2, name),
               password_hash = COALESCE($3, password_hash),
               notify_enabled = COALESCE($4, notify_enabled),
               notify_info = COALESCE($5, notify_info)
         WHERE id = $1
        RETURNING *
        """,
        user["id"],
        body.name,
        hash_password(body.password) if body.password else None,
        body.notify_enabled,
        body.notify_info,
    )
    return user_out(row)


@me_router.post("/telegram-link", response_model=TelegramLinkOut)
async def telegram_link(user: UserDep, pool: PoolDep) -> TelegramLinkOut:
    """Выдаёт одноразовый токен: пользователь открывает t.me/<bot>?start=<token>."""
    token = generate_link_token()
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30)
    await pool.execute(
        "INSERT INTO telegram_links(token, user_id, expires_at) VALUES ($1, $2, $3)",
        token,
        user["id"],
        expires,
    )
    bot = settings.telegram_bot_username.lstrip("@")
    url = f"https://t.me/{bot}?start={token}" if bot else ""
    return TelegramLinkOut(token=token, url=url, expires_at=expires)


@me_router.delete("/telegram", status_code=status.HTTP_204_NO_CONTENT)
async def telegram_unlink(user: UserDep, pool: PoolDep) -> None:
    await pool.execute("UPDATE users SET telegram_chat_id = NULL WHERE id = $1", user["id"])
    await log_action(pool, user["id"], "telegram_unlink")
