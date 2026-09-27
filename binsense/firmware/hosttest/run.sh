#!/usr/bin/env bash
# Проверка прошивки без железа:
#   1) тесты чистой логики (медиана, кадры датчика, заполненность, JSON);
#   2) пробная сборка всех файлов прошивки с заглушками Arduino/ESP8266 —
#      ловит ошибки компиляции, пока плата ещё едет с AliExpress.
#
# Запуск:  cd firmware/hosttest && ./run.sh
set -euo pipefail

cd "$(dirname "$0")"
ROOT=..
BUILD=build
mkdir -p $BUILD
CXX="${CXX:-g++}"
CXXFLAGS="-std=c++17 -Wall -Wextra -Wno-unused-parameter -I stubs -I $ROOT/include -I $ROOT/src"

echo "== Тесты логики"
"$CXX" $CXXFLAGS test_logic.cpp $ROOT/src/measure.cpp $ROOT/src/json_lite.cpp -o $BUILD/test_logic
$BUILD/test_logic

echo
echo "== Пробная сборка прошивки с заглушками"
for file in $ROOT/src/*.cpp stubs/stubs.cpp; do
  printf '  %-24s' "$(basename "$file")"
  "$CXX" $CXXFLAGS -c "$file" -o "$BUILD/$(basename "${file%.cpp}").o"
  echo "ok"
done

echo
echo "== Пробная сборка варианта для прототипа (HC-SR04, -DSENSOR_PULSE)"
for file in $ROOT/src/*.cpp; do
  printf '  %-24s' "$(basename "$file")"
  "$CXX" $CXXFLAGS -DSENSOR_PULSE -c "$file" -o "$BUILD/proto_$(basename "${file%.cpp}").o"
  echo "ok"
done
echo
echo "ГОТОВО"
