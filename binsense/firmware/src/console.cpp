#include "console.h"

#include "indicator.h"
#include "json_lite.h"
#include "measure.h"
#include "netlink.h"
#include "board.h"
#include "sensor.h"
#include "storage.h"

Console console;

void Console::banner(const DeviceConfig &cfg, const Credentials &creds) {
  Serial.println();
  Serial.println("=== BINSENSE CONSOLE ===");
  Serial.printf("id=%s fw=%s hw=%s provisioned=%d claimed=%d\n", deviceId(), FW_VERSION, HW_NAME,
                creds.provisioned ? 1 : 0, cfg.claimed ? 1 : 0);
  Serial.println("введите help для списка команд");
}

void Console::help() {
  Serial.println(F("команды:"));
  Serial.println(F("  info              — сведения об устройстве (JSON)"));
  Serial.println(F("  prov {json}       — записать настройки сервера (host, port, user, pass)"));
  Serial.println(F("  measure [n]       — n замеров расстояния"));
  Serial.println(F("  button            — состояние кнопки"));
  Serial.println(F("  led r g b         — задать цвет светодиода (0..255)"));
  Serial.println(F("  beep [n]          — пискнуть"));
  Serial.println(F("  cal               — калибровка пустого контейнера"));
  Serial.println(F("  send              — измерить и отправить данные на сервер"));
  Serial.println(F("  wifi portal|clear — настройка или сброс Wi-Fi"));
  Serial.println(F("  factory           — сброс настроек (учётка MQTT сохраняется)"));
  Serial.println(F("  reboot            — перезагрузить устройство"));
  Serial.println(F("  exit              — выйти из окна консоли после включения"));
}

void Console::printInfo(const DeviceConfig &cfg, const Credentials &creds) {
  char buffer[420];
  json::Writer writer(buffer, sizeof(buffer));
  char ssid[33] = {0};
  char pass[65] = {0};
  bool hasWifi = storage.loadWifi(ssid, sizeof(ssid), pass, sizeof(pass));

  writer.begin();
  writer.addString("id", deviceId());
  writer.addString("fw", FW_VERSION);
  writer.addString("hw", HW_NAME);
  writer.addBool("prov", creds.provisioned);
  writer.addBool("claimed", cfg.claimed);
  writer.addString("host", creds.host);
  writer.addInt("port", creds.port);
  writer.addString("user", creds.user);
  writer.addString("wifi", hasWifi ? ssid : "");
  writer.addInt("cfg_ver", (long)cfg.version);
  writer.addInt("empty_mm", (long)cfg.empty_mm);
  writer.addInt("full_mm", (long)cfg.full_mm);
  writer.end();
  Serial.println(writer.c_str());
}

bool Console::handle(String line, DeviceConfig &cfg, Credentials &creds) {
  line.trim();
  if (line.length() == 0) return true;

  if (line == "help" || line == "?") {
    help();
  } else if (line == "info") {
    printInfo(cfg, creds);
  } else if (line.startsWith("prov")) {
    int brace = line.indexOf('{');
    if (brace < 0) {
      Serial.println("ERR нужен JSON: prov {\"host\":\"...\",\"port\":1883,...}");
      return true;
    }
    String payload = line.substring(brace);
    char text[80];
    long number = 0;
    Credentials updated = creds;
    if (json::getString(payload.c_str(), "host", text, sizeof(text))) {
      strncpy(updated.host, text, sizeof(updated.host) - 1);
      updated.host[sizeof(updated.host) - 1] = '\0';
    }
    if (json::getInt(payload.c_str(), "port", number)) updated.port = (uint16_t)number;
    if (json::getString(payload.c_str(), "user", text, sizeof(text))) {
      strncpy(updated.user, text, sizeof(updated.user) - 1);
      updated.user[sizeof(updated.user) - 1] = '\0';
    }
    if (json::getString(payload.c_str(), "pass", text, sizeof(text))) {
      strncpy(updated.pass, text, sizeof(updated.pass) - 1);
      updated.pass[sizeof(updated.pass) - 1] = '\0';
    }
    if (updated.host[0] == '\0' || updated.user[0] == '\0' || updated.pass[0] == '\0') {
      Serial.println("ERR не хватает host/user/pass");
      return true;
    }
    if (updated.port == 0) updated.port = MQTT_DEFAULT_PORT;
    updated.provisioned = true;
    storage.saveCredentials(updated);
    creds = updated;
    indicator.blink(colors::GREEN, 2, 120, 120);
    Serial.println("OK prov");
  } else if (line.startsWith("measure")) {
    int count = 5;
    int space = line.indexOf(' ');
    if (space > 0) count = constrain(line.substring(space + 1).toInt(), 1, SENSOR_MAX_SAMPLES);
    for (int i = 0; i < count; i++) {
      int distance = sensor.readOnce();
      int fill = fillPercentSafe(distance, cfg);
      Serial.printf("  %2d: %5d мм  fill=%d%%\n", i + 1, distance, fill);
      delay(80);
    }
    Serial.println("OK measure");
  } else if (line == "button") {
    Serial.printf("OK кнопка %s\n", board.buttonPressed() ? "нажата" : "отпущена");
  } else if (line.startsWith("led")) {
    int r = 0, g = 0, b = 0;
    if (sscanf(line.c_str(), "led %d %d %d", &r, &g, &b) == 3) {
      Color color = {(uint8_t)r, (uint8_t)g, (uint8_t)b};
      indicator.set(color);
      Serial.println("OK led");
    } else {
      Serial.println("ERR формат: led 255 0 0");
    }
  } else if (line.startsWith("beep")) {
    int space = line.indexOf(' ');
    int count = space > 0 ? line.substring(space + 1).toInt() : 1;
    indicator.beep(constrain(count, 1, 5));
    Serial.println("OK beep");
  } else if (line == "cal") {
    if (calibrate_ && calibrate_()) Serial.println("OK cal");
    else Serial.println("ERR калибровка не удалась");
  } else if (line == "send") {
    if (sendNow_ && sendNow_()) Serial.println("OK send");
    else Serial.println("ERR отправка не удалась");
  } else if (line.startsWith("wifi")) {
    if (line.indexOf("clear") > 0) {
      storage.clearWifi();
      Serial.println("OK настройки Wi-Fi удалены, после перезагрузки откроется портал");
    } else {
      Serial.println("запускаю портал настройки…");
      bool ok = net.startPortal(PORTAL_TIMEOUT_S);
      Serial.println(ok ? "OK wifi, перезагружаюсь" : "ERR портал завершён без подключения");
      if (ok) board.restart();  // подключиться уже с новыми данными
    }
  } else if (line == "factory") {
    storage.factoryReset();
    Serial.println("OK сброшено, перезагрузите устройство");
  } else if (line == "reboot") {
    Serial.println("OK reboot");
    board.restart();
  } else if (line == "exit" || line == "quit") {
    Serial.println("OK exit");
    return false;
  } else {
    Serial.println("ERR неизвестная команда, см. help");
  }
  return true;
}

void Console::run(uint32_t windowMs, DeviceConfig &cfg, Credentials &creds) {
  banner(cfg, creds);
  uint32_t deadline = millis() + windowMs;
  String buffer;
  bool active = false;

  while (millis() < deadline) {
    while (Serial.available()) {
      char symbol = (char)Serial.read();
      if (symbol == '\r') continue;
      if (symbol == '\n') {
        active = true;
        if (!handle(buffer, cfg, creds)) return;
        buffer = "";
        deadline = millis() + CONSOLE_IDLE_MS;  // после команды ждём дольше
      } else if (buffer.length() < 400) {
        buffer += symbol;
      }
    }
    indicator.tick();
    delay(10);
  }
  if (active) Serial.println("консоль закрыта по таймауту");
}

void Console::poll(DeviceConfig &cfg, Credentials &creds) {
  while (Serial.available()) {
    char symbol = (char)Serial.read();
    if (symbol == '\r') continue;
    if (symbol == '\n') {
      handle(buffer_, cfg, creds);
      buffer_ = "";
    } else if (buffer_.length() < 400) {
      buffer_ += symbol;
    }
  }
}
