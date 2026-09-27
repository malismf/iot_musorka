-- BinSense: начальная схема базы данных.
-- Применяется автоматически при старте сервисов (app/migrate.py).

CREATE TABLE IF NOT EXISTS users (
    id               SERIAL PRIMARY KEY,
    email            TEXT NOT NULL UNIQUE,
    password_hash    TEXT NOT NULL,
    name             TEXT NOT NULL DEFAULT '',
    role             TEXT NOT NULL DEFAULT 'dispatcher'
                     CHECK (role IN ('admin', 'dispatcher', 'driver')),
    telegram_chat_id BIGINT UNIQUE,
    notify_info      BOOLEAN NOT NULL DEFAULT FALSE,  -- присылать ли события уровня info
    notify_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at    TIMESTAMPTZ
);

-- Одноразовые токены для привязки Telegram-аккаунта (/start <token>)
CREATE TABLE IF NOT EXISTS telegram_links (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS devices (
    id                    TEXT PRIMARY KEY,                -- bin-A1B2C3
    claim_code_hash       TEXT NOT NULL,                   -- HMAC кода привязки
    claim_attempts        INTEGER NOT NULL DEFAULT 0,
    claim_locked_until    TIMESTAMPTZ,
    owner_id              INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status                TEXT NOT NULL DEFAULT 'unclaimed'
                          CHECK (status IN ('unclaimed', 'active')),
    online                BOOLEAN NOT NULL DEFAULT FALSE,
    name                  TEXT,
    address               TEXT,
    lat                   DOUBLE PRECISION,
    lon                   DOUBLE PRECISION,
    volume_l              INTEGER,
    empty_mm              INTEGER,                         -- расстояние до дна пустого контейнера
    full_mm               INTEGER,                         -- расстояние, считающееся 100 %
    fw                    TEXT,
    hw                    TEXT,
    last_seen             TIMESTAMPTZ,
    last_ts               TIMESTAMPTZ,
    last_fill             SMALLINT,
    last_dist_mm          INTEGER,
    last_bat_v            REAL,
    last_rssi             SMALLINT,
    lid_opens_total       INTEGER NOT NULL DEFAULT 0,
    state                 JSONB NOT NULL DEFAULT '{}'::jsonb,  -- состояние правил уведомлений
    provisioned_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at            TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS devices_owner_idx ON devices(owner_id);
CREATE INDEX IF NOT EXISTS devices_status_idx ON devices(status);

CREATE TABLE IF NOT EXISTS device_config (
    device_id       TEXT PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL DEFAULT 1,
    config          JSONB NOT NULL DEFAULT '{}'::jsonb,
    applied_version INTEGER,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS telemetry (
    id           BIGSERIAL PRIMARY KEY,
    device_id    TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    ts           TIMESTAMPTZ NOT NULL,                       -- время измерения (часы устройства)
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    seq          BIGINT,
    boot_id      BIGINT,
    fill         SMALLINT,
    dist_mm      INTEGER,
    bat_v        REAL,
    rssi         SMALLINT,
    lid_opens    INTEGER NOT NULL DEFAULT 0,
    wake         TEXT
);

CREATE INDEX IF NOT EXISTS telemetry_device_ts_idx ON telemetry(device_id, ts DESC);
CREATE INDEX IF NOT EXISTS telemetry_received_idx ON telemetry(received_at DESC);
-- защита от дублей при QoS 1 (брокер может доставить сообщение повторно)
CREATE UNIQUE INDEX IF NOT EXISTS telemetry_dedupe_idx
    ON telemetry(device_id, boot_id, seq)
    WHERE seq IS NOT NULL AND boot_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS events (
    id          BIGSERIAL PRIMARY KEY,
    device_id   TEXT REFERENCES devices(id) ON DELETE CASCADE,
    type        TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'info'
                CHECK (severity IN ('info', 'warning', 'critical')),
    message     TEXT NOT NULL DEFAULT '',
    data        JSONB NOT NULL DEFAULT '{}'::jsonb,
    needs_ack   BOOLEAN NOT NULL DEFAULT FALSE,
    acked_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    acked_at    TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS events_device_idx ON events(device_id, created_at DESC);
CREATE INDEX IF NOT EXISTS events_created_idx ON events(created_at DESC);
CREATE INDEX IF NOT EXISTS events_open_idx ON events(created_at DESC) WHERE acked_at IS NULL;

CREATE TABLE IF NOT EXISTS notifications (
    id            BIGSERIAL PRIMARY KEY,
    event_id      BIGINT REFERENCES events(id) ON DELETE CASCADE,
    user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,
    channel       TEXT NOT NULL DEFAULT 'telegram',
    status        TEXT NOT NULL CHECK (status IN ('sent', 'failed', 'skipped')),
    error         TEXT,
    tg_message_id BIGINT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS notifications_event_idx ON notifications(event_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action     TEXT NOT NULL,
    device_id  TEXT,
    details    JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip         TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_created_idx ON audit_log(created_at DESC);

-- Технические метрики устройств (для Grafana, п. 12 задания)
CREATE TABLE IF NOT EXISTS device_metrics (
    id           BIGSERIAL PRIMARY KEY,
    device_id    TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    seq          BIGINT,
    boot_id      BIGINT,
    latency_ms   INTEGER,   -- received_at - ts, задержка доставки
    wake_ms      INTEGER,   -- сколько устройство бодрствовало
    wifi_ms      INTEGER,   -- время подключения к Wi-Fi
    mqtt_ms      INTEGER,   -- время подключения к брокеру
    rssi         SMALLINT,
    bat_v        REAL,
    lost         INTEGER NOT NULL DEFAULT 0,  -- потеряно сообщений по разрыву seq
    wake         TEXT,
    reset_reason TEXT
);

CREATE INDEX IF NOT EXISTS device_metrics_ts_idx ON device_metrics(ts DESC);
CREATE INDEX IF NOT EXISTS device_metrics_device_idx ON device_metrics(device_id, ts DESC);

-- Метрики HTTP API (время ответа, коды) — тоже для Grafana
CREATE TABLE IF NOT EXISTS api_requests (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    method      TEXT NOT NULL,
    path        TEXT NOT NULL,
    status      INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    user_id     INTEGER
);

CREATE INDEX IF NOT EXISTS api_requests_ts_idx ON api_requests(ts DESC);

-- Read-only роль для Grafana не должна видеть пароли и токены
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
        EXECUTE 'REVOKE ALL ON users, telegram_links FROM grafana_ro';
        EXECUTE 'GRANT SELECT (id, email, name, role, telegram_chat_id, created_at, last_login_at) ON users TO grafana_ro';
    END IF;
END
$$;
