"""Pydantic-схемы: тело запросов/ответов REST API и формат MQTT-сообщений."""
from __future__ import annotations

import datetime as dt
import re
from typing import Annotated, Any, Optional

from pydantic import AfterValidator, BaseModel, Field, field_validator

# Свой валидатор почты: email-validator запрещает внутренние домены вида .local,
# а система часто разворачивается внутри организации.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z0-9-]{2,}$")


def _check_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_RE.match(value):
        raise ValueError("некорректный адрес электронной почты")
    return value


Email = Annotated[str, AfterValidator(_check_email)]


# --- MQTT --------------------------------------------------------------------
class TelemetryIn(BaseModel):
    """Сообщение устройства в топике bins/<id>/telemetry."""

    seq: Optional[int] = None
    boot: Optional[int] = None
    ts: Optional[int] = None            # unix-время измерения по часам устройства
    fill: Optional[int] = None          # заполненность, %; null — устройство не откалибровано
    dist_mm: Optional[int] = None
    rssi: Optional[int] = None
    wake: Optional[str] = None          # timer | button | boot | setup
    wake_ms: Optional[int] = None
    wifi_ms: Optional[int] = None
    mqtt_ms: Optional[int] = None
    fw: Optional[str] = None
    hw: Optional[str] = None
    cfg_ver: Optional[int] = None
    reset: Optional[str] = None

    @field_validator("fill")
    @classmethod
    def clamp_fill(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        return max(0, min(100, int(v)))


class DeviceEventIn(BaseModel):
    """Сообщение устройства в топике bins/<id>/event."""

    type: str
    code: Optional[str] = None
    empty_mm: Optional[int] = None
    full_mm: Optional[int] = None
    fw: Optional[str] = None
    hw: Optional[str] = None
    reset: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    message: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)


# --- Пользователи ------------------------------------------------------------
class RegisterIn(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: Email
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    created_at: Optional[dt.datetime] = None
    last_login_at: Optional[dt.datetime] = None


class MeUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


# --- Устройства --------------------------------------------------------------
class DeviceOut(BaseModel):
    id: str
    name: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    status: str
    online: bool
    fill: Optional[int] = None
    dist_mm: Optional[int] = None
    rssi: Optional[int] = None
    last_seen: Optional[dt.datetime] = None
    last_ts: Optional[dt.datetime] = None
    empty_mm: Optional[int] = None
    full_mm: Optional[int] = None
    calibrated: bool = False
    fw: Optional[str] = None
    hw: Optional[str] = None
    owner_id: Optional[int] = None
    owner_name: Optional[str] = None
    full_pct: int = 80
    config_version: Optional[int] = None
    config_applied_version: Optional[int] = None
    config: dict[str, Any] = Field(default_factory=dict)
    open_events: int = 0
    claimed_at: Optional[dt.datetime] = None
    created_at: Optional[dt.datetime] = None


class ClaimIn(BaseModel):
    device_id: str = Field(min_length=3, max_length=64)
    claim_code: str = Field(min_length=4, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(default="", max_length=250)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)

    @field_validator("device_id")
    @classmethod
    def normalize_id(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("claim_code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        return v.strip().upper().replace("-", "").replace(" ", "")


class DeviceUpdateIn(BaseModel):
    # карточка
    name: Optional[str] = Field(default=None, max_length=120)
    address: Optional[str] = Field(default=None, max_length=250)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    # настройки, уезжающие на устройство
    interval_s: Optional[int] = Field(default=None, ge=10, le=86400)
    heartbeat_s: Optional[int] = Field(default=None, ge=60, le=86400)
    full_interval_s: Optional[int] = Field(default=None, ge=10, le=86400)
    full_pct: Optional[int] = Field(default=None, ge=10, le=100)
    delta_pct: Optional[int] = Field(default=None, ge=0, le=50)
    samples: Optional[int] = Field(default=None, ge=1, le=31)
    empty_mm: Optional[int] = Field(default=None, ge=50, le=10000)
    full_mm: Optional[int] = Field(default=None, ge=0, le=10000)


class ProvisionIn(BaseModel):
    device_id: str = Field(min_length=3, max_length=64)
    hw: Optional[str] = Field(default=None, max_length=64)
    fw: Optional[str] = Field(default=None, max_length=32)
    reset_claim_code: bool = False

    @field_validator("device_id")
    @classmethod
    def normalize_id(cls, v: str) -> str:
        return v.strip().lower()


class ProvisionOut(BaseModel):
    device_id: str
    mqtt_username: str
    mqtt_password: str
    mqtt_host: str
    mqtt_port: int
    claim_code: str
    claim_url: str
    created: bool


# --- Телеметрия, события, статистика ----------------------------------------
class TelemetryPoint(BaseModel):
    ts: dt.datetime
    fill: Optional[float] = None
    fill_max: Optional[float] = None
    dist_mm: Optional[float] = None
    rssi: Optional[float] = None


class EventOut(BaseModel):
    id: int
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    type: str
    severity: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    needs_ack: bool
    acked_at: Optional[dt.datetime] = None
    acked_by_name: Optional[str] = None
    resolved_at: Optional[dt.datetime] = None
    created_at: dt.datetime


class StatsOut(BaseModel):
    devices: int
    active: int
    unclaimed: int
    online: int
    offline: int
    full: int
    uncalibrated: int
    avg_fill: Optional[float] = None
    open_events: int
    collected_7d: int


class RouteStop(BaseModel):
    device_id: str
    name: Optional[str] = None
    address: Optional[str] = None
    lat: float
    lon: float
    fill: Optional[int] = None


class RouteOut(BaseModel):
    stops: list[RouteStop]
    total_km: float
    map_urls: list[str]


class PublicConfigOut(BaseModel):
    map_center: list[float]
    map_zoom: int
    public_url: str
    allow_registration: bool
    version: str


class AuditOut(BaseModel):
    id: int
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    action: str
    device_id: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
    ip: Optional[str] = None
    created_at: dt.datetime


TokenOut.model_rebuild()
