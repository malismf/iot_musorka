#pragma once

#include <functional>

#include "Arduino.h"

class WiFiManager {
 public:
  void setConfigPortalTimeout(unsigned long) {}
  void setConnectTimeout(unsigned long) {}
  void setDebugOutput(bool) {}
  void setAPCallback(std::function<void(WiFiManager *)>) {}
  void setSaveConfigCallback(std::function<void()>) {}
  bool autoConnect(const char * = nullptr, const char * = nullptr) { return true; }
  bool startConfigPortal(const char * = nullptr, const char * = nullptr) { return true; }
  void resetSettings() {}
  String getWiFiSSID(bool = true) { return String("test"); }
  String getWiFiPass(bool = true) { return String("password"); }
};
