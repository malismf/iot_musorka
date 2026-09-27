// Минимальные работа с JSON: чтение плоских объектов и сборка сообщений.
//
// Зачем свой код вместо ArduinoJson: сообщения устройства простые и плоские,
// а так прошивка не зависит от внешней библиотеки и логику можно полностью
// покрыть тестами на обычном компьютере (firmware/hosttest).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace json {

// Чтение значения по ключу верхнего уровня. Возвращает false, если ключа нет.
bool getInt(const char *doc, const char *key, long &out);
bool getBool(const char *doc, const char *key, bool &out);
bool getString(const char *doc, const char *key, char *out, size_t maxLen);

// Сборка JSON в заранее выделенный буфер (без динамической памяти).
class Writer {
 public:
  Writer(char *buffer, size_t capacity);
  void begin();
  void end();
  void addInt(const char *key, long value);
  void addUInt(const char *key, unsigned long value);
  void addFloat(const char *key, float value, int decimals = 2);
  void addBool(const char *key, bool value);
  void addString(const char *key, const char *value);
  bool ok() const { return !overflow_; }
  size_t length() const { return length_; }
  const char *c_str() const { return buffer_; }

 private:
  void put(const char *text);
  void putChar(char symbol);
  void putKey(const char *key);

  char *buffer_;
  size_t capacity_;
  size_t length_;
  bool first_;
  bool overflow_;
};

}  // namespace json
