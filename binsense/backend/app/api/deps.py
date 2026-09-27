"""Зависимости FastAPI: пул БД, текущий пользователь, проверка ролей."""
from __future__ import annotations

from typing import Annotated, Optional

import asyncpg
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]


async def user_from_token(pool: asyncpg.Pool, token: str) -> Optional[asyncpg.Record]:
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        return None
    user_id = payload.get("sub")
    if user_id is None:
        return None
    return await pool.fetchrow("SELECT * FROM users WHERE id = $1", int(user_id))


async def current_user(
    request: Request,
    pool: PoolDep,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
) -> asyncpg.Record:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется авторизация")
    user = await user_from_token(pool, credentials.credentials)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Недействительный токен")
    request.state.user_id = user["id"]
    return user


UserDep = Annotated[asyncpg.Record, Depends(current_user)]


def require_roles(*roles: str):
    async def checker(user: UserDep) -> asyncpg.Record:
        if roles and user["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return checker


AdminDep = Annotated[asyncpg.Record, Depends(require_roles("admin"))]
# редактировать устройства могут админ и диспетчер, водитель — только смотреть и подтверждать
EditorDep = Annotated[asyncpg.Record, Depends(require_roles("admin", "dispatcher"))]


def client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
