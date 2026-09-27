"""Конфигурация всех сервисов BinSense (читается из переменных окружения / .env)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Общее ---------------------------------------------------------------
    public_url: str = "http://localhost"          # адрес веб-приложения (ссылки привязки, Telegram)
    log_level: str = "INFO"

    # --- База данных ---------------------------------------------------------
    database_url: str = "postgresql://binsense:binsense@db:5432/binsense"
    db_pool_min: int = 1
    db_pool_max: int = 10

    # --- Авторизация ---------------------------------------------------------
    jwt_secret: str = "dev-secret-change-me"
    jwt_ttl_hours: int = 168                      # 7 дней
    admin_email: str = ""                         # создаётся при старте, если задан
    admin_password: str = ""
    default_role: str = "dispatcher"              # роль при самостоятельной регистрации
    allow_registration: bool = True

    # --- MQTT ----------------------------------------------------------------
    mqtt_host: str = "mqtt"                       # имя брокера внутри docker-сети
    mqtt_port: int = 1883
    mqtt_admin_user: str = "binsense-admin"       # учётка dynamic-security
    mqtt_admin_password: str = "change-me"
    mqtt_public_host: str = ""                    # адрес брокера для устройств (внешний)
    mqtt_public_port: int = 1883
    mqtt_topic_prefix: str = "bins"

    # --- Telegram ------------------------------------------------------------
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_api_base: str = "https://api.telegram.org"

    # --- Карта ---------------------------------------------------------------
    map_center: str = "55.7558,37.6173"
    map_zoom: int = 12

    # --- Настройки устройств по умолчанию ------------------------------------
    default_interval_s: int = 900                 # обычный интервал сна, 15 мин
    default_heartbeat_s: int = 7200               # обязательная отправка раз в 2 часа
    default_full_interval_s: int = 300            # интервал, когда контейнер заполнен
    default_night_interval_s: int = 1800
    default_night_start: int = 23
    default_night_end: int = 7
    default_full_pct: int = 80
    default_delta_pct: int = 3                    # порог изменения для отправки
    default_samples: int = 7
    default_tz: str = "MSK-3"                     # POSIX TZ для устройства
    default_full_mm: int = 250                    # мёртвая зона датчика + запас

    # --- Правила уведомлений -------------------------------------------------
    offline_factor: float = 1.5                   # нет связи дольше heartbeat * factor
    urgent_fill: int = 95
    urgent_delay_min: int = 120                   # если уведомление не подтверждено N минут
    collected_low_pct: int = 15                   # вывоз: было >= high, стало <= low
    collected_high_pct: int = 50

    # --- Хранение ------------------------------------------------------------
    telemetry_retention_days: int = 365
    metrics_retention_days: int = 30
    api_metrics: bool = True

    @property
    def device_mqtt_host(self) -> str:
        return self.mqtt_public_host or self.mqtt_host

    @property
    def map_center_tuple(self) -> tuple[float, float]:
        try:
            lat, lon = self.map_center.split(",")
            return float(lat), float(lon)
        except ValueError:
            return 55.7558, 37.6173


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
