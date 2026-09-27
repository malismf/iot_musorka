// BinSense — датчик заполненности мусорного контейнера.
//
// Плата ESP8266 питается от USB и работает постоянно: держит связь с
// брокером, меряет уровень по расписанию и отправляет данные, когда он заметно
// изменился или подошёл срок heartbeat. Настройки приходят retained-сообщением
// и применяются сразу, без перезагрузки.
#include <Arduino.h>
#include <time.h>

#include "board.h"
#include "config.h"
#include "console.h"
#include "indicator.h"
#include "json_lite.h"
#include "measure.h"
#include "netlink.h"
#include "sensor.h"
#include "storage.h"

#define EVENT_QUEUE_SIZE 3
#define EVENT_PAYLOAD_SIZE 200

static DeviceConfig cfg;
static Credentials creds;
static char wifiSsid[33] = {0};
static char wifiPass[65] = {0};

static uint32_t seq = 0;
static uint32_t bootId = 0;          // случайное число на каждое включение
static int lastSentFill = -1;
static bool sentOnce = false;        // было ли сообщение после включения
static uint32_t lastSentMs = 0;
static uint32_t nextMeasureMs = 0;   // время следующего замера по millis()
static bool recheckPending = false;  // следующий замер — повторный, после скачка
static bool interactive = false;     // замер запросил человек — показываем индикацию
static const char *wakeReason = "boot";
static bool wasOnline = false;
static bool claimBlinking = false;

static char eventQueue[EVENT_QUEUE_SIZE][EVENT_PAYLOAD_SIZE];
static uint8_t eventCount = 0;

// --- вспомогательное ---------------------------------------------------------
static void queueEvent(const char *payload) {
  if (eventCount >= EVENT_QUEUE_SIZE) return;
  strncpy(eventQueue[eventCount], payload, EVENT_PAYLOAD_SIZE - 1);
  eventQueue[eventCount][EVENT_PAYLOAD_SIZE - 1] = '\0';
  eventCount++;
}

static void queueSimpleEvent(const char *type, const char *key = nullptr,
                             const char *value = nullptr) {
  char buffer[EVENT_PAYLOAD_SIZE];
  json::Writer writer(buffer, sizeof(buffer));
  writer.begin();
  writer.addString("type", type);
  if (key && value) writer.addString(key, value);
  writer.end();
  queueEvent(buffer);
}

static int localHour() {
  time_t now = time(nullptr);
  if (now < 1700000000) return -1;
  struct tm info;
  localtime_r(&now, &info);
  return info.tm_hour;
}

static uint32_t secondsSinceSend() {
  if (!sentOnce) return 0xFFFFFFFFu;
  return (millis() - lastSentMs) / 1000;
}

// Сравнение через разность: переживает переполнение millis() раз в 49 суток
static bool timeReached(uint32_t at) { return (int32_t)(millis() - at) >= 0; }

static void scheduleMeasure(uint32_t seconds) { nextMeasureMs = millis() + seconds * 1000UL; }

static void buildTelemetry(char *buffer, size_t size, const Measurement &measurement) {
  json::Writer writer(buffer, size);
  writer.begin();
  writer.addUInt("seq", seq);
  writer.addUInt("boot", bootId);
  time_t now = time(nullptr);
  if (now > 1700000000) writer.addUInt("ts", (unsigned long)now);
  if (measurement.fill >= 0) writer.addInt("fill", measurement.fill);
  if (measurement.dist_mm > 0) writer.addInt("dist_mm", measurement.dist_mm);
  writer.addInt("rssi", net.rssi());
  writer.addString("wake", wakeReason);
  writer.addUInt("wifi_ms", net.wifiMs());
  writer.addUInt("mqtt_ms", net.mqttMs());
  writer.addString("fw", FW_VERSION);
  writer.addString("hw", HW_NAME);
  writer.addUInt("cfg_ver", cfg.version);
  if (!sentOnce) writer.addString("reset", board.resetReason());
  writer.end();
}

// --- сеть ----------------------------------------------------------------------
static void flushEvents() {
  while (eventCount > 0 && net.mqttConnected()) {
    if (!net.publishEvent(eventQueue[0])) return;
    for (uint8_t i = 1; i < eventCount; i++) {
      memcpy(eventQueue[i - 1], eventQueue[i], EVENT_PAYLOAD_SIZE);
    }
    eventCount--;
  }
}

static bool sendTelemetry(const Measurement &measurement) {
  if (!net.mqttConnected()) {
    Serial.println("[net] нет связи с брокером — отправлю, когда появится");
    return false;
  }
  flushEvents();
  seq++;
  char payload[420];
  buildTelemetry(payload, sizeof(payload), measurement);
  bool ok = net.publishTelemetry(payload);
  Serial.printf("[net] телеметрия: %s\n", payload);
  if (ok) {
    lastSentFill = measurement.fill;
    lastSentMs = millis();
    sentOnce = true;
  }
  return ok;
}

static void handleConfig() {
  bool wasClaimed = cfg.claimed;
  if (!net.applyConfig(cfg)) return;
  storage.saveConfig(cfg);
  NetLink::applyTimezone(cfg.tz);
  if (cfg.claimed && !wasClaimed) {
    Serial.println("[net] устройство привязано к аккаунту");
    indicator.stopBlinking();
    claimBlinking = false;
    indicator.blink(colors::GREEN, 3, 200, 200);
    indicator.beep(2);
  }
  // новый интервал может оказаться короче — не ждём старого
  uint32_t soon = millis() + chooseIntervalS(cfg, lastSentFill, localHour()) * 1000UL;
  if ((int32_t)(nextMeasureMs - soon) > 0) nextMeasureMs = soon;
}

// Пока устройство не привязано к аккаунту, светодиод медленно мигает бирюзовым
static void updateClaimIndicator(bool online) {
  bool waiting = online && !cfg.claimed;
  if (waiting && !claimBlinking) {
    indicator.startBlinking(colors::CYAN, CLAIM_BLINK_MS);
    claimBlinking = true;
  } else if (!waiting && claimBlinking) {
    indicator.stopBlinking();
    claimBlinking = false;
  }
}

// --- действия ------------------------------------------------------------------
static Measurement measureDistance(uint8_t samples) {
  Measurement measurement = sensor.read(samples, cfg);
  Serial.printf("[измерение] %d мм, заполнено %d%%, годных замеров %d%s\n", measurement.dist_mm,
                measurement.fill, measurement.samples_ok,
                measurement.error ? measurement.error : "");
  return measurement;
}

// Замер по расписанию или по запросу человека. true — данные ушли на сервер.
static bool measureCycle() {
  Measurement measurement = measureDistance(cfg.samples);
  bool requested = interactive;
  interactive = false;

  // Датчика крышки нет: резкий скачок или сбой может значить, что крышку открыли
  // прямо во время замера. Один раз перемеряем, прежде чем сообщать серверу.
  bool recheck = !requested && sentOnce && !recheckPending &&
                 needsRecheck(measurement.fill, lastSentFill, !measurement.ok);
  if (recheck) {
    recheckPending = true;
    Serial.printf("[измерение] скачок уровня или сбой — повторю через %u с\n",
                  (unsigned)RECHECK_DELAY_S);
    scheduleMeasure(RECHECK_DELAY_S);
    return false;
  }
  recheckPending = false;

  if (!measurement.ok && measurement.error) {
    queueSimpleEvent("error", "code", measurement.error);
  }
  if (requested && measurement.dist_mm > 0) {
    claimBlinking = false;  // показ цвета прерывает мигание — потом оно включится снова
    indicator.stopBlinking();
    indicator.fillColor(measurement.fill, cfg.full_pct);
    delay(1500);
    indicator.off();
  }

  bool sent = false;
  bool send = shouldSend(cfg, measurement.fill, lastSentFill, secondsSinceSend(), requested,
                         !sentOnce, eventCount > 0, !measurement.ok);
  if (send) {
    sent = sendTelemetry(measurement);
    if (requested) {
      if (sent) {
        indicator.beep(1);
      } else {
        indicator.blink(colors::RED, 3);
        indicator.beep(3);
      }
    }
  } else {
    Serial.println("[измерение] изменений нет — не отправляю");
  }
  wakeReason = "timer";
  scheduleMeasure(chooseIntervalS(cfg, measurement.fill, localHour()));
  return sent;
}

// Калибровка: устройство стоит на пустом контейнере, кнопку держали 3 секунды.
// Датчика крышки нет, поэтому перед замером просто даём время закрыть крышку.
static bool doCalibration() {
  Serial.printf("[калибровка] закройте крышку, замер через %u с…\n",
                (unsigned)(CALIBRATION_DELAY_MS / 1000));
  claimBlinking = false;
  indicator.startBlinking(colors::PURPLE, 400);
  uint32_t started = millis();
  while (millis() - started < CALIBRATION_DELAY_MS) {
    indicator.tick();
    delay(50);
  }

  DeviceConfig probe = cfg;
  probe.empty_mm = 0;  // при калибровке заполненность не считаем
  Measurement measurement = sensor.read(SENSOR_MAX_SAMPLES, probe);
  indicator.stopBlinking();

  if (measurement.dist_mm <= 0 || measurement.samples_ok < 3) {
    Serial.println("[калибровка] не удалась");
    indicator.blink(colors::RED, 3);
    indicator.beep(3);
    queueSimpleEvent("error", "code", "CALIBRATION_FAILED");
    return false;
  }

  cfg.empty_mm = (uint32_t)measurement.dist_mm;
  if (cfg.full_mm == 0 || cfg.full_mm >= cfg.empty_mm) {
    cfg.full_mm = cfg.empty_mm > DEFAULT_FULL_MM * 2 ? DEFAULT_FULL_MM : cfg.empty_mm / 4;
  }
  storage.saveCalibration(cfg.empty_mm, cfg.full_mm);

  char payload[EVENT_PAYLOAD_SIZE];
  json::Writer writer(payload, sizeof(payload));
  writer.begin();
  writer.addString("type", "calibrated");
  writer.addUInt("empty_mm", cfg.empty_mm);
  writer.addUInt("full_mm", cfg.full_mm);
  writer.end();
  queueEvent(payload);

  Serial.printf("[калибровка] глубина контейнера %u мм\n", (unsigned)cfg.empty_mm);
  indicator.blink(colors::GREEN, 3, 200, 200);
  indicator.beep(1, 400);

  // сразу отправить событие и новый уровень
  interactive = true;
  wakeReason = "button";
  nextMeasureMs = millis();
  return true;
}

// Команда send из консоли: измерить и немедленно отправить.
static bool doSendNow() {
  interactive = true;
  wakeReason = "button";
  return measureCycle();
}

// Нажатие кнопки разбираем по времени удержания.
static void handleButton() {
  uint32_t started = millis();
  claimBlinking = false;
  indicator.stopBlinking();
  indicator.set(colors::WHITE);
  while (board.buttonPressed() && millis() - started < BUTTON_RESET_MS + 2000) {
    uint32_t held = millis() - started;
    if (held >= BUTTON_RESET_MS) {
      indicator.set(colors::RED);
    } else if (held >= BUTTON_CAL_MS) {
      indicator.set(colors::PURPLE);
    }
    delay(50);
  }
  uint32_t held = millis() - started;
  indicator.off();
  Serial.printf("[кнопка] удержание %u мс\n", (unsigned)held);

  if (held >= BUTTON_RESET_MS) {
    Serial.println("[кнопка] сброс настроек и новая настройка Wi-Fi");
    indicator.blink(colors::RED, 5, 100, 100);
    storage.factoryReset();
    net.startPortal(PORTAL_TIMEOUT_S);
    board.restart();  // начать с чистого листа: заново получить настройки с сервера
  } else if (held >= BUTTON_CAL_MS) {
    doCalibration();
  } else {
    interactive = true;
    wakeReason = "button";
    measureCycle();
  }
}

// --- запуск ----------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(50);

  indicator.begin();
  board.begin();
  storage.begin();
  storage.loadConfig(cfg);
  storage.loadCredentials(creds);
  NetLink::applyTimezone(cfg.tz);
  sensor.begin();
  bootId = board.random32();
  Serial.printf("\n[старт] %s fw=%s hw=%s причина=%s\n", deviceId(), FW_VERSION, HW_NAME,
                board.resetReason());

  // Окно консоли после включения: через него работает provision.py
  console.setActions(doCalibration, doSendNow);
  console.run(CONSOLE_WINDOW_MS, cfg, creds);
  storage.loadCredentials(creds);

  char payload[EVENT_PAYLOAD_SIZE];
  json::Writer writer(payload, sizeof(payload));
  writer.begin();
  writer.addString("type", "hello");
  writer.addString("fw", FW_VERSION);
  writer.addString("hw", HW_NAME);
  writer.addString("reset", board.resetReason());
  writer.end();
  queueEvent(payload);

  if (!creds.provisioned) {
    // Без учётки MQTT работать не с кем; консоль остаётся доступной
    Serial.println("[старт] нет учётных данных — запустите tools/provision.py");
    indicator.blink(colors::RED, 3, 300, 200);
  }

  // Первое включение: Wi-Fi ещё не настроен — поднимаем портал
  if (!storage.loadWifi(wifiSsid, sizeof(wifiSsid), wifiPass, sizeof(wifiPass)) &&
      creds.provisioned) {
    Serial.println("[старт] Wi-Fi не настроен, открываю портал");
    if (!net.startPortal(PORTAL_TIMEOUT_S)) board.restart();  // никто не настроил — ещё раз
    storage.loadWifi(wifiSsid, sizeof(wifiSsid), wifiPass, sizeof(wifiPass));
    wakeReason = "setup";
  }

  net.begin(cfg.tz);
  nextMeasureMs = millis();  // первый замер сразу
}

void loop() {
  console.poll(cfg, creds);

  if (board.buttonPressed()) {
    delay(BUTTON_DEBOUNCE_MS);
    if (board.buttonPressed()) handleButton();
  }

  bool online = net.maintain(wifiSsid, wifiPass, creds);
  if (online) {
    handleConfig();
    flushEvents();
    // связь появилась, а первое сообщение ещё не ушло — мерить сразу
    if (!wasOnline && !sentOnce) nextMeasureMs = millis();
  }
  wasOnline = online;
  updateClaimIndicator(online);

  if (timeReached(nextMeasureMs)) measureCycle();

  indicator.tick();
  delay(10);
}
