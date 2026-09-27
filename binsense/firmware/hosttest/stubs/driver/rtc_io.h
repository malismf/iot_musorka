#pragma once

#include "../esp_sleep.h"

int rtc_gpio_pullup_dis(gpio_num_t pin);
int rtc_gpio_pulldown_dis(gpio_num_t pin);
