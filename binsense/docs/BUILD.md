# Сборка проекта

Пошаговая сборка всех частей BinSense из текущего кода: сервер (Docker),
фронтенд отдельно для разработки, прошивка ESP8266, тесты. Про полное
развёртывание на сервере с доменом и HTTPS — [DEPLOY.md](DEPLOY.md); про
локальный стенд с настоящей платой по Wi-Fi — [LOCAL_TEST.md](LOCAL_TEST.md).
Здесь — просто «собрать и запустить всё, что есть в репозитории».

## 0. Что нужно

| Часть | Требуется |
|---|---|
| Сервер | Docker + Docker Compose |
| Фронтенд (для разработки без Docker) | Node.js 20+ |
| Прошивка | PlatformIO (CLI или расширение VS Code) |
| Тесты сервера | Python 3.12, живая PostgreSQL |
| Тесты прошивки | g++ (или другой C++17-компилятор) |
| Схемы (опционально) | Python 3, без внешних зависимостей |

Держите проект в пути без кириллицы (например `C:\binsense`) — иначе
PlatformIO на Windows может не собрать прошивку.

## 1. Сервер целиком (Docker)

```bash
git clone <URL_РЕПОЗИТОРИЯ> binsense
cd binsense
./infra/scripts/init-env.sh localhost admin@binsense.local 192.168.137.1
docker compose up -d --build
```

`init-env.sh` создаёт `.env` из `.env.example` и генерирует пароли:
- 1-й аргумент — домен (`localhost` для стенда на одной машине);
- 2-й — почта администратора;
- 3-й — адрес брокера MQTT, который получит устройство (для стенда — IP
  ноутбука в сети, куда подключается плата; при мобильном хот-споте Windows
  это обычно `192.168.137.1`). Повторный запуск скрипта `.env` не
  перезаписывает.

`docker compose up -d --build` поднимает и собирает образы: `db` (PostgreSQL
16), `mqtt` (Mosquitto 2 с dynamic-security и ролью на устройство), `api`
(FastAPI, `backend/Dockerfile`), `ingestor` (тот же образ, `app.ingestor`),
`bot` (тот же образ, `app.bot`), `web` (сборка React + Caddy по
`frontend/Dockerfile`), `grafana`. Миграции из `backend/migrations/`
применяются самим приложением при старте (`app/db.py`), отдельно их
запускать не нужно.

Проверить: `https://localhost` (сертификат самоподписанный — браузер
предупредит), логин — `ADMIN_EMAIL`/`ADMIN_PASSWORD` из `.env`.

Демо-данные без реального устройства:

```bash
docker compose --profile demo up -d emulator   # 12 виртуальных контейнеров
```

## 2. Фронтенд отдельно (разработка)

Сервер — в Docker, фронтенд — с горячей перезагрузкой на хосте:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
cd frontend
npm install
npm run dev        # http://localhost:5173, прокси на :8000
```

Сборка production-бандла отдельно от Docker (например, для проверки перед
коммитом):

```bash
cd frontend
npm install
npm run build       # результат в frontend/dist
npm run preview     # просмотр собранного бандла на :4173
```

## 3. Прошивка ESP8266 (NodeMCU)

Датчик выбирается окружением PlatformIO в `firmware/platformio.ini`:

| Окружение | Датчик |
|---|---|
| `esp8266` (основной) | A02YYUW по UART, влагозащищённый |
| `esp8266_hcsr04` | HC-SR04 (Trig/Echo), для прототипа на столе |
| `esp8266_jsn` | JSN-SR04T v3 в режиме UART |

```bash
cd firmware
pio run -e esp8266              # собрать
pio run -e esp8266 -t upload    # собрать и залить (плата по USB)
pio device monitor            # консоль, 115200 бод
```

Для варианта с HC-SR04: `pio run -e esp8266_hcsr04 -t upload`.

После прошивки — подготовка устройства и привязка его к серверу
(`tools/provision.py` пишет Wi-Fi/MQTT-настройки и выводит код привязки):

```bash
cd ..
python tools/provision.py --api https://localhost --port COM10 --flash
```

Адрес брокера, который получит устройство, берётся из `MQTT_PUBLIC_HOST` в
`.env` либо передаётся флагом `--mqtt-host`.

## 4. Windows без Docker

Если Docker недоступен, весь стек можно поднять через нативные процессы —
подробности и предварительные требования (PostgreSQL, Mosquitto, Python,
Node.js) в [LOCAL_TEST.md, §3б](LOCAL_TEST.md):

```powershell
powershell -ExecutionPolicy Bypass -File infra\windows\setup.ps1   # один раз
powershell -ExecutionPolicy Bypass -File infra\windows\start.ps1
```

Не запускайте `start.ps1` с выводом в конвейер (`| Select-Object` и
т. п.) — сервисы наследуют канал, и команда не завершится. Останов —
`infra\windows\stop.ps1`.

## 5. Тесты

Сервер (нужна отдельная тестовая база, 48 тестов):

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # или source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
TEST_DATABASE_URL=postgresql://binsense:ПАРОЛЬ@localhost:5432/binsense_test \
    python -m pytest
```

Логика прошивки без железа (58 проверок + пробная сборка обоих вариантов
заглушками Arduino/ESP8266):

```bash
cd firmware/hosttest
./run.sh                 # CXX=clang++ и т. п., если не g++
```

## 6. Схемы (опционально)

Принципиальная и монтажная схемы генерируются кодом, без внешних
зависимостей:

```bash
cd hardware/schematic
python make_schematic.py   # результат — SVG в hardware/schematic/
```

## Итоговая проверка «всё собралось»

- `docker compose ps` — все сервисы `healthy`/`running`;
- `https://localhost/api/health` отвечает `200`;
- `cd firmware/hosttest && ./run.sh` — без ошибок;
- `pio run -e esp8266` и `pio run -e esp8266_hcsr04` — оба варианта прошивки
  компилируются;
- `cd backend && python -m pytest` — 48 тестов зелёные;
- `cd frontend && npm run build` — сборка без ошибок.
