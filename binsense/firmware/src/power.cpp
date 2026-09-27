#include "power.h"

#include <driver/rtc_io.h>
#include <esp_sleep.h>
#include <esp_system.h>

#include "indicator.h"

Power power;

void Power::begin() {
  pinMode(PIN_SENSOR_PWR, OUTPUT);
  sensorOff();
  pinMode(PIN_BUTTON, INPUT);  // подтяжка 10 кОм стоит на плате
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_BATTERY, ADC_11db);
}

// P-канальный MOSFET: низкий уровень на затворе открывает ключ.
void Power::sensorOn() { digitalWrite(PIN_SENSOR_PWR, LOW); }

void Power::sensorOff() { digitalWrite(PIN_SENSOR_PWR, HIGH); }

float Power::batteryVolts() {
  uint32_t sum = 0;
  const int samples = 16;
  for (int i = 0; i < samples; i++) {
    sum += analogReadMilliVolts(PIN_BATTERY);
    delay(2);
  }
  float millivolts = (float)sum / samples;
  return millivolts * BATTERY_DIVIDER / 1000.0f;
}

bool Power::buttonPressed() { return digitalRead(PIN_BUTTON) == LOW; }

const char *Power::resetReason() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON: return "POWERON";
    case ESP_RST_EXT: return "EXT";
    case ESP_RST_SW: return "SW";
    case ESP_RST_PANIC: return "PANIC";
    case ESP_RST_INT_WDT: return "INT_WDT";
    case ESP_RST_TASK_WDT: return "TASK_WDT";
    case ESP_RST_WDT: return "WDT";
    case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
    case ESP_RST_BROWNOUT: return "BROWNOUT";
    default: return "UNKNOWN";
  }
}

void Power::deepSleep(uint32_t seconds) {
  sensorOff();
  indicator.off();

  esp_sleep_enable_timer_wakeup((uint64_t)seconds * 1000000ULL);

  // Кнопка: просыпаемся по низкому уровню. Если её держат прямо сейчас,
  // источник не включаем — иначе устройство проснётся мгновенно.
  if (!buttonPressed()) {
    rtc_gpio_pullup_dis((gpio_num_t)PIN_BUTTON);
    rtc_gpio_pulldown_dis((gpio_num_t)PIN_BUTTON);
    esp_sleep_enable_ext0_wakeup((gpio_num_t)PIN_BUTTON, 0);
  }

  Serial.printf("[sleep] засыпаю на %u с\n", (unsigned)seconds);
  Serial.flush();
  esp_deep_sleep_start();
}
