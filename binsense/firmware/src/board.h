// Плата: кнопка, причина перезагрузки, случайное число, перезапуск.
// Устройство питается от USB и не спит, поэтому управления питанием здесь нет.
#pragma once

#include <Arduino.h>

#include "config.h"

class Board {
 public:
  void begin();
  bool buttonPressed();
  const char *resetReason();
  uint32_t random32();
  void restart();
};

extern Board board;
