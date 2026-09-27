"""Регистрация, вход, профиль."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from ...config import settings
from ...devices import log_action
from ...schemas import (
    LoginIn,
    MeUpdateIn,
    RegisterIn,
    TokenOut,
    UserOut,
)
from ...security import create_token, hash_password, verify_password
from ..deps import PoolDep, UserDep, client_ip

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(prefix="/me", tags=["me"])


def user_out(row) -> UserOut:
    return UserOut(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
    )


async def _issue_token(pool, row, request: Request) -> TokenOut:
    await pool.execute("UPDATE users SET last_login_at = now() WHERE id = $1", row["id"])
    await log_action(pool, row["id"], "login", ip=client_ip(request))
    return TokenOut(access_token=create_token(row["id"]), user=user_out(row))


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, pool: PoolDep, request: Request) -> TokenOut:
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Регистрация закрыта администратором")
    exists = await pool.fetchval("SELECT 1 FROM users WHERE lower(email) = lower($1)", body.email)
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с такой почтой уже есть")
    row = await pool.fetchrow(
        """
        INSERT INTO users(email, password_hash, name)
        VALUES (lower($1), $2, $3)
        RETURNING *
        """,
        body.email,
        hash_password(body.password),
        body.name or body.email.split("@")[0],
    )
    await log_action(pool, row["id"], "register", ip=client_ip(request))
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
               password_hash = COALESCE($3, password_hash)
         WHERE id = $1
        RETURNING *
        """,
        user["id"],
        body.name,
        hash_password(body.password) if body.password else None,
    )
    return user_out(row)

