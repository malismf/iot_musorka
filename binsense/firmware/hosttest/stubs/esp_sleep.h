#pragma once

#include <cstdint>

typedef int gpio_num_t;
typedef int esp_err_t;

typedef enum {
  ESP_SLEEP_WAKEUP_UNDEFINED,
  ESP_SLEEP_WAKEUP_ALL,
  ESP_SLEEP_WAKEUP_EXT0,
  ESP_SLEEP_WAKEUP_EXT1,
  ESP_SLEEP_WAKEUP_TIMER,
  ESP_SLEEP_WAKEUP_TOUCHPAD,
  ESP_SLEEP_WAKEUP_ULP,
} esp_sleep_wakeup_cause_t;

typedef enum {
  ESP_EXT1_WAKEUP_ALL_LOW = 0,
  ESP_EXT1_WAKEUP_ANY_HIGH = 1,
} esp_sleep_ext1_wakeup_mode_t;

esp_err_t esp_sleep_enable_timer_wakeup(uint64_t time_in_us);
esp_err_t esp_sleep_enable_ext0_wakeup(gpio_num_t pin, int level);
esp_err_t esp_sleep_enable_ext1_wakeup(uint64_t mask, esp_sleep_ext1_wakeup_mode_t mode);
esp_sleep_wakeup_cause_t esp_sleep_get_wakeup_cause();
void esp_deep_sleep_start();
