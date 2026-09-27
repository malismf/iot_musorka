// Питание датчика, измерение заряда аккумулятора и уход в глубокий сон.
#pragma once

#include <Arduino.h>

#include "config.h"

class Power {
 public:
  void begin();
  void sensorOn();
  void sensorOff();
  float batteryVolts();
  bool buttonPressed();
  // Настраивает источники пробуждения и уходит в сон (функция не возвращается).
  void deepSleep(uint32_t seconds);
  const char *resetReason();
};

extern Power power;
