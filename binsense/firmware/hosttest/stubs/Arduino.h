// Заглушки Arduino/ESP8266 для проверки прошивки на обычном компьютере.
// Они НЕ используются при сборке для ESP8266 — только в firmware/hosttest/run.sh,
// чтобы поймать ошибки компиляции и прогнать тесты логики без железа.
#pragma once

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <string>

#define F(x) (x)
#define PROGMEM

#define HIGH 1
#define LOW 0
#define INPUT 0x01
#define OUTPUT 0x03
#define INPUT_PULLUP 0x05
#define SERIAL_8N1 0x800001c

#ifndef constrain
#define constrain(amt, low, high) ((amt) < (low) ? (low) : ((amt) > (high) ? (high) : (amt)))
#endif


class String {
 public:
  String() {}
  String(const char *text) : value_(text ? text : "") {}
  String(const std::string &text) : value_(text) {}
  String(int number) : value_(std::to_string(number)) {}
  String(unsigned number) : value_(std::to_string(number)) {}

  const char *c_str() const { return value_.c_str(); }
  size_t length() const { return value_.size(); }
  void trim() {
    size_t start = value_.find_first_not_of(" \t\r\n");
    size_t end = value_.find_last_not_of(" \t\r\n");
    value_ = (start == std::string::npos) ? "" : value_.substr(start, end - start + 1);
  }
  int indexOf(char symbol) const {
    size_t position = value_.find(symbol);
    return position == std::string::npos ? -1 : (int)position;
  }
  int indexOf(const char *text) const {
    size_t position = value_.find(text);
    return position == std::string::npos ? -1 : (int)position;
  }
  String substring(int from) const { return String(value_.substr((size_t)from)); }
  String substring(int from, int to) const {
    return String(value_.substr((size_t)from, (size_t)(to - from)));
  }
  bool startsWith(const char *text) const { return value_.rfind(text, 0) == 0; }
  bool endsWith(const char *text) const {
    size_t len = strlen(text);
    return value_.size() >= len && value_.compare(value_.size() - len, len, text) == 0;
  }
  long toInt() const { return strtol(value_.c_str(), nullptr, 10); }
  String &operator+=(char symbol) {
    value_ += symbol;
    return *this;
  }
  String &operator+=(const char *text) {
    value_ += text;
    return *this;
  }
  bool operator==(const char *text) const { return value_ == text; }
  friend String operator+(const String &left, const char *right) {
    return String(left.value_ + right);
  }
  friend String operator+(const String &left, const String &right) {
    return String(left.value_ + right.value_);
  }
  friend String operator+(const char *left, const String &right) {
    return String(std::string(left) + right.value_);
  }

 private:
  std::string value_;
};

class Stream {
 public:
  virtual int available() { return 0; }
  virtual int read() { return -1; }
  void setTimeout(unsigned long) {}
};

class HardwareSerial : public Stream {
 public:
  void begin(unsigned long) {}
  void begin(unsigned long, uint32_t, int8_t, int8_t) {}
  void print(const char *text) { fputs(text, stdout); }
  void println() { fputs("\n", stdout); }
  void println(const char *text) { printf("%s\n", text); }
  void println(const String &text) { printf("%s\n", text.c_str()); }
  int printf(const char *format, ...) {
    va_list args;
    va_start(args, format);
    int written = vprintf(format, args);
    va_end(args);
    return written;
  }
  void flush() {}
};

extern HardwareSerial Serial;
extern HardwareSerial Serial1;

unsigned long millis();
void delay(unsigned long ms);
void delayMicroseconds(unsigned int us);
void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, uint8_t value);
int digitalRead(uint8_t pin);
void analogWrite(uint8_t pin, int value);
void analogWriteRange(uint32_t range);
void analogWriteFreq(uint32_t freq);
unsigned long pulseIn(uint8_t pin, uint8_t state, unsigned long timeout);
void configTime(const char *tz, const char *server1, const char *server2 = nullptr,
                const char *server3 = nullptr);

struct rst_info {
  uint32_t reason;
};

class EspClass {
 public:
  uint32_t getChipId() { return 0x445566; }
  uint32_t random() { return 42; }
  void restart() { printf("[stub] restart\n"); }
  rst_info *getResetInfoPtr() {
    static rst_info info = {0};
    return &info;
  }
};
extern EspClass ESP;
