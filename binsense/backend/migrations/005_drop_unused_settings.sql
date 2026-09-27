-- Устройство питается от USB: ночной режим (и нужный только ему часовой пояс)
-- не нужен. Объём контейнера ни на что не влиял — заполненность считается по
-- глубине из калибровки. Прогноз убран вместе с API.

ALTER TABLE devices DROP COLUMN IF EXISTS volume_l;

UPDATE device_config
   SET config = config - 'night_interval_s' - 'night_start' - 'night_end' - 'tz'
 WHERE config ?| ARRAY['night_interval_s', 'night_start', 'night_end', 'tz'];
