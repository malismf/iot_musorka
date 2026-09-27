// Измерение расстояния до мусора.
//
// Основной вариант — влагозащищённый датчик с выходом UART (A02YYUW или
// JSN-SR04T v3, переведённый в режим UART). У ESP8266 второго аппаратного UART
// нет, поэтому датчик читается программным (SoftwareSerial). Поддержан и
// HC-SR04 с классическими Trig/Echo (собирается с флагом -DSENSOR_PULSE).
#pragma once

#include <Arduino.h>

#include "config.h"

class Sensor {
 public:
  void begin();
  // Делает samples замеров, отбрасывает недостоверные и возвращает медиану.
  Measurement read(uint8_t samples, const DeviceConfig &cfg);
  // Один «сырой» замер в мм (для консоли и отладки); <= 0 — ошибка.
  int readOnce();

 private:
#ifndef SENSOR_PULSE
  Stream *uart_ = nullptr;
  void flushInput();
#endif
};

extern Sensor sensor;
