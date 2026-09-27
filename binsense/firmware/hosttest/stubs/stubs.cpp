// Реализация заглушек: минимальное поведение, достаточное для проверки сборки.
#include "Arduino.h"

#include <chrono>

#include "EEPROM.h"
#include "ESP8266WiFi.h"
#include "MQTT.h"

HardwareSerial Serial;
HardwareSerial Serial1;
EspClass ESP;
WiFiClass WiFi;
EEPROMClass EEPROM;

static const auto startTime = std::chrono::steady_clock::now();

unsigned long millis() {
  auto now = std::chrono::steady_clock::now();
  return (unsigned long)std::chrono::duration_cast<std::chrono::milliseconds>(now - startTime)
      .count();
}

void delay(unsigned long) {}
void delayMicroseconds(unsigned int) {}
void pinMode(uint8_t, uint8_t) {}
void digitalWrite(uint8_t, uint8_t) {}
int digitalRead(uint8_t) { return HIGH; }
void analogWrite(uint8_t, int) {}
void analogWriteRange(uint32_t) {}
void analogWriteFreq(uint32_t) {}
unsigned long pulseIn(uint8_t, uint8_t, unsigned long) { return 5800; }
void configTime(const char *, const char *, const char *, const char *) {}
