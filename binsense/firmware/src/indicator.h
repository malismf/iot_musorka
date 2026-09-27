// Обратная связь для пользователя: RGB-светодиод и зуммер.
// Каждому действию соответствует свой цвет — см. docs/USER_GUIDE.md.
#pragma once

#include <Arduino.h>

#include "config.h"

struct Color {
  uint8_t r, g, b;
};

namespace colors {
const Color OFF = {0, 0, 0};
const Color RED = {255, 0, 0};
const Color GREEN = {0, 255, 0};
const Color BLUE = {0, 0, 255};
const Color YELLOW = {255, 180, 0};
const Color PURPLE = {180, 0, 255};
const Color CYAN = {0, 200, 200};
const Color WHITE = {255, 255, 255};
}  // namespace colors

class Indicator {
 public:
  void begin();
  void set(const Color &color);
  void off();
  void blink(const Color &color, int times, int onMs = 150, int offMs = 150);
  void beep(int times = 1, int onMs = 60, int offMs = 60);
  void fillColor(int fill, uint8_t fullPct);  // цвет по заполненности
  void tick();                                // мигание без блокировки (в порталах)
  void startBlinking(const Color &color, int periodMs);
  void stopBlinking();

 private:
  bool blinking_ = false;
  Color blinkColor_ = colors::OFF;
  int blinkPeriod_ = 500;
  uint32_t lastToggle_ = 0;
  bool phase_ = false;
};

extern Indicator indicator;
