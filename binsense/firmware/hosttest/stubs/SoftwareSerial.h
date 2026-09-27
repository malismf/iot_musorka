// Заглушка программного UART ESP8266.
#pragma once

#include "Arduino.h"

class SoftwareSerial : public Stream {
 public:
  SoftwareSerial(int8_t, int8_t) {}
  void begin(unsigned long) {}
};
