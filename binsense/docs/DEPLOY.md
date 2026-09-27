# Развёртывание сервера BinSense

Полная инструкция: от пустого сервера до работающей системы с картой,
Grafana и готовыми к выдаче устройствами.

Весь сервер поднимается одной командой `docker compose up -d --build`. Ниже
подробно расписано, что нужно сделать до и после неё.

---

## 1. Что разворачивается

| Сервис | Образ | Порт | Назначение |
|---|---|---|---|
| `web` | Caddy + собранный фронтенд | 80, 443 | веб-приложение, HTTPS, прокси к API и Grafana |
| `api` | `binsense/backend` | внутренний 8000 | REST API и WebSocket |
| `ingestor` | `binsense/backend` | — | приём MQTT, запись в БД, правила событий |
| `mqtt` | `eclipse-mosquitto:2` | 1883 | обмен с устройствами |
| `db` | `postgres:16-alpine` | внутренний 5432 | данные |
| `grafana` | `grafana/grafana` | `/grafana/` | технический мониторинг |
| `emulator` | `binsense/backend` (профиль `demo`) | — | виртуальные контейнеры для демо |

```
устройства ──MQTT 1883──► mosquitto ──► ingestor ──► PostgreSQL
                                                         ▲
                          браузер ──HTTPS──► caddy ──► api ┘
                                             │        └─► WebSocket
                                             └─────────► grafana (чтение)
```

---

## 2. Что нужно

- Сервер с Ubuntu 22.04/24.04 (подойдёт VPS 2 vCPU / 2 ГБ RAM / 20 ГБ диска)
  или любая машина с Docker. Для учебного проекта хватает самого дешёвого VPS.
- Домен, A-запись которого указывает на IP сервера (нужен для HTTPS и
  геолокации в браузере).
- Открытые порты: **80** и **443** (веб), **1883** (устройства).
- На рабочем ноутбуке: Python 3.10+ и PlatformIO — для подготовки устройств.

> Без домена система тоже работает: см. раздел 10 «Локальный запуск» и
> [LOCAL_TEST.md](LOCAL_TEST.md) — сервер на ноутбуке и плата по Wi-Fi.

---

## 3. Подготовка сервера

```bash
ssh root@ВАШ_СЕРВЕР

apt update && apt upgrade -y
apt install -y git curl ufw

# Docker + compose plugin
curl -fsSL https://get.docker.com | sh
docker --version && docker compose version

# Брандмауэр
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 1883/tcp        # MQTT для устройств
ufw --force enable
```

Часовой пояс сервера (влияет на отчёты и логи):

```bash
timedatectl set-timezone Europe/Moscow
```

---

## 4. Код и настройки

```bash
mkdir -p /opt && cd /opt
git clone https://github.com/ВАША_КОМАНДА/binsense.git
cd binsense

# .env со случайными паролями: укажите домен и почту администратора
./infra/scripts/init-env.sh bins.example.com admin@bins.example.com
```

Скрипт напечатает пароль администратора — сохраните его. Файл `.env` содержит
все секреты, он не попадает в git (`chmod 600`).

Что стоит проверить в `.env` перед запуском:

| Переменная | Значение |
|---|---|
| `DOMAIN` | домен сайта; Caddy получит по нему сертификат Let's Encrypt |
| `PUBLIC_URL` | `https://<домен>` — попадает в ссылки для привязки |
| `MQTT_PUBLIC_HOST` | адрес брокера, который прошивается в устройства |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | первый администратор, создаётся при старте |
| `MAP_CENTER` | центр карты при первом открытии, `широта,долгота` |
| `DEFAULT_*` | режим работы устройств по умолчанию |

---

## 5. Запуск

```bash
docker compose up -d --build     # первая сборка занимает 3–5 минут
docker compose ps                # все сервисы должны быть running/healthy
```

Проверка:

```bash
curl -sk https://bins.example.com/api/health
# {"status":"ok","db":true,"version":"1.0.0"}

docker compose logs -f api | head -30
docker compose logs mqtt | head -20   # «mosquitto version 2.x running»
```

Откройте `https://bins.example.com` и войдите под `ADMIN_EMAIL` /
`ADMIN_PASSWORD`.

Что ещё доступно:

- `https://bins.example.com/api/docs` — Swagger с описанием всех методов API;
- `https://bins.example.com/grafana/` — Grafana, логин `admin`, пароль из
  `GRAFANA_ADMIN_PASSWORD`; дашборд «BinSense — техническое состояние»
  подключается автоматически.

---

## 6. Первая проверка без железа

Пока устройства не собраны, поднимите эмулятор — он регистрируется на сервере
теми же запросами, что и настоящее устройство, и публикует телеметрию в MQTT:

```bash
docker compose --profile demo up -d emulator
docker compose logs -f emulator
```

На карте появятся 12 контейнеров, часть начнёт заполняться, один уйдёт в
офлайн. Остановить: `docker compose stop emulator`.

---

## 7. Подготовка устройств

Делается один раз для каждого устройства, с ноутбука, к которому подключена
плата. Скрипт заливает прошивку, читает идентификатор, регистрирует устройство
на сервере, записывает в него учётные данные и выводит код привязки вместе
со ссылкой, по которой устройство добавляют в приложении.

```bash
cd binsense
python3 -m venv .venv && source .venv/bin/activate
pip install pyserial httpx platformio

python tools/provision.py \
    --api https://bins.example.com \
    --email admin@bins.example.com \
    --port /dev/ttyUSB0 \
    --flash --env esp8266          # с HC-SR04: --env esp8266_hcsr04
```

Результат:

```
== Вход на https://bins.example.com выполнен
== Устройство: bin-a1b2c3 (fw 2.0.0, esp8266-a02yyuw)
== Зарегистрировано на сервере: bin-a1b2c3
   код привязки: 7F3K9Q2M
== Записываю настройки в устройство…
== Устройство настроено
== Ссылка для привязки: https://bins.example.com/claim?id=bin-a1b2c3&code=7F3K9Q2M
```

Код показывается один раз: передайте монтажнику ссылку или идентификатор с
кодом. Новый код выдаёт `--reset-code`.

Дальше устройство отдают монтажнику — он действует по `docs/USER_GUIDE.md`.

Если платы ещё нет, а учётные данные нужны (например, для ручного теста):

```bash
python tools/provision.py --device-id bin-test01 --api https://bins.example.com \
    --email admin@bins.example.com
```

---

## 8. Обновление и обслуживание

```bash
cd /opt/binsense
git pull
docker compose up -d --build        # миграции базы применяются автоматически
docker compose ps
```

Логи:

```bash
docker compose logs -f ingestor     # приём данных от устройств
docker compose logs -f api
docker compose logs --since 1h mqtt
```

Резервные копии (база + учётные записи брокера + `.env`):

```bash
./infra/scripts/backup.sh
crontab -e
# 0 3 * * * cd /opt/binsense && ./infra/scripts/backup.sh >> /var/log/binsense-backup.log 2>&1
```

Восстановление: `./infra/scripts/restore.sh backups/db-ГГГГММДД-ЧЧММ.sql.gz`.

Полезные команды:

```bash
# список учётных записей устройств в брокере
docker compose exec mqtt mosquitto_ctrl -u "$MQTT_ADMIN_USER" -P "$MQTT_ADMIN_PASSWORD" \
    dynsec listClients

# посмотреть живой поток телеметрии
docker compose exec mqtt mosquitto_sub -u "$MQTT_ADMIN_USER" -P "$MQTT_ADMIN_PASSWORD" \
    -t 'bins/#' -v

# запрос к базе
docker compose exec db psql -U binsense -d binsense -c \
    "select id, name, last_fill, online, last_seen from devices order by last_seen desc"
```

---

## 9. Безопасность

Что уже сделано:

- у каждого устройства своя учётная запись MQTT и роль, разрешающая писать
  только в свои топики — чужую телеметрию подделать нельзя;
- пароли пользователей хранятся как scrypt-хеши, коды привязки — как HMAC;
- код привязки блокируется после 10 неудачных попыток на 15 минут;
- Grafana ходит в базу под ролью `grafana_ro` без доступа к паролям и токенам;
- HTTPS с автоматическим сертификатом Let's Encrypt.

Что стоит сделать дополнительно:

1. **Закрыть регистрацию** после того, как все сотрудники завели аккаунты:
   `ALLOW_REGISTRATION=false` в `.env` и `docker compose up -d api`.
2. **Включить TLS для MQTT** (порт 8883), если устройства выходят в интернет
   через недоверенные сети:

   ```bash
   # сертификат, который уже получил Caddy, копируем брокеру
   mkdir -p infra/mosquitto/certs
   docker compose exec web cat \
     /data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$DOMAIN/$DOMAIN.crt \
     > infra/mosquitto/certs/fullchain.pem
   docker compose exec web cat \
     /data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$DOMAIN/$DOMAIN.key \
     > infra/mosquitto/certs/privkey.pem
   ```

   раскомментировать блок `listener 8883` в `infra/mosquitto/mosquitto.conf`,
   добавить `- "8883:8883"` в `docker-compose.yml`, прописать
   `MQTT_PUBLIC_PORT=8883` и пересобрать прошивку с флагом `-DMQTT_TLS`
   (см. `docs/FIRMWARE.md`). Сертификат обновляется раз в три месяца —
   повторите копирование по расписанию.
3. Ограничить доступ к `/grafana/` по IP, если сервер публичный.
4. Настроить `fail2ban` для SSH и включить вход только по ключу.

---

## 10. Локальный запуск (без домена)

Пошаговая проверка с настоящей платой — сервер на ноутбуке, плата по
Wi-Fi, включая брандмауэр Windows и хот-спот, — в
[LOCAL_TEST.md](LOCAL_TEST.md).

**На ноутбуке для разработки:**

```bash
# третий аргумент — IP ноутбука в сети, куда подключается плата
./infra/scripts/init-env.sh localhost admin@binsense.local 192.168.137.1
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Открывается `https://localhost` (самоподписанный сертификат — браузер
предупредит), API доступен на `http://localhost:8000`, Grafana на
`http://localhost:3000`, база на `localhost:5432`.

Фронтенд удобно запускать отдельно, с горячей перезагрузкой:

```bash
cd frontend && npm install && npm run dev      # http://localhost:5173
```

**Демонстрация в аудитории без интернета:** поставьте сервер на ноутбук,
раздайте Wi-Fi с телефона и пропишите в `.env`:

```env
DOMAIN=:80
PUBLIC_URL=http://192.168.43.10
MQTT_PUBLIC_HOST=192.168.43.10
```

где `192.168.43.10` — адрес ноутбука в этой сети. Устройства нужно
перепрошить настройками (`tools/provision.py --mqtt-host 192.168.43.10`).
Так сайт открывается и с телефона по `http://192.168.43.10`, но геолокация
браузера по http не работает — место на карте отмечается вручную.

---

## 11. Если что-то не работает

| Симптом | Вероятная причина | Что делать |
|---|---|---|
| `docker compose up` падает на `db` | не задан `POSTGRES_PASSWORD` | проверьте `.env`, запустите `init-env.sh` |
| Сайт не открывается, в логах Caddy ошибки ACME | DNS не указывает на сервер или закрыт 80-й порт | `dig +short ВАШ_ДОМЕН`, `ufw status` |
| `/api/health` отвечает 503 | база не поднялась | `docker compose logs db`, проверьте место на диске |
| Устройство не подключается к брокеру | неверные учётные данные или адрес | `docker compose logs mqtt`, в консоли устройства `info`, при необходимости повторите `provision.py` |
| Телеметрия приходит, но на карте пусто | у устройства не заданы координаты | привяжите устройство заново или укажите место в карточке |
| Заполненность всегда 0 % или «нет калибровки» | устройство не откалибровано | кнопка 3 секунды на пустом контейнере или поле «Глубина» в карточке |
| Grafana показывает «no data» | нет данных за выбранный период или не создана роль `grafana_ro` | смените период; `docker compose exec db psql -U binsense -c "\du"` |
| Панель Grafana с ошибкой доступа | база создавалась до появления скрипта ролей | выполните SQL из `infra/db/init/01-grafana-role.sh` вручную |
| Устройство часто в офлайне | слабый Wi-Fi у контейнера | проверьте RSSI в Grafana, перенесите точку доступа или устройство |

Диагностика «изнутри»:

```bash
docker compose exec api python -c "import asyncio, app.db as db; \
    print(asyncio.run(db.create_pool()) is not None)"
docker compose exec ingestor env | grep MQTT
```

---

## 12. Чек-лист сдачи

- [ ] `https://домен` открывается, вход работает;
- [ ] `/api/docs` показывает документацию API;
- [ ] `/grafana/` открывается, на дашборде есть данные;
- [ ] эмулятор рисует контейнеры на карте;
- [ ] реальное устройство прошито, привязано, шлёт телеметрию;
- [ ] событие о заполнении всплывает в приложении и появляется в ленте событий;
- [ ] `./infra/scripts/backup.sh` отрабатывает и кладёт файлы в `backups/`;
- [ ] пароли из `.env` сохранены в надёжном месте, `.env` не в git.
