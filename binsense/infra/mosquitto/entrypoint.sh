#!/bin/sh
# Точка входа контейнера с брокером.
# При первом запуске создаёт файл dynamic-security с учётной записью
# администратора — от её имени сервер BinSense заводит устройства.
set -e

CONFIG=/mosquitto/data/dynamic-security.json
ADMIN_USER="${MQTT_ADMIN_USER:-binsense-admin}"
ADMIN_PASSWORD="${MQTT_ADMIN_PASSWORD}"

if [ -z "$ADMIN_PASSWORD" ]; then
    echo "MQTT_ADMIN_PASSWORD не задан — брокер не будет запущен" >&2
    exit 1
fi

if [ ! -f "$CONFIG" ]; then
    echo "создаю $CONFIG с администратором $ADMIN_USER"
    mosquitto_ctrl dynsec init "$CONFIG" "$ADMIN_USER" "$ADMIN_PASSWORD"
fi

# Брокер работает под пользователем mosquitto и должен иметь доступ к данным
chown -R mosquitto:mosquitto /mosquitto/data 2>/dev/null || true
chmod 600 "$CONFIG" 2>/dev/null || true

exec /usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf
