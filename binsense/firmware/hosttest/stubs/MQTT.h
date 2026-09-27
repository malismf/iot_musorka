#pragma once

#include "Arduino.h"
#include "ESP8266WiFi.h"

typedef void (*MQTTClientCallbackSimple)(String &topic, String &payload);

class MQTTClient {
 public:
  explicit MQTTClient(int = 128) {}
  void begin(const char *, int, Client &) {}
  void onMessage(MQTTClientCallbackSimple callback) { callback_ = callback; }
  void setOptions(int, bool, int) {}
  bool connect(const char *, const char * = nullptr, const char * = nullptr, bool = false) {
    return true;
  }
  bool publish(const char *, const char *, bool, int) { return true; }
  bool subscribe(const char *, int = 0) { return true; }
  bool loop() { return true; }
  bool connected() { return true; }
  bool disconnect() { return true; }
  int lastError() { return 0; }
  int returnCode() { return 0; }

 private:
  MQTTClientCallbackSimple callback_ = nullptr;
};
