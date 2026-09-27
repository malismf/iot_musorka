// Заглушка эмуляции EEPROM: байты в памяти процесса.
#pragma once

#include <cstring>
#include <vector>

#include "Arduino.h"

class EEPROMClass {
 public:
  void begin(size_t size) { data_.assign(size, 0xFF); }
  template <typename T>
  T &get(int address, T &value) {
    std::memcpy(&value, data_.data() + address, sizeof(T));
    return value;
  }
  template <typename T>
  const T &put(int address, const T &value) {
    std::memcpy(data_.data() + address, &value, sizeof(T));
    return value;
  }
  bool commit() { return true; }

 private:
  std::vector<uint8_t> data_;
};

extern EEPROMClass EEPROM;
