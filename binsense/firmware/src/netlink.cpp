#include "netlink.h"

#include <ESP8266WiFi.h>
#include <MQTT.h>
#include <WiFiManager.h>
#include <time.h>

#include "indicator.h"
#include "json_lite.h"
#include "storage.h"

NetLink net;

static WiFiClient wifiClient;
static MQTTClient mqtt(512);
static char configPayload[512] = {0};
static bool configReceived = false;

const char *deviceId() {
  static char id[16] = {0};
  if (id[0] == '\0') {
    // ChipId — последние три байта MAC-адреса: их достаточно для уникальности
    snprintf(id, sizeof(id), "bin-%06x", (unsigned)(ESP.getChipId() & 0xFFFFFFu));
  }
  return id;
}

static String topicFor(const char *suffix) {
  return String("bins/") + deviceId() + "/" + suffix;
}

static void onMqttMessage(String &topic, String &payload) {
  if (!topic.endsWith("/config")) return;
  strncpy(configPayload, payload.c_str(), sizeof(configPayload) - 1);
  configPayload[sizeof(configPayload) - 1] = '\0';
  configReceived = true;
}

static bool due(uint32_t last, uint32_t period, bool tried) {
  return !tried || millis() - last >= period;
}

// --- Подключение ------------------------------------------------------------
void NetLink::begin() {
  WiFi.persistent(false);  // данные Wi-Fi храним сами, во флеш SDK не пишем
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  // Время нужно только для меток в телеметрии (UTC). NTP опрашивается в фоне;
  // без интернета время просто не появится
  configTime("UTC0", "pool.ntp.org", "time.google.com");
}

bool NetLink::connectWifi(const char *ssid, const char *pass) {
  uint32_t started = millis();
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED && millis() - started < WIFI_TIMEOUT_MS) {
    indicator.tick();
    delay(100);
  }
  if (WiFi.status() != WL_CONNECTED) {
    lastError_ = "WIFI_FAIL";
    Serial.printf("[wifi] не подключился к %s\n", ssid);
    return false;
  }
  wifiMs_ = millis() - started;
  Serial.printf("[wifi] %s, %d dBm, IP %s, %u мс\n", ssid, WiFi.RSSI(),
                WiFi.localIP().toString().c_str(), (unsigned)wifiMs_);
  return true;
}

bool NetLink::connectMqtt(const Credentials &creds) {
  uint32_t started = millis();
  configReceived = false;
  mqtt.begin(creds.host, creds.port, wifiClient);
  mqtt.setOptions(60 /* keepalive */, true /* clean session */, MQTT_TIMEOUT_MS);
  mqtt.onMessage(onMqttMessage);
  if (!mqtt.connect(deviceId(), creds.user, creds.pass)) {
    Serial.printf("[mqtt] ошибка подключения к %s:%u: err=%d rc=%d\n", creds.host, creds.port,
                  (int)mqtt.lastError(), (int)mqtt.returnCode());
    lastError_ = "MQTT_FAIL";
    return false;
  }
  mqttMs_ = millis() - started;
  // retained-настройки придут сразу после подписки
  mqtt.subscribe(topicFor("config").c_str(), 1);
  Serial.printf("[mqtt] подключено к %s:%u за %u мс\n", creds.host, creds.port,
                (unsigned)mqttMs_);
  return true;
}

bool NetLink::maintain(const char *ssid, const char *pass, const Credentials &creds) {
  if (WiFi.status() != WL_CONNECTED) {
    if (!ssid || !ssid[0] || !due(lastWifiAttempt_, WIFI_RETRY_MS, wifiTried_)) return false;
    lastWifiAttempt_ = millis();
    wifiTried_ = true;
    if (!connectWifi(ssid, pass)) return false;
    mqttTried_ = false;  // сеть появилась — к брокеру сразу, без паузы
  }
  if (!creds.provisioned) return false;
  if (!mqtt.connected()) {
    if (!due(lastMqttAttempt_, MQTT_RETRY_MS, mqttTried_)) return false;
    lastMqttAttempt_ = millis();
    mqttTried_ = true;
    if (!connectMqtt(creds)) return false;
  }
  mqtt.loop();
  return mqtt.connected();
}

bool NetLink::startPortal(uint32_t timeoutS) {
  WiFiManager wm;
  wm.setConfigPortalTimeout(timeoutS);
  wm.setConnectTimeout(20);
  wm.setDebugOutput(false);
  wm.setAPCallback([](WiFiManager *) { indicator.startBlinking(colors::BLUE, 800); });

  String apName = String("BinSense-") + (deviceId() + 4);
  Serial.printf("[wifi] режим настройки: точка доступа %s\n", apName.c_str());
  indicator.startBlinking(colors::BLUE, 800);
  bool ok = wm.startConfigPortal(apName.c_str());
  indicator.stopBlinking();

  if (ok) {
    storage.saveWifi(wm.getWiFiSSID().c_str(), wm.getWiFiPass().c_str());
    indicator.blink(colors::GREEN, 1, 800, 0);
    wifiTried_ = false;
  } else {
    indicator.blink(colors::RED, 3);
    lastError_ = "PORTAL_TIMEOUT";
  }
  return ok;
}

bool NetLink::wifiConnected() { return WiFi.status() == WL_CONNECTED; }

bool NetLink::mqttConnected() { return mqtt.connected(); }

int NetLink::rssi() { return WiFi.RSSI(); }

// --- Настройки ----------------------------------------------------------------
bool NetLink::applyConfig(DeviceConfig &cfg) {
  if (!configReceived) return false;
  configReceived = false;
  long value = 0;
  bool flag = false;

  long version = 0;
  if (!json::getInt(configPayload, "ver", version)) return false;

  bool claimedNow = cfg.claimed;
  if (json::getBool(configPayload, "claimed", flag)) claimedNow = flag;

  if ((uint32_t)version <= cfg.version && claimedNow == cfg.claimed) {
    return false;  // ничего нового
  }

  cfg.version = (uint32_t)version;
  cfg.claimed = claimedNow;
  if (json::getInt(configPayload, "interval_s", value)) cfg.interval_s = (uint32_t)value;
  if (json::getInt(configPayload, "heartbeat_s", value)) cfg.heartbeat_s = (uint32_t)value;
  if (json::getInt(configPayload, "full_interval_s", value)) cfg.full_interval_s = (uint32_t)value;
  if (json::getInt(configPayload, "full_pct", value)) cfg.full_pct = (uint8_t)value;
  if (json::getInt(configPayload, "delta_pct", value)) cfg.delta_pct = (uint8_t)value;
  if (json::getInt(configPayload, "samples", value)) {
    cfg.samples = (uint8_t)(value > SENSOR_MAX_SAMPLES ? SENSOR_MAX_SAMPLES : value);
  }
  if (json::getInt(configPayload, "empty_mm", value) && value > 0) cfg.empty_mm = (uint32_t)value;
  if (json::getInt(configPayload, "full_mm", value) && value > 0) cfg.full_mm = (uint32_t)value;
  Serial.printf("[cfg] приняты настройки версии %u\n", (unsigned)cfg.version);
  return true;
}

bool NetLink::publishTelemetry(const char *payload) {
  bool ok = mqtt.publish(topicFor("telemetry").c_str(), payload, false, 1);
  if (!ok) lastError_ = "PUBLISH_FAIL";
  return ok;
}

bool NetLink::publishEvent(const char *payload) {
  bool ok = mqtt.publish(topicFor("event").c_str(), payload, false, 1);
  if (!ok) lastError_ = "PUBLISH_FAIL";
  return ok;
}
