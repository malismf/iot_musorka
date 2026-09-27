# BinSense — контекст проекта

Система мониторинга заполненности мусорных контейнеров: датчик на ESP8266
(NodeMCU, питание от USB) под крышкой → MQTT → сервер → карта и уведомления
в браузере.
Учебный проект, 3 человека. Документация — в `docs/`, начинать с `README.md`.

## Стек

| Часть | Технологии |
|---|---|
| Прошивка | ESP8266 (NodeMCU / D1 mini), PlatformIO + Arduino, WiFiManager, 256dpi/MQTT (QoS 1) |
| Сервер | Python 3.12, FastAPI, asyncpg, aiomqtt, PostgreSQL 16, Mosquitto 2 |
| Веб | React 18 + Vite, react-leaflet, Chart.js, иконки lucide-react — без смайликов в интерфейсе (JSX, без TypeScript) |
| Инфраструктура | docker compose, Caddy (HTTPS), Grafana |

## Структура

```
firmware/        прошивка; src/measure.cpp и src/json_lite.cpp — чистая логика без Arduino
firmware/hosttest/  тесты логики + пробная сборка с заглушками (g++, без железа)
backend/app/     api/ (FastAPI), ingestor/ (MQTT → БД → правила → события)
backend/app/rules.py      правила событий — чистые функции, покрыты тестами
backend/migrations/       SQL-миграции, применяются при старте (app/db.py)
frontend/src/    pages/ + components/ + lib/ (api.js, store.jsx с WebSocket)
tools/           provision.py (подготовка устройств, код и ссылка привязки), emulator.py
infra/           mosquitto, caddy, grafana (дашборд генерируется make_dashboard.py)
docs/            DEPLOY, LOCAL_TEST, ASSEMBLY, USER_GUIDE, PROTOCOL, asyncapi.yaml, openapi.json
docs/presentation/  тезисы и вопросы к защите (README.md); слайды опубликованы отдельно
hardware/        BOM.csv и WIRING.md (распиновка); схему команда рисует сама
```

## Команды

```bash
# полный стек (третий аргумент — IP ноутбука для платы, см. docs/LOCAL_TEST.md)
./infra/scripts/init-env.sh localhost admin@binsense.local 192.168.137.1
docker compose up -d --build
docker compose --profile demo up -d emulator      # 12 виртуальных контейнеров

# разработка
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
cd frontend && npm install && npm run dev          # :5173, прокси на :8000

# тесты
cd backend && TEST_DATABASE_URL=postgresql://binsense:ПАРОЛЬ@localhost:5432/binsense_test \
    python -m pytest                               # 37 тестов, нужна живая БД
cd firmware/hosttest && ./run.sh                   # 51 проверка + компиляция (CXX=… для не-g++)

# без Docker на Windows (docs/LOCAL_TEST.md §3б): рантайм в %USERPROFILE%\binsense-run
powershell -ExecutionPolicy Bypass -File infra\windows\setup.ps1   # один раз
powershell -ExecutionPolicy Bypass -File infra\windows\start.ps1   # stop.ps1 — остановка

# прошивка и подготовка платы (адрес брокера — MQTT_PUBLIC_HOST или --mqtt-host)
cd firmware && pio run -e esp8266 -t upload && pio device monitor   # HC-SR04: esp8266_hcsr04
python tools/provision.py --api https://localhost --port COM5 --flash
```

## Архитектурные решения (не ломать, не «упрощать»)

- **Плата ESP8266, питание от USB, без аккумулятора и без сна.** `loop()`
  работает постоянно: держит Wi-Fi и MQTT, опрашивает кнопку и консоль, меряет
  по расписанию (`chooseIntervalS`). Батареи нет — миграция `003_drop_battery.sql`
  убрала `bat_v`; не возвращайте замер заряда и события `low_battery`.
  Датчик на программном UART (D5/D6): аппаратный занят консолью. D3/D4/D8 —
  выводы загрузчика, их уровень при включении не менять.
- **Настройки устройству — retained-сообщение** `bins/<id>/config`: устройство
  получает последнюю версию сразу после (пере)подключения, а новые — как только
  их сохранили. Версия `ver` растёт, устройство возвращает её в `cfg_ver`
  телеметрии — так сервер знает, что настройки применены.
- **Last Will не используется.** Статус «нет связи» считает
  `Ingestor.check_offline()` по `last_seen` и `heartbeat_s × OFFLINE_FACTOR` —
  не зависит от брокера и ловит устройство, которое на связи, но молчит.
- **QoS 1 + дедупликация.** Уникальный индекс `telemetry(device_id, boot_id, seq)`;
  `boot` — случайный идентификатор включения, отличает перезагрузку от потери.
  Разрывы `seq` дают метрику потерь для Grafana.
- **Права в MQTT — per-device.** Mosquitto 2.0 **не поддерживает `%u`** в ACL
  dynamic-security (проверено), поэтому на каждое устройство создаётся своя роль
  `dev-<id>`. Повторный `addClientRole` брокер считает ошибкой («Internal error»),
  поэтому `mqtt.py` сначала делает `getClient`.
- **Realtime без Redis:** ingestor делает `pg_notify('binsense_ws', …)`, API
  слушает канал и рассылает по WebSocket (`app/api/ws.py`).
- **Датчика крышки нет** (геркон убран из прошивки, схем и БД —
  миграция `002_drop_lid.sql`). Замер мог попасть на открытую крышку, поэтому скачок уровня ≥ 20 % или сбой
  датчика перемеряется через 60 с перед отправкой (`measure.cpp::needsRecheck`,
  `RECHECK_*` в `config.h`). Не возвращайте `lid_opens`/`lid_left_open`.
- **Telegram-бота нет** (убран вместе с таблицами и полями пользователей —
  миграция `004_drop_telegram.sql`). События видны в веб-приложении: лента,
  всплывающие предупреждения по WebSocket. Не возвращайте
  `bot/`, `notify.py`, `telegram_links` и `notifications`.
- **Привязка — по коду, без наклеек и QR.** `provision.py` выводит код и
  ссылку `PUBLIC_URL/claim?id=…&code=…`, страница привязки заполняется из
  ссылки или вручную. Код показывается один раз, новый — `--reset-code`.
- **Отправка по изменению**, а не каждое измерение (`delta_pct`, `heartbeat_s`) —
  в базе и на графиках только изменения; логика в
  `firmware/src/measure.cpp::shouldSend`.
- **Настройки прошивки во флеше — одна структура с CRC** (`Storage::Data`,
  эмуляция EEPROM). Меняете структуру — увеличьте `STORAGE_VERSION`, но
  тогда перепрошивка сотрёт учётку MQTT и плату придётся заново готовить
  `provision.py`. Поэтому удалённые поля `DeviceConfig` заменены резервом
  (`reserved1`/`reserved2`), раскладку сторожит `static_assert`.
- **В прошивке нет ArduinoJson**: свой `json_lite` — меньше памяти и логика
  тестируется на обычном компьютере.
- **Схему команда рисует сама**, генератора схем в репозитории нет (удалён).
  Источник правды по распиновке — `hardware/WIRING.md` и флаги `-DPIN_*`.
- **Корпус — готовая герметичная коробка**, своих деталей корпуса в проекте
  нет. Пункт 4 задания из-за этого не закрыт — см. `docs/REQUIREMENTS.md`.
- Пароли — `hashlib.scrypt`, коды привязки — HMAC, без внешних библиотек.
- Почта валидируется своим regex: `email-validator` запрещает домены вида `.local`,
  а систему разворачивают внутри организации.

## Инварианты при изменениях

| Меняете | Обновите заодно |
|---|---|
| Поле телеметрии | `firmware/src/main.cpp::buildTelemetry`, `backend/app/schemas.py::TelemetryIn`, таблицы `telemetry`/`device_metrics` (новая миграция), `docs/asyncapi.yaml`, `docs/PROTOCOL.md` |
| Поле настроек устройства | `CONFIG_FIELDS` в `backend/app/devices.py`, `build_config_payload`, `DeviceUpdateIn`, `NetLink::applyConfig` и `Storage` в прошивке, форма в `frontend/src/pages/DevicePage.jsx`, asyncapi |
| Новый тип события | `backend/app/rules.py` (спека), `frontend/src/lib/format.js` (`EVENT_TITLES`, `EVENT_ICONS` — иконка из `lucide-react` и цвет) |
| Формула заполненности | одинаково в `firmware/src/measure.cpp::fillPercent` и в калибровке на сервере — иначе устройство и карточка разойдутся |
| Схема БД | только новым файлом `backend/migrations/00N_*.sql` (применяются по порядку, с advisory-lock) |
| Панель Grafana | правьте `infra/grafana/make_dashboard.py` и перегенерируйте JSON, руками JSON не редактируйте |
| Пины/плата | только флаги `-DPIN_*` в `firmware/platformio.ini`, код не трогать |
| Распиновка | таблица в `hardware/WIRING.md` и схема, которую рисует команда |
| Слайды презентации | правятся в опубликованной презентации (генератора в репозитории нет); тезисы и вопросы — в `docs/presentation/README.md` |

## Соглашения

- Комментарии, сообщения логов, тексты интерфейса и документация — по-русски;
  имена сущностей в коде — по-английски.
- Python: строки ≤ 100 символов, явный SQL через asyncpg (без ORM), pydantic v2.
- React: функциональные компоненты, состояние приложения — в `lib/store.jsx`,
  сетевые вызовы — только через `lib/api.js`.
- Прошивка: бизнес-логика — в `measure.cpp`/`json_lite.cpp` (без Arduino), чтобы
  её покрывали хост-тесты; всё, что трогает железо, — в отдельных модулях.
- Новая функциональность сервера сопровождается тестом в `backend/tests/`.

## Текущее состояние

Работает и проверено на локальном стенде: подготовка устройства → привязка по
коду → retained-настройки → телеметрия → события → вывоз →
история, маршрут, метрики. Прошло 37 тестов сервера,
51 проверка логики прошивки, сборка обоих вариантов прошивки настоящим
тулчейном ESP8266 (PlatformIO), сборка фронтенда. Готовые образы — в
`%USERPROFILE%\binsense-run\fw-release` на машине разработчика.

Схемы (принципиальную и монтажную) команда рисует сама, распиновка — в
`hardware/WIRING.md`. Презентация: 19 слайдов, опубликована отдельно;
тезисы и вопросы — в `docs/presentation/README.md`. Презентация и тезисы ещё
описывают ESP32 с аккумулятором и Telegram-бота — их нужно обновить отдельно.

Не проверялось вживую: сборка docker-образов (в песочнице был закрыт реестр)
и работа на реальной плате ESP8266.

Осталось команде: собрать устройство на реальном железе в готовой герметичной
коробке, пройти стенд по `docs/LOCAL_TEST.md`, снять фотографии и видео по
`docs/MEDIA.md`.

## Известные шероховатости

- Прогноз, объём контейнера, ночной режим и часовой пояс удалены целиком
  (миграция `005_drop_unused_settings.sql`) — не возвращайте. Уровень Wi-Fi
  не показывается в интерфейсе, но приходит в телеметрии и нужен Grafana.
- Подтверждения событий («Принято») и формы «Подготовить устройство» в
  интерфейсе нет. На сервере `POST /events/{id}/ack` остался, а
  `POST /admin/devices` нужен `provision.py`.
- События «Срочно вывезти» (`full_urgent`, уровень `critical`) больше нет —
  миграция `006_drop_urgent.sql`. Фильтр в ленте — «Контейнер заполнен».
- Карта по умолчанию — Иркутск (`MAP_CENTER`, резерв — `DEFAULT_MAP_CENTER`
  в `frontend/src/lib/tiles.js`).
- Плитки OpenStreetMap требуют интернета; для закрытого контура адрес слоя
  меняется в `frontend/src/lib/tiles.js`.
- Геолокация на странице привязки работает только по HTTPS (или на
  localhost); место на карте можно отметить вручную.
- PlatformIO на Windows может не собрать прошивку из пути с кириллицей —
  держите проект в пути латиницей (`C:\binsense`).
- Локальный стенд: ESP8266 видит только сети 2.4 ГГц с паролем (не
  WPA2-Enterprise); на Windows нужно правило брандмауэра для порта 1883.
- `start.ps1` не запускайте с выводом в конвейер (`| Select-Object` и т. п.):
  сервисы наследуют канал, и команда не завершится.
- Телеметрия хранится сырой; при большом числе устройств стоит включить
  TimescaleDB или агрегировать историю.
