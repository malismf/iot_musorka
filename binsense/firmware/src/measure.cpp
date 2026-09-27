#include "measure.h"

#include <stdlib.h>

static int compareInt(const void *a, const void *b) {
  int left = *(const int *)a;
  int right = *(const int *)b;
  return (left > right) - (left < right);
}

int medianInt(int *values, int count) {
  if (count <= 0) return 0;
  qsort(values, (size_t)count, sizeof(int), compareInt);
  if (count % 2 == 1) return values[count / 2];
  return (values[count / 2 - 1] + values[count / 2]) / 2;
}

bool parseUartFrame(const uint8_t *data, int length, int &distance_mm, int *consumed) {
  for (int i = 0; i + 3 < length; i++) {
    if (data[i] != 0xFF) continue;
    uint8_t high = data[i + 1];
    uint8_t low = data[i + 2];
    uint8_t checksum = data[i + 3];
    if ((uint8_t)((0xFF + high + low) & 0xFF) != checksum) continue;
    distance_mm = (high << 8) | low;
    if (consumed) *consumed = i + 4;
    return true;
  }
  if (consumed) *consumed = length > 3 ? length - 3 : 0;
  return false;
}

int fillPercent(int distance_mm, uint32_t empty_mm, uint32_t full_mm) {
  if (empty_mm == 0 || distance_mm <= 0) return -1;
  if (empty_mm <= full_mm) return -1;  // калибровка некорректна
  long span = (long)empty_mm - (long)full_mm;
  long value = ((long)empty_mm - distance_mm) * 100 / span;
  if (value < 0) value = 0;
  if (value > 100) value = 100;
  return (int)value;
}

uint32_t chooseIntervalS(const DeviceConfig &cfg, int fill) {
  uint32_t interval = cfg.interval_s;
  if (fill >= 0 && fill >= cfg.full_pct) interval = cfg.full_interval_s;
  if (interval < 10) interval = 10;
  if (interval > 24 * 3600) interval = 24 * 3600;
  return interval;
}

bool needsRecheck(int fill, int lastSentFill, bool sensorError) {
  if (sensorError) return true;
  if (fill < 0 || lastSentFill < 0) return false;
  int delta = fill - lastSentFill;
  if (delta < 0) delta = -delta;
  return delta >= RECHECK_DELTA_PCT;
}

bool shouldSend(const DeviceConfig &cfg, int fill, int lastSentFill, uint32_t secondsSinceSend,
                bool interactive, bool firstAfterBoot, bool eventPending, bool sensorError) {
  if (interactive || firstAfterBoot || eventPending || sensorError) return true;
  if (secondsSinceSend >= cfg.heartbeat_s) return true;
  if (fill < 0) return false;
  if (lastSentFill < 0) return true;
  int delta = fill - lastSentFill;
  if (delta < 0) delta = -delta;
  return delta >= (int)cfg.delta_pct;
}
