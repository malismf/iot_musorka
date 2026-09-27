#pragma once

#include "Arduino.h"

#define WL_CONNECTED 3
#define WIFI_STA 1
#define WIFI_OFF 0

class Client {};

class WiFiClient : public Client {};

class IPAddress {
 public:
  String toString() const { return String("192.168.1.50"); }
};

class WiFiClass {
 public:
  int status() { return WL_CONNECTED; }
  int begin(const char *, const char * = nullptr, int32_t = 0, const uint8_t * = nullptr,
            bool = true) {
    return WL_CONNECTED;
  }
  bool disconnect(bool = false) { return true; }
  bool mode(int) { return true; }
  void persistent(bool) {}
  bool setAutoReconnect(bool) { return true; }
  int32_t RSSI() { return -62; }
  IPAddress localIP() { return IPAddress(); }
  String SSID() { return String("test"); }
};

extern WiFiClass WiFi;
