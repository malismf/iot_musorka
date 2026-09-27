"""Консоль прошивки BinSense без мусора при подключении.

    python tools/console.py COM10            # подключиться, не перезагружая плату
    python tools/console.py COM10 --reset    # подключиться и перезагрузить плату

Драйвер FTDI 2.12 с неоригинальным FT232 (так у части плат D1 mini), пока порт
закрыт, копит копии последней строки и выдаёт их разом при открытии —
мегабайты за минуту. Монитор PlatformIO их показывает, этот скрипт сбрасывает.
Команды вводятся как обычно (help, info, measure 5, cal, send…), выход — Ctrl+C.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time

try:
    import serial
except ImportError:  # pragma: no cover
    raise SystemExit("Нужен пакет pyserial: pip install pyserial")


def drain(ser: serial.Serial, quiet_s: float = 0.3, limit_s: float = 60.0) -> int:
    """Выбрасывает накопленное драйвером: читает, пока в порту не станет тихо."""
    ser.reset_input_buffer()
    dropped = 0
    last_data = time.time()
    started = time.time()
    while time.time() - last_data < quiet_s and time.time() - started < limit_s:
        chunk = ser.read(65536)
        if chunk:
            dropped += len(chunk)
            last_data = time.time()
    return dropped


def reader(ser: serial.Serial, stop: threading.Event) -> None:
    pending = b""
    while not stop.is_set():
        try:
            chunk = ser.read(1024)
        except serial.SerialException as exc:
            print(f"== порт закрыт: {exc}", flush=True)
            stop.set()
            return
        if not chunk:
            continue
        pending += chunk
        *lines, pending = pending.split(b"\n")
        for line in lines:
            text = line.decode("utf-8", "replace").rstrip("\r")
            print(f"{time.strftime('%H:%M:%S')} > {text}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Консоль прошивки BinSense")
    parser.add_argument("port", help="последовательный порт, например COM10")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--reset", action="store_true", help="перезагрузить плату при подключении")
    args = parser.parse_args()
    # вывод в файл или конвейер не должен падать на кириллице
    sys.stdout.reconfigure(errors="replace")

    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = args.port, args.baud, 0.05
    ser.dtr = ser.rts = False  # иначе открытие порта перезагрузит плату
    try:
        ser.open()
    except serial.SerialException as exc:
        raise SystemExit(f"Не открыть {args.port}: {exc} (порт занят другим монитором?)")
    dropped = drain(ser)
    if dropped:
        print(f"== пропущено {dropped // 1024} КБ, накопленных драйвером", flush=True)
    ser.timeout = 0.2
    if args.reset:
        ser.rts = True
        time.sleep(0.15)
        ser.rts = False
    print(f"== {args.port}, {args.baud} бод. Команды: help, info, cal, send. Выход — Ctrl+C",
          flush=True)

    stop = threading.Event()
    threading.Thread(target=reader, args=(ser, stop), daemon=True).start()
    try:
        for line in sys.stdin:
            if stop.is_set():
                break
            ser.write(line.rstrip("\r\n").encode("utf-8") + b"\n")
    except KeyboardInterrupt:
        pass
    finally:
        time.sleep(0.5)  # дочитать ответ на последнюю команду
        stop.set()
        ser.close()


if __name__ == "__main__":
    main()
