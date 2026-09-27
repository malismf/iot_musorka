// Сеть: Wi-Fi, MQTT (QoS 1), NTP и публикация сообщений.
//
// Устройство работает от USB и держит подключение постоянно: maintain()
// вызывается из loop() и переподключает Wi-Fi и брокер, если связь пропала.
// Настройки приходят retained-сообщением сразу после подписки и потом — при
// каждом изменении на сервере.
#pragma once

#include <Arduino.h>

#include "config.h"

// Идентификатор устройства: bin- + последние три байта MAC-адреса.
const char *deviceId();

class NetLink {
 public:
  void begin();
  // Поддерживает подключение; возвращает true, если брокер доступен.
  bool maintain(const char *ssid, const char *pass, const Credentials &creds);
  // Портал настройки: устройство поднимает точку доступа BinSense-XXXX.
  bool startPortal(uint32_t timeoutS);
  bool wifiConnected();
  bool mqttConnected();
  int rssi();
  uint32_t wifiMs() const { return wifiMs_; }
  uint32_t mqttMs() const { return mqttMs_; }

  // Разбирает полученные настройки. true — пришло что-то новое.
  bool applyConfig(DeviceConfig &cfg);

  bool publishTelemetry(const char *payload);
  bool publishEvent(const char *payload);
  const char *lastError() const { return lastError_; }

 private:
  bool connectWifi(const char *ssid, const char *pass);
  bool connectMqtt(const Credentials &creds);

  uint32_t lastWifiAttempt_ = 0;
  uint32_t lastMqttAttempt_ = 0;
  bool wifiTried_ = false;
  bool mqttTried_ = false;
  uint32_t wifiMs_ = 0;
  uint32_t mqttMs_ = 0;
  const char *lastError_ = "";
};

extern NetLink net;
