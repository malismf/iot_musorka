// Чистая логика измерений и расписания — без Arduino, чтобы её можно было
// проверить тестами на обычном компьютере (см. firmware/hosttest).
#pragma once

#include "config.h"

// Медиана массива (массив изменяется). Возвращает 0 для пустого массива.
int medianInt(int *values, int count);

// Разбор кадра UART-датчика (A02YYUW, JSN-SR04T в режиме UART):
// 0xFF, старший байт, младший байт, контрольная сумма.
// Возвращает true и расстояние в мм, если в буфере найден корректный кадр.
bool parseUartFrame(const uint8_t *data, int length, int &distance_mm, int *consumed = nullptr);

// Заполненность в процентах. Возвращает -1, если калибровки нет или данные неверные.
int fillPercent(int distance_mm, uint32_t empty_mm, uint32_t full_mm);

// Интервал до следующего замера с учётом заполненности и ночного режима.
uint32_t chooseIntervalS(const DeviceConfig &cfg, int fill, int localHour);

// Нужно ли отправлять данные на сервер прямо сейчас.
bool shouldSend(const DeviceConfig &cfg, int fill, int lastSentFill, uint32_t secondsSinceSend,
                bool interactive, bool firstAfterBoot, bool eventPending, bool sensorError);

// Датчика крышки нет, поэтому замер мог попасть на открытую крышку. Резкий скачок
// уровня (или сбой датчика) перепроверяется повторным замером через RECHECK_DELAY_S.
bool needsRecheck(int fill, int lastSentFill, bool sensorError);

// Проверка, попадает ли час в ночной интервал (start может быть больше end).
bool isNightHour(int hour, uint8_t start, uint8_t end);

// Удобная обёртка: заполненность по текущей калибровке устройства.
inline int fillPercentSafe(int distance_mm, const DeviceConfig &cfg) {
  return fillPercent(distance_mm, cfg.empty_mm, cfg.full_mm);
}
