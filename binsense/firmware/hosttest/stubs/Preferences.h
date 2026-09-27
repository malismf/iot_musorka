// Заглушка NVS: хранит значения в памяти процесса.
#pragma once

#include <map>
#include <string>

#include "Arduino.h"

class Preferences {
 public:
  bool begin(const char *, bool = false, const char * = nullptr) { return true; }
  void end() {}
  bool clear() {
    ints_.clear();
    strings_.clear();
    return true;
  }
  bool remove(const char *key) {
    ints_.erase(key);
    strings_.erase(key);
    return true;
  }
  size_t putUInt(const char *key, uint32_t value) {
    ints_[key] = value;
    return 4;
  }
  size_t putInt(const char *key, int32_t value) {
    ints_[key] = (uint32_t)value;
    return 4;
  }
  size_t putBool(const char *key, bool value) {
    ints_[key] = value ? 1 : 0;
    return 1;
  }
  size_t putString(const char *key, const char *value) {
    strings_[key] = value ? value : "";
    return strlen(value ? value : "");
  }
  size_t putString(const char *key, String value) { return putString(key, value.c_str()); }
  uint32_t getUInt(const char *key, uint32_t fallback = 0) {
    auto it = ints_.find(key);
    return it == ints_.end() ? fallback : it->second;
  }
  int32_t getInt(const char *key, int32_t fallback = 0) {
    return (int32_t)getUInt(key, (uint32_t)fallback);
  }
  bool getBool(const char *key, bool fallback = false) {
    auto it = ints_.find(key);
    return it == ints_.end() ? fallback : it->second != 0;
  }
  String getString(const char *key, String fallback = String()) {
    auto it = strings_.find(key);
    return it == strings_.end() ? fallback : String(it->second.c_str());
  }
  bool isKey(const char *key) {
    return ints_.count(key) != 0 || strings_.count(key) != 0;
  }

 private:
  std::map<std::string, uint32_t> ints_;
  std::map<std::string, std::string> strings_;
};
