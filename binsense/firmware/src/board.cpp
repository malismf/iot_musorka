#include "board.h"

#include <user_interface.h>

Board board;

// Подтяжка кнопки к питанию уже стоит на плате (GPIO0 — вывод загрузчика).
void Board::begin() { pinMode(PIN_BUTTON, INPUT_PULLUP); }

bool Board::buttonPressed() { return digitalRead(PIN_BUTTON) == LOW; }

// Названия совпадают с прошлой прошивкой на ESP32: по ним строится панель
// «Причины перезагрузок» в Grafana.
const char *Board::resetReason() {
  switch (ESP.getResetInfoPtr()->reason) {
    case REASON_DEFAULT_RST: return "POWERON";
    case REASON_WDT_RST: return "WDT";
    case REASON_EXCEPTION_RST: return "PANIC";
    case REASON_SOFT_WDT_RST: return "TASK_WDT";
    case REASON_SOFT_RESTART: return "SW";
    case REASON_DEEP_SLEEP_AWAKE: return "DEEPSLEEP";
    case REASON_EXT_SYS_RST: return "EXT";
    default: return "UNKNOWN";
  }
}

uint32_t Board::random32() { return ESP.random(); }

void Board::restart() {
  Serial.flush();
  ESP.restart();
}
