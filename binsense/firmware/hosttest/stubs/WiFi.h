#pragma once

#include "Arduino.h"

#define WL_CONNECTED 3
#define WIFI_STA 1
#define WIFI_OFF 0

class Client {};

class WiFiClient : public Client {};

class WiFiClass {
 public:
  int status() { return WL_CONNECTED; }
  int begin(const char *, const char * = nullptr, int32_t = 0, const uint8_t * = nullptr,
            bool = true) {
    return WL_CONNECTED;
  }
  int begin() { return WL_CONNECTED; }
  void disconnect(bool = false, bool = false) {}
  void mode(int) {}
  void setSleep(bool) {}
  void persistent(bool) {}
  int32_t RSSI() { return -62; }
  uint8_t *BSSID() {
    static uint8_t bssid[6] = {1, 2, 3, 4, 5, 6};
    return bssid;
  }
  int32_t channel() { return 6; }
  String SSID() { return String("test"); }
};

extern WiFiClass WiFi;
