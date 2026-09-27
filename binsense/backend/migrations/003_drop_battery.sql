-- Аккумулятора в устройстве больше нет: оно питается от USB и работает
-- постоянно. Убираем напряжение батареи из телеметрии, карточки и метрик.
-- События low_battery / battery_ok, если успели накопиться, остаются в истории.

ALTER TABLE telemetry DROP COLUMN IF EXISTS bat_v;
ALTER TABLE devices DROP COLUMN IF EXISTS last_bat_v;
ALTER TABLE device_metrics DROP COLUMN IF EXISTS bat_v;
