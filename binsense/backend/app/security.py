"""Пароли, JWT и коды привязки устройств."""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import secrets
import string

import jwt

from .config import settings

# Алфавит кода привязки без похожих символов (0/O, 1/I) — код вводят вручную
CLAIM_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CLAIM_LENGTH = 8

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


# --- Пароли пользователей ----------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(base64.b64decode(hash_b64)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, base64.b64decode(hash_b64))


# --- JWT ---------------------------------------------------------------------
def create_token(user_id: int) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(hours=settings.jwt_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


# --- Устройства --------------------------------------------------------------
def generate_claim_code(length: int = CLAIM_LENGTH) -> str:
    return "".join(secrets.choice(CLAIM_ALPHABET) for _ in range(length))


def hash_claim_code(device_id: str, code: str) -> str:
    """Код привязки хранится только в виде HMAC — как и пароль."""
    msg = f"{device_id}:{code.strip().upper()}".encode()
    return hmac.new(settings.jwt_secret.encode(), msg, hashlib.sha256).hexdigest()


def verify_claim_code(device_id: str, code: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_claim_code(device_id, code), stored_hash)


def generate_mqtt_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

