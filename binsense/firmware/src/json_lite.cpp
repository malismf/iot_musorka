#include "json_lite.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace json {
namespace {

// Ищет "key" и возвращает указатель на первый символ значения после двоеточия.
const char *findValue(const char *doc, const char *key) {
  if (!doc || !key) return nullptr;
  char pattern[64];
  snprintf(pattern, sizeof(pattern), "\"%s\"", key);
  const char *position = doc;
  while ((position = strstr(position, pattern)) != nullptr) {
    const char *cursor = position + strlen(pattern);
    while (*cursor == ' ' || *cursor == '\t' || *cursor == '\n' || *cursor == '\r') cursor++;
    if (*cursor == ':') {
      cursor++;
      while (*cursor == ' ' || *cursor == '\t' || *cursor == '\n' || *cursor == '\r') cursor++;
      return cursor;
    }
    position = cursor;
  }
  return nullptr;
}

}  // namespace

bool getInt(const char *doc, const char *key, long &out) {
  const char *value = findValue(doc, key);
  if (!value) return false;
  if (*value == 'n') return false;  // null
  char *end = nullptr;
  long parsed = strtol(value, &end, 10);
  if (end == value) return false;
  out = parsed;
  return true;
}

bool getBool(const char *doc, const char *key, bool &out) {
  const char *value = findValue(doc, key);
  if (!value) return false;
  if (strncmp(value, "true", 4) == 0) {
    out = true;
    return true;
  }
  if (strncmp(value, "false", 5) == 0) {
    out = false;
    return true;
  }
  if (*value == '0' || *value == '1') {
    out = (*value == '1');
    return true;
  }
  return false;
}

bool getString(const char *doc, const char *key, char *out, size_t maxLen) {
  const char *value = findValue(doc, key);
  if (!value || *value != '"' || maxLen == 0) return false;
  value++;
  size_t index = 0;
  while (*value && *value != '"' && index + 1 < maxLen) {
    if (*value == '\\' && value[1]) value++;  // простое экранирование
    out[index++] = *value++;
  }
  out[index] = '\0';
  return true;
}

size_t getIntArray(const char *doc, const char *key, long *out, size_t maxItems) {
  const char *value = findValue(doc, key);
  if (!value || *value != '[') return 0;
  value++;
  size_t count = 0;
  while (*value && *value != ']' && count < maxItems) {
    char *end = nullptr;
    long parsed = strtol(value, &end, 10);
    if (end == value) break;
    out[count++] = parsed;
    value = end;
    while (*value == ' ' || *value == ',') value++;
  }
  return count;
}

// --- Writer ------------------------------------------------------------------
Writer::Writer(char *buffer, size_t capacity)
    : buffer_(buffer), capacity_(capacity), length_(0), first_(true), overflow_(false) {
  if (capacity_ > 0) buffer_[0] = '\0';
}

void Writer::putChar(char symbol) {
  if (length_ + 1 >= capacity_) {
    overflow_ = true;
    return;
  }
  buffer_[length_++] = symbol;
  buffer_[length_] = '\0';
}

void Writer::put(const char *text) {
  while (*text) putChar(*text++);
}

void Writer::putKey(const char *key) {
  if (!first_) putChar(',');
  first_ = false;
  putChar('"');
  put(key);
  put("\":");
}

void Writer::begin() {
  length_ = 0;
  first_ = true;
  overflow_ = false;
  if (capacity_ > 0) buffer_[0] = '\0';
  putChar('{');
}

void Writer::end() { putChar('}'); }

void Writer::addInt(const char *key, long value) {
  char text[24];
  snprintf(text, sizeof(text), "%ld", value);
  putKey(key);
  put(text);
}

void Writer::addUInt(const char *key, unsigned long value) {
  char text[24];
  snprintf(text, sizeof(text), "%lu", value);
  putKey(key);
  put(text);
}

void Writer::addFloat(const char *key, float value, int decimals) {
  char text[32];
  snprintf(text, sizeof(text), "%.*f", decimals, (double)value);
  putKey(key);
  put(text);
}

void Writer::addBool(const char *key, bool value) {
  putKey(key);
  put(value ? "true" : "false");
}

void Writer::addString(const char *key, const char *value) {
  putKey(key);
  putChar('"');
  for (const char *cursor = value; *cursor; cursor++) {
    if (*cursor == '"' || *cursor == '\\') putChar('\\');
    if ((unsigned char)*cursor < 0x20) continue;  // управляющие символы пропускаем
    putChar(*cursor);
  }
  putChar('"');
}

}  // namespace json
