#include "indicator.h"

Indicator indicator;

void Indicator::begin() {
  // Программный ШИМ ESP8266: 8 бит, 1 кГц — мерцания не видно
  analogWriteRange(255);
  analogWriteFreq(1000);
  pinMode(PIN_LED_R, OUTPUT);
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_B, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  off();
}

void Indicator::set(const Color &color) {
  // светодиод с общим катодом: больше скважность — ярче
  analogWrite(PIN_LED_R, color.r);
  analogWrite(PIN_LED_G, color.g);
  analogWrite(PIN_LED_B, color.b);
}

void Indicator::off() { set(colors::OFF); }

void Indicator::blink(const Color &color, int times, int onMs, int offMs) {
  for (int i = 0; i < times; i++) {
    set(color);
    delay(onMs);
    off();
    if (i + 1 < times) delay(offMs);
  }
}

void Indicator::beep(int times, int onMs, int offMs) {
#ifndef NO_BUZZER
  for (int i = 0; i < times; i++) {
    digitalWrite(PIN_BUZZER, HIGH);
    delay(onMs);
    digitalWrite(PIN_BUZZER, LOW);
    if (i + 1 < times) delay(offMs);
  }
#else
  (void)times;
  (void)onMs;
  (void)offMs;
#endif
}

void Indicator::fillColor(int fill, uint8_t fullPct) {
  if (fill < 0) {
    set(colors::CYAN);  // нет калибровки
  } else if (fill >= fullPct) {
    set(colors::RED);
  } else if (fill >= 50) {
    set(colors::YELLOW);
  } else {
    set(colors::GREEN);
  }
}

void Indicator::startBlinking(const Color &color, int periodMs) {
  blinking_ = true;
  blinkColor_ = color;
  blinkPeriod_ = periodMs;
  lastToggle_ = millis();
  phase_ = true;
  set(color);
}

void Indicator::stopBlinking() {
  blinking_ = false;
  off();
}

void Indicator::tick() {
  if (!blinking_) return;
  uint32_t now = millis();
  if (now - lastToggle_ < (uint32_t)blinkPeriod_ / 2) return;
  lastToggle_ = now;
  phase_ = !phase_;
  set(phase_ ? blinkColor_ : colors::OFF);
}
