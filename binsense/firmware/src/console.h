// Последовательная консоль: заводская настройка и проверка железа при сборке.
//
// После включения питания устройство несколько секунд ждёт команду (с этим
// окном работает tools/provision.py: info, prov, exit), а дальше консоль
// опрашивается из loop() и доступна всё время: measure, button, led, beep.
#pragma once

#include <Arduino.h>

#include "config.h"

typedef bool (*ConsoleAction)();

class Console {
 public:
  void banner(const DeviceConfig &cfg, const Credentials &creds);
  // Ждёт команду windowMs миллисекунд; после первой команды остаётся в консоли.
  void run(uint32_t windowMs, DeviceConfig &cfg, Credentials &creds);
  // Неблокирующий разбор ввода — вызывается из loop().
  void poll(DeviceConfig &cfg, Credentials &creds);
  void setActions(ConsoleAction calibrate, ConsoleAction sendNow) {
    calibrate_ = calibrate;
    sendNow_ = sendNow;
  }

 private:
  void help();
  void printInfo(const DeviceConfig &cfg, const Credentials &creds);
  bool handle(String line, DeviceConfig &cfg, Credentials &creds);

  String buffer_;
  ConsoleAction calibrate_ = nullptr;
  ConsoleAction sendNow_ = nullptr;
};

extern Console console;
