// Заглушка SDK ESP8266: причины перезагрузки.
#pragma once

#include "Arduino.h"

enum rst_reason {
  REASON_DEFAULT_RST = 0,
  REASON_WDT_RST = 1,
  REASON_EXCEPTION_RST = 2,
  REASON_SOFT_WDT_RST = 3,
  REASON_SOFT_RESTART = 4,
  REASON_DEEP_SLEEP_AWAKE = 5,
  REASON_EXT_SYS_RST = 6,
};
