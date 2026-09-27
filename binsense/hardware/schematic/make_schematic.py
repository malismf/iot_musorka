#!/usr/bin/env python
"""Генератор схем BinSense.

    python make_schematic.py

Строит три листа в SVG:
  schematic.svg        принципиальная схема: NodeMCU (ESP8266) и датчик A02YYUW;
  schematic_proto.svg  вариант с датчиком HC-SR04;
  wiring.svg           монтажная схема: что куда паяется на макетной плате.

Схема выводится из той же таблицы, что и `hardware/WIRING.md`: список цепей
лежит в NETS, и он же выгружается в netlist.csv. Если меняется распиновка,
правится одна таблица, а не три картинки.
"""

from pathlib import Path

import symbols as S

ROOT = Path(__file__).parent
W, H = 1760, 1100

# Распиновка NodeMCU / Wemos D1 mini. Порядок строк = порядок выводов сверху вниз.
# (вывод платы, имя цепи, y, комментарий)
PINS_LEFT = [
    ("D3 / GPIO0", "BTN", 380, "кнопка FLASH"),
    ("VIN", "+5V", 460, "5 В от USB"),
]
PINS_RIGHT = [
    ("D5 / GPIO14", "SENS_RX", 290, "UART RX, белый"),
    ("D6 / GPIO12", "SENS_TX", 340, "UART TX, жёлтый"),
    ("D1 / GPIO5", "LED_R", 420, "красный канал"),
    ("D2 / GPIO4", "LED_G", 470, "зелёный канал"),
    ("D7 / GPIO13", "LED_B", 520, "синий канал"),
    ("D8 / GPIO15", "BUZZ", 600, "база ключа зуммера"),
]

# Цепи для netlist.csv: имя, что к чему.
NETS = [
    ("+3V3", "U1.3V3, U2.VCC, BZ1.+"),
    ("+5V", "J1.VBUS, U1.VIN, U3.VCC (только HC-SR04)"),
    ("GND", "J1.GND, U1.GND, U2.GND, D1.K, Q1.E, SW1.2"),
    ("SENS_RX", "U1.D5, U2.TX (белый)"),
    ("SENS_TX", "U1.D6, U2.RX (жёлтый)"),
    ("BTN", "U1.D3, SW1.1, R1.2 (R1 — на плате)"),
    ("LED_R", "U1.D1, R2.1"),
    ("LED_G", "U1.D2, R3.1"),
    ("LED_B", "U1.D7, R4.1"),
    ("BUZZ", "U1.D8, R5.1"),
    ("BUZZ_C", "Q1.C, BZ1.−"),
    ("TRIG", "U1.D5, U3.Trig (только HC-SR04)"),
    ("ECHO_DIV", "R6.2, R7.1, U1.D6 (только HC-SR04)"),
]


def mcu(out):
    """Плата NodeMCU с выводами и именами цепей."""
    x, y, w, h = 660, 230, 300, 540
    S.ic(out, x, y, w, h, "U1  NodeMCU (ESP8266)", "или Wemos D1 mini")
    for name, net, py, note in PINS_LEFT:
        ex, ey = S.ic_pin(out, x, py, name, "left")
        S.net_label(out, ex, ey, net, "left")
        S.text(out, x + 8, py + 18, note, 10, S.NOTE)
    for name, net, py, note in PINS_RIGHT:
        ex, ey = S.ic_pin(out, x + w, py, name, "right")
        S.net_label(out, ex, ey, net, "right")
        S.text(out, x + w - 8, py + 18, note, 10, S.NOTE, "end")

    # Земля и 3.3 В: стабилизатор стоит на самой плате.
    gx, gy = S.ic_pin(out, x, 660, "GND", "left")
    S.gnd(out, gx - 30, gy, "")
    S.wire(out, [(gx - 30, gy), (gx, gy)])
    vx, vy = S.ic_pin(out, x, 720, "3V3", "left")
    S.wire(out, [(vx - 30, vy), (vx, vy)])
    S.vcc(out, vx - 30, vy)
    S.text(out, x + 8, 738, "стабилизатор платы, питает всю обвязку",
           10, S.NOTE)


def button_block(out):
    """Кнопка на GPIO0: на NodeMCU это встроенная FLASH, подтяжка — на плате."""
    S.box(out, 110, 240, 380, 200, fill="#fbfcfd", stroke=S.NOTE, width=1.2,
          dash="6 5", r=6)
    S.text(out, 126, 264, "Кнопка монтажника", 13, S.INK, "start", "bold")

    node_x, node_y = 250, 350
    S.vcc(out, node_x, 286)
    S.resistor(out, node_x, 286, "R1", "10 кОм, на плате", vertical=True,
               length=64)
    S.wire(out, [(node_x, 350), (node_x, node_y)])
    S.dot(out, node_x, node_y)
    S.net_label(out, node_x + 150, node_y, "BTN", "left")
    S.wire(out, [(node_x, node_y), (node_x + 150, node_y)])

    S.wire(out, [(node_x, node_y), (node_x, node_y + 40)])
    S.push_button(out, node_x, node_y + 40, "SW1", "6x6")
    S.wire(out, [(node_x + 60, node_y + 40), (node_x + 60, node_y + 58)])
    S.gnd(out, node_x + 60, node_y + 58, "")
    S.text(out, 126, 430, "На D1 mini кнопку ставят между D3 и GND",
           10, S.NOTE)


def power_block(out):
    """Питание от USB: стабилизатор 3.3 В уже стоит на плате."""
    S.box(out, 110, 470, 380, 210, fill="#fbfcfd", stroke=S.NOTE, width=1.2,
          dash="6 5", r=6)
    S.text(out, 126, 494, "Питание от USB", 13, S.INK, "start", "bold")
    S.ic(out, 150, 520, 170, 100, "J1  micro-USB", "зарядка 5 В, 1 А")
    ex, ey = S.ic_pin(out, 320, 555, "VBUS", "right")
    S.net_label(out, ex, ey, "+5V", "right")
    gx, gy = S.ic_pin(out, 320, 595, "GND", "right")
    S.wire(out, [(gx, gy), (gx + 20, gy)])
    S.gnd(out, gx + 20, gy, "")
    S.text(out, 126, 650, "Разъём USB — на самой плате: кабель от зарядки",
           10, S.NOTE)
    S.text(out, 126, 666, "телефона включается прямо в него.", 10, S.NOTE)


def sensor_block(out):
    """Датчик A02YYUW: питание 3.3 В, данные — программный UART."""
    S.box(out, 1030, 240, 670, 250, fill="#fbfcfd", stroke=S.NOTE, width=1.2,
          dash="6 5", r=6)
    S.text(out, 1046, 264, "Ультразвуковой датчик A02YYUW (UART)",
           13, S.INK, "start", "bold")

    # Все выводы датчика слева: имена цепей остаются внутри листа.
    S.ic(out, 1470, 290, 190, 180, "U2  A02YYUW", "влагозащищённый")
    S.ic_pin(out, 1470, 320, "VCC", "left")
    S.ic_pin(out, 1470, 360, "GND", "left")
    S.ic_pin(out, 1470, 400, "RX жёлт.", "left")
    S.ic_pin(out, 1470, 440, "TX бел.", "left")
    S.wire(out, [(1400, 320), (1436, 320)])
    S.vcc(out, 1400, 320)
    S.gnd(out, 1436, 360, "")
    S.net_label(out, 1436, 400, "SENS_TX", "left")
    S.net_label(out, 1436, 440, "SENS_RX", "left")
    S.text(out, 1046, 330, "Питание 3.3 В: при 5 В выход TX датчика", 11,
           S.NOTE)
    S.text(out, 1046, 348, "был бы выше допустимого для ESP8266.", 11, S.NOTE)
    S.text(out, 1046, 384, "Второго аппаратного UART у ESP8266 нет —", 11,
           S.NOTE)
    S.text(out, 1046, 402, "датчик читается программным на D5/D6.", 11, S.NOTE)
    S.text(out, 1046, 476, "Устройство работает от USB, поэтому датчик питается "
                           "постоянно, без ключа.", 10, S.NOTE)


def led_block(out):
    """RGB-светодиод: по 220 Ом на канал, общий катод."""
    S.box(out, 1030, 510, 670, 200, fill="#fbfcfd", stroke=S.NOTE, width=1.2,
          dash="6 5", r=6)
    S.text(out, 1046, 534, "Индикация: светодиод RGB с общим катодом",
           13, S.INK, "start", "bold")

    channels = [("LED_R", "R2", 1160, "красный"),
                ("LED_G", "R3", 1330, "зелёный"),
                ("LED_B", "R4", 1500, "синий")]
    cathode_y = 666
    for net, ref, x, colour in channels:
        S.net_label(out, x - 62, 574, net, "left")
        S.wire(out, [(x - 62, 574), (x, 574)])
        S.resistor(out, x, 564, ref, "220 Ом", vertical=True, length=44,
                   label_side=-1)
        top, bottom = S.led(out, x, 608, "D1", colour)
        S.wire(out, [bottom, (x, cathode_y)])
    S.wire(out, [(1160, cathode_y), (1500, cathode_y)])
    S.gnd(out, 1330, cathode_y, "")
    for x in (1160, 1500):
        S.dot(out, x, cathode_y)
    S.text(out, 1046, 698, "Ток канала 5–7 мА: светодиод хорошо виден снаружи "
                           "корпуса.", 10, S.NOTE)


def buzzer_block(out):
    """Зуммер через NPN-ключ: вывод ESP8266 не тянет его напрямую."""
    S.box(out, 1030, 730, 670, 200, fill="#fbfcfd", stroke=S.NOTE, width=1.2,
          dash="6 5", r=6)
    S.text(out, 1046, 754, "Зуммер подтверждения при монтаже", 13, S.INK,
           "start", "bold")

    base_y = 846
    S.net_label(out, 1140, base_y, "BUZZ", "left")
    S.resistor(out, 1150, base_y, "R5", "1 кОм", length=60)
    collector, emitter = S.npn(out, 1210, base_y, "Q1", "S8050")
    S.gnd(out, emitter[0], emitter[1], "")
    top, bottom = S.buzzer(out, 1420, 836, "BZ1", "3.3 В активный")
    S.wire(out, [collector, (collector[0], bottom[1]), bottom])
    S.vcc(out, top[0], top[1])
    S.text(out, 1046, 918, "D8 при включении притянут к земле — зуммер не "
                           "пищит, пока прошивка не запустилась.", 10, S.NOTE)


def sheet_main():
    out = S.document(W, H)
    S.text(out, 60, 78, "BinSense — принципиальная электрическая схема "
                        "устройства", 24, S.INK, "start", "bold")
    S.text(out, 60, 106, "Блоки соединены именами цепей: схема читается без "
                         "проводов через весь лист, распиновка совпадает "
                         "с hardware/WIRING.md.", 12, S.NOTE)
    S.text(out, 60, 128, "Номиналы и обозначения — из hardware/BOM.csv. "
                         "Вариант с датчиком HC-SR04 — на листе 2.",
           12, S.NOTE)
    mcu(out)
    button_block(out)
    power_block(out)
    sensor_block(out)
    led_block(out)
    buzzer_block(out)
    S.frame(out, W, H, "Принципиальная электрическая схема",
            "Лист 1 из 2 · основная сборка")
    S.save(out, ROOT / "schematic.svg")


def sheet_proto():
    """Лист 2: вариант с датчиком HC-SR04 и чем он отличается."""
    out = S.document(1200, 820)
    S.ic(out, 420, 200, 300, 260, "U1  NodeMCU (ESP8266)",
         "окружение esp8266_hcsr04")
    for name, net, py in (("D5 / GPIO14", "TRIG", 250),
                          ("D6 / GPIO12", "ECHO_DIV", 330),
                          ("VIN", "+5V", 410)):
        ex, ey = S.ic_pin(out, 720, py, name, "right")
        S.net_label(out, ex, ey, net, "right")
    gx, gy = S.ic_pin(out, 420, 410, "GND", "left")
    S.gnd(out, gx - 30, gy, "")
    S.wire(out, [(gx - 30, gy), (gx, gy)])

    S.ic(out, 900, 200, 190, 170, "U3  HC-SR04", "питание 5 В")
    S.ic_pin(out, 900, 230, "VCC", "left")
    S.ic_pin(out, 900, 270, "Trig", "left")
    S.ic_pin(out, 900, 310, "Echo", "left")
    S.ic_pin(out, 900, 350, "GND", "left")
    S.net_label(out, 866, 230, "+5V", "left")
    S.net_label(out, 866, 270, "TRIG", "left")
    S.gnd(out, 866, 350, "")

    # Делитель Echo: датчик питается от 5 В, вход ESP8266 пяти вольт не терпит.
    S.wire(out, [(866, 310), (700, 310), (700, 560)])
    S.resistor(out, 700, 560, "R6", "1 кОм", vertical=True, length=56)
    node_y = 616
    S.dot(out, 700, node_y)
    S.net_label(out, 560, node_y, "ECHO_DIV", "left")
    S.wire(out, [(560, node_y), (700, node_y)])
    S.resistor(out, 700, node_y, "R7", "2 кОм", vertical=True, length=56,
               label_side=-1)
    S.gnd(out, 700, node_y + 56, "")
    S.text(out, 120, 620, "Делитель 1 кОм / 2 кОм: 5 В на выходе Echo", 12)
    S.text(out, 120, 640, "превращаются в 3.3 В на входе ESP8266.", 12)
    S.text(out, 120, 680, "Trig от 3.3 В HC-SR04 понимает без согласования.",
           12, S.NOTE)
    S.text(out, 120, 700, "HC-SR04 не защищён от влаги: для установки на", 12,
           S.NOTE)
    S.text(out, 120, 720, "контейнер лучше A02YYUW (лист 1).", 12, S.NOTE)
    S.frame(out, 1200, 820, "Схема с датчиком HC-SR04",
            "Лист 2 из 2 · вариант датчика",
            "Собирается окружением pio run -e esp8266_hcsr04")
    S.save(out, ROOT / "schematic_proto.svg")


# --- монтажная схема ------------------------------------------------------

WIRES = [
    # (откуда, куда, цвет, подпись)
    ("U1.D5", "U2.TX", "#ffffff", "бел."),
    ("U1.D6", "U2.RX", "#f2c94c", "жёлт."),
    ("U1.D3", "SW1", "#27ae60", "BTN, только D1 mini"),
    ("U1.D1", "R2", "#eb5757", "LED_R"),
    ("U1.D2", "R3", "#27ae60", "LED_G"),
    ("U1.D7", "R4", "#2d9cdb", "LED_B"),
    ("U1.D8", "R5", "#f2994a", "BUZZ"),
    ("U1.3V3", "шина +3.3 В", "#eb5757", "питание"),
    ("U1.GND", "шина GND", "#333333", "земля"),
]


def sheet_wiring():
    """Монтажная схема: расположение деталей на макетной плате 40 × 60 мм."""
    out = S.document(1500, 1000)
    S.text(out, 60, 70, "Монтажная схема: макетная плата 40 × 60 мм рядом с NodeMCU",
           22, S.INK, "start", "bold")
    S.text(out, 60, 96, "Вид сверху. NodeMCU вставляется в гребёнки, обвязка — на "
                        "той же макетной плате. Размеры в клетках 2.54 мм.",
           12, S.NOTE)

    # Плата NodeMCU.
    S.box(out, 120, 150, 620, 300, fill="#eef3ef", stroke="#4a7a5c", width=2, r=6)
    S.text(out, 132, 176, "U1 NodeMCU (ESP8266), разъём USB — питание", 13,
           "#2f6b4c", "start", "bold")
    left = [("3V3", 210), ("GND", 240), ("VIN", 270), ("D3", 300)]
    right = [("D1", 210), ("D2", 240), ("D5", 270), ("D6", 300), ("D7", 330),
             ("D8", 360)]
    for name, y in left:
        S.box(out, 130, y - 9, 18, 18, fill="#c8d8cd", stroke="#4a7a5c",
              width=1.2, r=3)
        S.text(out, 156, y + 5, name, 11)
    for name, y in right:
        S.box(out, 712, y - 9, 18, 18, fill="#c8d8cd", stroke="#4a7a5c",
              width=1.2, r=3)
        S.text(out, 704, y + 5, name, 11, S.INK, "end")

    # Макетная плата и что на ней стоит.
    S.box(out, 820, 150, 560, 330, fill="#fdf7ea", stroke="#b08a3e", width=2, r=6)
    S.text(out, 832, 176, "Макетная плата 40 × 60 мм", 13, "#8a6a26",
           "start", "bold")
    placed = [
        (850, 200, 120, 46, "D1 RGB", "к стенке корпуса"),
        (990, 200, 120, 46, "R2 R3 R4", "по 220 Ом"),
        (1130, 200, 120, 46, "клеммы", "провода датчика"),
        (850, 270, 120, 46, "Q1 S8050", "ключ зуммера"),
        (990, 270, 120, 46, "R5 1 кОм", "база Q1"),
        (1130, 270, 120, 46, "SW1 кнопка", "только для D1 mini"),
        (850, 340, 260, 46, "BZ1 зуммер", "опционально, выносится проводами"),
        (1130, 340, 120, 46, "R6 R7", "делитель, HC-SR04"),
    ]
    for x, y, w, h, name, note in placed:
        S.box(out, x, y, w, h, fill="#ffffff", stroke="#b08a3e", width=1.4, r=4)
        S.text(out, x + w / 2, y + 20, name, 12, S.INK, "middle", "bold")
        S.text(out, x + w / 2, y + 36, note, 9, S.NOTE, "middle")

    # Легенда проводов.
    S.text(out, 120, 620, "Провода между платой и обвязкой", 15, S.INK, "start",
           "bold")
    for i, (src, dst, colour, label) in enumerate(WIRES):
        y = 650 + i * 26
        S.wire(out, [(120, y), (200, y)], 5,
               colour if colour != "#ffffff" else "#d8d8d8")
        S.text(out, 216, y + 5, f"{src} → {dst}", 12)
        S.text(out, 470, y + 5, label, 11, S.NOTE)

    S.text(out, 820, 620, "Правила пайки", 15, S.INK, "start", "bold")
    rules = [
        "D3, D4 и D8 — выводы загрузчика: при включении D3 и D4",
        "не должны быть притянуты к земле, а D8 — к питанию.",
        "Поэтому кнопку не держат при включении, а зуммер",
        "стоит на D8 через ключ.",
        "Провода датчика обжимаются в клеммник: разъём Dupont в",
        "контейнере разбалтывается от вибрации при выгрузке.",
        "Питание — зарядка телефона 5 В, 1 А и кабель micro-USB.",
    ]
    for i, line in enumerate(rules):
        S.text(out, 820, 650 + i * 24, line, 12, S.NOTE)

    S.frame(out, 1500, 1000, "Монтажная схема", "Сборка на макетной плате")
    S.save(out, ROOT / "wiring.svg")


def netlist():
    lines = ["цепь,подключения"]
    for name, members in NETS:
        lines.append(f'"{name}","{members}"')
    (ROOT / "netlist.csv").write_text("\n".join(lines) + "\n", encoding="utf-8",
                                      newline="\n")


def main():
    sheet_main()
    sheet_proto()
    sheet_wiring()
    netlist()
    print("схемы: schematic.svg, schematic_proto.svg, wiring.svg, netlist.csv")


if __name__ == "__main__":
    main()
