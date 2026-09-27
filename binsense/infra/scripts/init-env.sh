#!/usr/bin/env bash
# Создаёт .env со случайными паролями на основе .env.example.
#
#   ./infra/scripts/init-env.sh [домен] [почта-администратора] [адрес-брокера-для-устройств]
#
# Для локального стенда (домен localhost) адрес брокера — это IP ноутбука в той
# сети Wi-Fi, куда подключается плата. Если его не указать, скрипт возьмёт адрес
# основного сетевого интерфейса. Работает в Linux, macOS и Git Bash на Windows.
#
# Повторный запуск не перезаписывает существующий .env.
set -euo pipefail

cd "$(dirname "$0")/../.."

DOMAIN="${1:-localhost}"
ADMIN_EMAIL="${2:-admin@${DOMAIN}}"
MQTT_HOST="${3:-}"

if [ -f .env ]; then
    echo ".env уже существует — ничего не меняю"
    exit 0
fi

# В Windows обычно есть только python или py, а python3 бывает заглушкой Microsoft Store
PYTHON=""
for candidate in python3 python py; do
    if "$candidate" -c "import sys" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "Нужен Python 3 (python3, python или py)" >&2
    exit 1
fi

secret() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex "${1:-16}"
    else
        "$PYTHON" -c "import secrets,sys; print(secrets.token_hex(int(sys.argv[1])))" "${1:-16}"
    fi
}

# Адрес этой машины в локальной сети. UDP-сокет только выбирает маршрут,
# пакеты никуда не отправляются.
lan_ip() {
    "$PYTHON" - <<'PY'
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    sock.connect(("192.0.2.1", 80))
    print(sock.getsockname()[0])
except OSError:
    print("")
finally:
    sock.close()
PY
}

PUBLIC_URL="https://${DOMAIN}"
if [ -z "$MQTT_HOST" ]; then
    MQTT_HOST="$DOMAIN"
    if [ "$DOMAIN" = "localhost" ]; then
        MQTT_HOST="$(lan_ip)"
        MQTT_HOST="${MQTT_HOST:-localhost}"
    fi
fi

cp .env.example .env
replace() {  # ключ значение
    "$PYTHON" - "$1" "$2" <<'PY'
import pathlib, re, sys
key, value = sys.argv[1], sys.argv[2]
path = pathlib.Path(".env")
text = path.read_text(encoding="utf-8")
text = re.sub(rf"(?m)^{re.escape(key)}=.*$", lambda _: f"{key}={value}", text)
# без newline="\n" Python на Windows запишет CRLF
path.write_text(text, encoding="utf-8", newline="\n")
PY
}

ADMIN_PASSWORD="$(secret 8)"

replace DOMAIN "$DOMAIN"
replace PUBLIC_URL "$PUBLIC_URL"
replace MQTT_PUBLIC_HOST "$MQTT_HOST"
replace POSTGRES_PASSWORD "$(secret 16)"
replace JWT_SECRET "$(secret 32)"
replace MQTT_ADMIN_PASSWORD "$(secret 16)"
replace GRAFANA_ADMIN_PASSWORD "$(secret 8)"
replace GRAFANA_DB_PASSWORD "$(secret 16)"
replace ADMIN_EMAIL "$ADMIN_EMAIL"
replace ADMIN_PASSWORD "$ADMIN_PASSWORD"

chmod 600 .env 2>/dev/null || true
echo "Файл .env создан."
echo "  домен:          $DOMAIN"
echo "  брокер MQTT:    $MQTT_HOST:1883 (этот адрес получат устройства)"
echo "  администратор:  $ADMIN_EMAIL"
echo "  пароль:         $ADMIN_PASSWORD"
echo
if [ "$DOMAIN" = "localhost" ]; then
    echo "Локальный стенд: плата должна видеть брокер по адресу $MQTT_HOST."
    echo "Если плата подключается к мобильному хот-споту Windows, адрес ноутбука"
    echo "там 192.168.137.1 — поправьте MQTT_PUBLIC_HOST в .env. Подробно: docs/LOCAL_TEST.md"
    echo
fi
echo "Пароль администратора Grafana смотрите в .env (GRAFANA_ADMIN_PASSWORD)."
echo "Дальше:  docker compose up -d --build"
