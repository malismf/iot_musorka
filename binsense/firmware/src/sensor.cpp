#include "sensor.h"

#ifndef SENSOR_PULSE
#include <SoftwareSerial.h>
#endif

#include "measure.h"

Sensor sensor;

#ifndef SENSOR_PULSE
static SoftwareSerial sensorSerial(PIN_SENSOR_RX, PIN_SENSOR_TX);
#endif

void Sensor::begin() {
#ifdef SENSOR_PULSE
  pinMode(PIN_TRIG, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);
  pinMode(PIN_ECHO, INPUT);
#else
  // Высокий уровень на RX датчика (TX программного UART в покое) включает у
  // A02YYUW режим усреднённых данных.
  sensorSerial.begin(SENSOR_UART_BAUD);
  uart_ = &sensorSerial;
#endif
}

#ifndef SENSOR_PULSE
// Датчик питается постоянно и сам шлёт кадры: перед замером выбрасываем
// накопившиеся в буфере, иначе медиана посчиталась бы по старым данным.
void Sensor::flushInput() {
  while (uart_->available()) uart_->read();
}
#endif

int Sensor::readOnce() {
#ifdef SENSOR_PULSE
  // HC-SR04: импульс 10 мкс на Trig, длительность Echo пропорциональна расстоянию.
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(4);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long duration = pulseIn(PIN_ECHO, HIGH, 30000UL);
  if (duration == 0) return -1;
  // 343 м/с при 20 °C: расстояние = длительность / 2 * 0.343 мм/мкс
  return (int)(duration * 343L / 2000L);
#else
  if (uart_ == nullptr) return -1;
  uint8_t buffer[32];
  int length = 0;
  uint32_t deadline = millis() + SENSOR_SAMPLE_TIMEOUT_MS;
  while (millis() < deadline && length < (int)sizeof(buffer)) {
    while (uart_->available() && length < (int)sizeof(buffer)) {
      buffer[length++] = (uint8_t)uart_->read();
    }
    int distance = 0;
    if (parseUartFrame(buffer, length, distance)) return distance;
    delay(5);
  }
  return -1;
#endif
}

Measurement Sensor::read(uint8_t samples, const DeviceConfig &cfg) {
  Measurement result;
  result.ok = false;
  result.dist_mm = 0;
  result.samples_ok = 0;
  result.fill = -1;
  result.error = nullptr;

  if (samples == 0) samples = 1;
  if (samples > SENSOR_MAX_SAMPLES) samples = SENSOR_MAX_SAMPLES;

  int values[SENSOR_MAX_SAMPLES];
  int count = 0;
  int attempts = samples * 2;  // запас на случай сбойных кадров
#ifndef SENSOR_PULSE
  if (uart_ == nullptr) begin();
  flushInput();
#endif

  for (int i = 0; i < attempts && count < samples; i++) {
    int distance = readOnce();
    if (distance >= SENSOR_MIN_MM && distance <= SENSOR_MAX_MM) {
      values[count++] = distance;
    }
    delay(60);
  }

  result.samples_ok = count;
  if (count == 0) {
    result.error = "SENSOR_TIMEOUT";
    return result;
  }
  if (count < samples / 2 + 1) {
    // часть кадров потерялась — данные считаем ненадёжными
    result.error = "SENSOR_UNSTABLE";
  }

  result.dist_mm = medianInt(values, count);
  result.fill = fillPercent(result.dist_mm, cfg.empty_mm, cfg.full_mm);
  result.ok = result.error == nullptr;
  return result;
}
