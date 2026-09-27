// Хранение настроек во флеше (эмуляция EEPROM): учётка MQTT, Wi-Fi, калибровка,
// конфиг. Всё лежит одной структурой с контрольной суммой: повреждённые или
// оставшиеся от старой версии данные не читаются, а заменяются значениями по
// умолчанию.
#pragma once

#include "config.h"

class Storage {
 public:
  void begin();

  void loadConfig(DeviceConfig &cfg);
  void saveConfig(const DeviceConfig &cfg);
  void saveCalibration(uint32_t empty_mm, uint32_t full_mm);

  void loadCredentials(Credentials &creds);
  void saveCredentials(const Credentials &creds);

  bool loadWifi(char *ssid, size_t ssidLen, char *pass, size_t passLen);
  void saveWifi(const char *ssid, const char *pass);
  void clearWifi();

  // Полный сброс пользовательских настроек. Учётные данные MQTT сохраняются,
  // иначе устройство пришлось бы заново готовить скриптом provision.py.
  void factoryReset();

 private:
  // Меняется структура — увеличьте STORAGE_VERSION, иначе прочитается мусор
  struct Data {
    uint32_t magic;
    uint16_t version;
    bool hasConfig;
    DeviceConfig cfg;
    Credentials creds;
    char ssid[33];
    char wifiPass[65];
    uint32_t crc;
  };

  void commit();
  static uint32_t checksum(const Data &data);

  Data data_;
};

extern Storage storage;
