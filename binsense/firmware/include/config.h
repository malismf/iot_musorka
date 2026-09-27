// Настройки прошивки BinSense: пины, константы, структуры данных.
// Любой параметр можно переопределить в platformio.ini через -D.
//
// Плата — ESP8266 (NodeMCU / Wemos D1 mini), питание от USB. Номера пинов —
// GPIO; в скобках подпись на плате.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define FW_VERSION "2.0.0"

#ifndef HW_NAME
#define HW_NAME "esp8266"
#endif

// --- Пины --------------------------------------------------------------------
#ifndef PIN_SENSOR_RX
#define PIN_SENSOR_RX 14   // (D5) TX ультразвукового датчика -> программный UART
#endif
#ifndef PIN_SENSOR_TX
#define PIN_SENSOR_TX 12   // (D6) RX датчика (A02YYUW: высокий уровень = усреднённые данные)
#endif
#ifndef PIN_TRIG
#define PIN_TRIG 14        // (D5) только для HC-SR04
#endif
#ifndef PIN_ECHO
#define PIN_ECHO 12        // (D6) только для HC-SR04, через делитель 1 кОм / 2 кОм
#endif
#ifndef PIN_BUTTON
#define PIN_BUTTON 0       // (D3) кнопка FLASH на NodeMCU, подтяжка к 3.3 В уже на плате
#endif
#ifndef PIN_LED_R
#define PIN_LED_R 5        // (D1)
#endif
#ifndef PIN_LED_G
#define PIN_LED_G 4        // (D2)
#endif
#ifndef PIN_LED_B
#define PIN_LED_B 13       // (D7)
#endif
#ifndef PIN_BUZZER
#define PIN_BUZZER 15      // (D8) активный зуммер через NPN; на плате подтяжка к земле
#endif

// --- Датчик ------------------------------------------------------------------
#ifndef SENSOR_MIN_MM
#define SENSOR_MIN_MM 30      // ближе — мёртвая зона (A02YYUW: 30 мм, JSN-SR04T: 250 мм)
#endif
#ifndef SENSOR_MAX_MM
#define SENSOR_MAX_MM 4500
#endif
#ifndef SENSOR_UART_BAUD
#define SENSOR_UART_BAUD 9600
#endif
#ifndef SENSOR_SAMPLE_TIMEOUT_MS
#define SENSOR_SAMPLE_TIMEOUT_MS 250
#endif
#define SENSOR_MAX_SAMPLES 15

// --- Поведение ---------------------------------------------------------------
#define CONSOLE_WINDOW_MS 3000       // сколько ждём команду в консоли после включения
#define CONSOLE_IDLE_MS 120000       // консоль после первой команды ждёт следующую
#define CALIBRATION_DELAY_MS 5000    // пауза перед калибровкой: убрать руку, закрыть крышку
#define RECHECK_DELTA_PCT 20         // скачок уровня, после которого замер повторяется
#define RECHECK_DELAY_S 60           // через сколько повторить (крышку успеют закрыть)
#define CLAIM_BLINK_MS 1200          // мигание бирюзовым, пока устройство не привязано
#define WIFI_TIMEOUT_MS 15000
#define WIFI_RETRY_MS 30000          // пауза между попытками подключиться к Wi-Fi
#define MQTT_TIMEOUT_MS 6000
#define MQTT_RETRY_MS 10000          // пауза между попытками подключиться к брокеру
#define PORTAL_TIMEOUT_S 600         // портал настройки Wi-Fi
#define BUTTON_DEBOUNCE_MS 50
#define BUTTON_CAL_MS 3000           // удержание кнопки: калибровка
#define BUTTON_RESET_MS 10000        // удержание кнопки: сброс настроек

// --- Значения по умолчанию (до получения настроек с сервера) -----------------
#define DEFAULT_INTERVAL_S 900
#define DEFAULT_HEARTBEAT_S 7200
#define DEFAULT_FULL_INTERVAL_S 300
#define DEFAULT_FULL_PCT 80
#define DEFAULT_DELTA_PCT 3
#define DEFAULT_SAMPLES 7
#ifndef DEFAULT_FULL_MM
#define DEFAULT_FULL_MM 250
#endif

#ifndef MQTT_DEFAULT_PORT
#define MQTT_DEFAULT_PORT 1883
#endif

// --- Структуры ---------------------------------------------------------------
struct DeviceConfig {
  uint32_t version;
  bool claimed;
  uint32_t interval_s;
  uint32_t heartbeat_s;
  uint32_t full_interval_s;
  uint8_t reserved1[6];  // место убранного ночного режима: раскладка флеша не меняется
  uint8_t full_pct;
  uint8_t delta_pct;
  uint8_t samples;
  uint32_t empty_mm;  // расстояние до дна пустого контейнера (калибровка)
  uint32_t full_mm;   // расстояние, считающееся 100 %
  char reserved2[40];    // место убранного часового пояса
};
// Иначе после перепрошивки Storage не узнает старые данные и сотрёт учётку MQTT
static_assert(offsetof(DeviceConfig, full_pct) == 26 && offsetof(DeviceConfig, empty_mm) == 32 &&
                  sizeof(DeviceConfig) == 80,
              "раскладка DeviceConfig должна совпадать с записанной во флеш");

struct Credentials {
  char host[64];
  uint16_t port;
  char user[40];
  char pass[40];
  bool provisioned;
};

struct Measurement {
  bool ok;
  int dist_mm;
  int samples_ok;
  int fill;  // -1, если устройство не откалибровано
  const char *error;
};

inline void configDefaults(DeviceConfig &cfg) {
  cfg.version = 0;
  cfg.claimed = false;
  cfg.interval_s = DEFAULT_INTERVAL_S;
  cfg.heartbeat_s = DEFAULT_HEARTBEAT_S;
  cfg.full_interval_s = DEFAULT_FULL_INTERVAL_S;
  for (size_t i = 0; i < sizeof(cfg.reserved1); i++) cfg.reserved1[i] = 0;
  cfg.full_pct = DEFAULT_FULL_PCT;
  cfg.delta_pct = DEFAULT_DELTA_PCT;
  cfg.samples = DEFAULT_SAMPLES;
  cfg.empty_mm = 0;
  cfg.full_mm = DEFAULT_FULL_MM;
  for (size_t i = 0; i < sizeof(cfg.reserved2); i++) cfg.reserved2[i] = 0;
}
