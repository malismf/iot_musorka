-- Датчика крышки (геркона) в устройстве больше нет: убираем счётчики открытий.
-- События lid_left_open, если они успели накопиться, остаются в истории как есть.

ALTER TABLE telemetry DROP COLUMN IF EXISTS lid_opens;
ALTER TABLE devices DROP COLUMN IF EXISTS lid_opens_total;
