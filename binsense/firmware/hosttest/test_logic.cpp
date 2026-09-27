// Тесты логики прошивки, которые можно запускать на обычном компьютере:
//     cd firmware/hosttest && ./run.sh
//
// Проверяются медиана, разбор кадров UART-датчика, расчёт заполненности,
// выбор интервала замеров, правило отправки, повторный замер и собственный разбор JSON.
#include <cstdio>
#include <cstring>

#include "json_lite.h"
#include "measure.h"

static int failed = 0;
static int total = 0;

#define CHECK(condition, description)                                  \
  do {                                                                 \
    total++;                                                           \
    if (!(condition)) {                                                \
      failed++;                                                        \
      printf("  ПРОВАЛ: %s (строка %d)\n", description, __LINE__);     \
    }                                                                  \
  } while (0)

#define CHECK_EQ(actual, expected, description)                                        \
  do {                                                                                 \
    total++;                                                                           \
    long a = (long)(actual);                                                           \
    long e = (long)(expected);                                                         \
    if (a != e) {                                                                      \
      failed++;                                                                        \
      printf("  ПРОВАЛ: %s — получено %ld, ожидалось %ld (строка %d)\n", description,  \
             a, e, __LINE__);                                                          \
    }                                                                                  \
  } while (0)

static void testMedian() {
  int odd[] = {980, 120, 1000, 990, 985};
  CHECK_EQ(medianInt(odd, 5), 985, "медиана нечётного количества отбрасывает выброс");
  int even[] = {100, 200, 300, 400};
  CHECK_EQ(medianInt(even, 4), 250, "медиана чётного количества");
  int single[] = {777};
  CHECK_EQ(medianInt(single, 1), 777, "медиана одного значения");
  CHECK_EQ(medianInt(nullptr, 0), 0, "пустой массив");
}

static void testFrames() {
  // 0xFF, старший, младший, контрольная сумма; 0x03D4 = 980 мм
  uint8_t good[] = {0xFF, 0x03, 0xD4, 0xD6};
  int distance = 0;
  CHECK(parseUartFrame(good, 4, distance), "корректный кадр распознан");
  CHECK_EQ(distance, 980, "расстояние из кадра");

  uint8_t noisy[] = {0x12, 0x34, 0xFF, 0x03, 0xD4, 0xD6};
  distance = 0;
  CHECK(parseUartFrame(noisy, 6, distance), "кадр найден среди мусора");
  CHECK_EQ(distance, 980, "расстояние из зашумлённого потока");

  uint8_t badSum[] = {0xFF, 0x03, 0xD4, 0x00};
  CHECK(!parseUartFrame(badSum, 4, distance), "кадр с неверной суммой отброшен");

  uint8_t tooShort[] = {0xFF, 0x03};
  CHECK(!parseUartFrame(tooShort, 2, distance), "неполный кадр отброшен");
}

static void testFill() {
  CHECK_EQ(fillPercent(980, 980, 250), 0, "пустой контейнер — 0 %");
  CHECK_EQ(fillPercent(250, 980, 250), 100, "мусор у самой крышки — 100 %");
  CHECK_EQ(fillPercent(615, 980, 250), 50, "середина контейнера");
  CHECK_EQ(fillPercent(200, 980, 250), 100, "ближе порога — не больше 100 %");
  CHECK_EQ(fillPercent(1200, 980, 250), 0, "дальше дна — не меньше 0 %");
  CHECK_EQ(fillPercent(500, 0, 250), -1, "без калибровки заполненность неизвестна");
  CHECK_EQ(fillPercent(500, 200, 250), -1, "некорректная калибровка");
}

static void testNightAndInterval() {
  CHECK(isNightHour(2, 23, 7), "2 часа ночи попадает в интервал 23–7");
  CHECK(isNightHour(23, 23, 7), "23 часа — начало ночи");
  CHECK(!isNightHour(12, 23, 7), "полдень — не ночь");
  CHECK(!isNightHour(-1, 23, 7), "время неизвестно — считаем, что не ночь");
  CHECK(isNightHour(1, 0, 6), "интервал без перехода через полночь");

  DeviceConfig cfg;
  configDefaults(cfg);
  CHECK_EQ(chooseIntervalS(cfg, 30, 12), DEFAULT_INTERVAL_S, "обычный интервал днём");
  CHECK_EQ(chooseIntervalS(cfg, 30, 2), DEFAULT_NIGHT_INTERVAL_S, "ночью реже");
  CHECK_EQ(chooseIntervalS(cfg, 95, 2), DEFAULT_FULL_INTERVAL_S,
           "заполненный контейнер важнее ночного режима");
  CHECK_EQ(chooseIntervalS(cfg, -1, 12), DEFAULT_INTERVAL_S,
           "без калибровки работаем по обычному интервалу");
  cfg.interval_s = 3;
  CHECK_EQ(chooseIntervalS(cfg, 30, 12), 10, "интервал не меньше 10 секунд");
}

static void testShouldSend() {
  DeviceConfig cfg;
  configDefaults(cfg);
  CHECK(shouldSend(cfg, 40, 40, 10, true, false, false, false), "нажатие кнопки — отправляем");
  CHECK(shouldSend(cfg, 40, 40, 10, false, true, false, false), "первый замер после включения");
  CHECK(shouldSend(cfg, 40, 40, 10, false, false, true, false), "есть событие в очереди");
  CHECK(shouldSend(cfg, 40, 40, 10, false, false, false, true), "ошибка датчика");
  CHECK(shouldSend(cfg, 44, 40, 10, false, false, false, false), "уровень изменился на 4 %");
  CHECK(!shouldSend(cfg, 41, 40, 10, false, false, false, false), "изменение меньше порога");
  CHECK(shouldSend(cfg, 41, 40, cfg.heartbeat_s, false, false, false, false),
        "по heartbeat отправляем в любом случае");
  CHECK(!shouldSend(cfg, -1, 40, 10, false, false, false, false),
        "без измерения молчим (если нет других причин)");
  CHECK(shouldSend(cfg, 20, -1, 10, false, false, false, false), "первое измерение после привязки");
}

static void testRecheck() {
  CHECK(needsRecheck(5, 85, false), "уровень упал с 85 до 5 % — перемерить (открыта крышка?)");
  CHECK(needsRecheck(100, 40, false), "скачок вверх тоже перепроверяется");
  CHECK(!needsRecheck(44, 40, false), "обычное изменение отправляется сразу");
  CHECK(!needsRecheck(40 + RECHECK_DELTA_PCT - 1, 40, false), "чуть меньше порога — без повтора");
  CHECK(needsRecheck(-1, 40, true), "сбой датчика перепроверяется до отправки ошибки");
  CHECK(!needsRecheck(90, -1, false), "первый замер сравнивать не с чем");
  CHECK(!needsRecheck(-1, 40, false), "без калибровки скачков не бывает");
}

static void testJsonReader() {
  const char *config =
      "{\"ver\":7,\"claimed\":true,\"interval_s\":900,\"night\":[23,7],\"tz\":\"MSK-3\","
      "\"full_pct\":80,\"empty_mm\":982,\"name\":\"Площадка \\\"1\\\"\"}";
  long number = 0;
  bool flag = false;
  char text[40];

  CHECK(json::getInt(config, "ver", number) && number == 7, "чтение целого");
  CHECK(json::getBool(config, "claimed", flag) && flag, "чтение логического значения");
  CHECK(json::getInt(config, "empty_mm", number) && number == 982, "чтение калибровки");
  CHECK(json::getString(config, "tz", text, sizeof(text)) && strcmp(text, "MSK-3") == 0,
        "чтение строки");
  long night[2] = {0, 0};
  CHECK(json::getIntArray(config, "night", night, 2) == 2 && night[0] == 23 && night[1] == 7,
        "чтение массива");
  CHECK(!json::getInt(config, "missing", number), "отсутствующий ключ");
  CHECK(json::getString(config, "name", text, sizeof(text)), "строка с экранированием");

  const char *prov = "{\"host\":\"bins.example.com\",\"port\":1883,\"user\":\"bin-a1\"}";
  CHECK(json::getString(prov, "host", text, sizeof(text)) &&
            strcmp(text, "bins.example.com") == 0,
        "разбор команды prov");
  CHECK(json::getInt(prov, "port", number) && number == 1883, "порт из команды prov");
}

static void testJsonWriter() {
  char buffer[256];
  json::Writer writer(buffer, sizeof(buffer));
  writer.begin();
  writer.addUInt("seq", 42);
  writer.addInt("fill", 73);
  writer.addFloat("bat_v", 3.91f, 2);
  writer.addString("wake", "timer");
  writer.addBool("ok", true);
  writer.end();
  CHECK(writer.ok(), "буфер не переполнен");
  CHECK(strcmp(buffer, "{\"seq\":42,\"fill\":73,\"bat_v\":3.91,\"wake\":\"timer\",\"ok\":true}") == 0,
        "собранный JSON совпадает с ожидаемым");

  // проверяем, что переполнение не портит память
  char small[16];
  json::Writer tight(small, sizeof(small));
  tight.begin();
  tight.addString("key", "очень длинное значение");
  tight.end();
  CHECK(!tight.ok(), "переполнение замечено");
  CHECK(strlen(small) < sizeof(small), "строка осталась корректной");

  // и что записанное читается обратно
  json::Writer roundtrip(buffer, sizeof(buffer));
  roundtrip.begin();
  roundtrip.addInt("dist_mm", 615);
  roundtrip.addString("type", "calibrated");
  roundtrip.end();
  long value = 0;
  char text[20];
  CHECK(json::getInt(buffer, "dist_mm", value) && value == 615, "число читается обратно");
  CHECK(json::getString(buffer, "type", text, sizeof(text)) && strcmp(text, "calibrated") == 0,
        "строка читается обратно");
}

int main() {
  printf("Тесты логики прошивки BinSense\n");
  testMedian();
  testFrames();
  testFill();
  testNightAndInterval();
  testShouldSend();
  testRecheck();
  testJsonReader();
  testJsonWriter();
  printf("%s: проверок %d, провалов %d\n", failed == 0 ? "УСПЕХ" : "ОШИБКИ", total, failed);
  return failed == 0 ? 0 : 1;
}
