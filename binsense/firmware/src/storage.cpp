#include "storage.h"

#include <EEPROM.h>
#include <string.h>

Storage storage;

static const uint32_t STORAGE_MAGIC = 0xB1A5E8u;
static const uint16_t STORAGE_VERSION = 1;

static void copyText(char *target, size_t size, const char *source) {
  strncpy(target, source ? source : "", size - 1);
  target[size - 1] = '\0';
}

uint32_t Storage::checksum(const Data &data) {
  // CRC32 по всем байтам структуры, кроме самого поля crc
  const uint8_t *bytes = reinterpret_cast<const uint8_t *>(&data);
  size_t length = offsetof(Data, crc);
  uint32_t crc = 0xFFFFFFFFu;
  for (size_t i = 0; i < length; i++) {
    crc ^= bytes[i];
    for (int bit = 0; bit < 8; bit++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
  }
  return ~crc;
}

void Storage::begin() {
  EEPROM.begin(sizeof(Data));
  EEPROM.get(0, data_);
  if (data_.magic != STORAGE_MAGIC || data_.version != STORAGE_VERSION ||
      data_.crc != checksum(data_)) {
    memset(&data_, 0, sizeof(data_));
    data_.magic = STORAGE_MAGIC;
    data_.version = STORAGE_VERSION;
    data_.creds.port = MQTT_DEFAULT_PORT;
  }
}

void Storage::commit() {
  data_.crc = checksum(data_);
  EEPROM.put(0, data_);
  EEPROM.commit();
}

void Storage::loadConfig(DeviceConfig &cfg) {
  if (!data_.hasConfig) {
    configDefaults(cfg);
    return;
  }
  cfg = data_.cfg;
  if (cfg.samples > SENSOR_MAX_SAMPLES) cfg.samples = SENSOR_MAX_SAMPLES;
  if (cfg.samples == 0) cfg.samples = 1;
}

void Storage::saveConfig(const DeviceConfig &cfg) {
  data_.cfg = cfg;
  data_.hasConfig = true;
  commit();
}

void Storage::saveCalibration(uint32_t empty_mm, uint32_t full_mm) {
  if (!data_.hasConfig) configDefaults(data_.cfg);
  data_.cfg.empty_mm = empty_mm;
  data_.cfg.full_mm = full_mm;
  data_.hasConfig = true;
  commit();
}

void Storage::loadCredentials(Credentials &creds) {
  creds = data_.creds;
  creds.host[sizeof(creds.host) - 1] = '\0';
  creds.user[sizeof(creds.user) - 1] = '\0';
  creds.pass[sizeof(creds.pass) - 1] = '\0';
  if (creds.port == 0) creds.port = MQTT_DEFAULT_PORT;
  creds.provisioned = creds.host[0] != '\0' && creds.user[0] != '\0' && creds.pass[0] != '\0';
}

void Storage::saveCredentials(const Credentials &creds) {
  copyText(data_.creds.host, sizeof(data_.creds.host), creds.host);
  copyText(data_.creds.user, sizeof(data_.creds.user), creds.user);
  copyText(data_.creds.pass, sizeof(data_.creds.pass), creds.pass);
  data_.creds.port = creds.port;
  commit();
}

bool Storage::loadWifi(char *ssid, size_t ssidLen, char *pass, size_t passLen) {
  if (data_.ssid[0] == '\0') return false;
  copyText(ssid, ssidLen, data_.ssid);
  copyText(pass, passLen, data_.wifiPass);
  return true;
}

void Storage::saveWifi(const char *ssid, const char *pass) {
  copyText(data_.ssid, sizeof(data_.ssid), ssid);
  copyText(data_.wifiPass, sizeof(data_.wifiPass), pass);
  commit();
}

void Storage::clearWifi() {
  data_.ssid[0] = '\0';
  data_.wifiPass[0] = '\0';
  commit();
}

void Storage::factoryReset() {
  Credentials creds = data_.creds;
  memset(&data_, 0, sizeof(data_));
  data_.magic = STORAGE_MAGIC;
  data_.version = STORAGE_VERSION;
  data_.creds = creds;  // учётку MQTT не теряем — она выдана при подготовке
  commit();
}
