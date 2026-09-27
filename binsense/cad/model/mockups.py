"""Упрощённые модели покупных компонентов.

В STL не выгружаются: нужны, чтобы проверить, что всё помещается, и чтобы
построить сборку, разнесённый вид и чертёж расположения элементов.
Размеры — габаритные, с учётом разъёмов: провод с колодкой Dupont занимает
заметно больше места, чем сам штырёк, и это частая причина переделки корпуса.
"""

from . import params as P
from .solid import at, box, cyl, prism, rrect


def esp32_board():
    """Плата LOLIN D32: текстолит, модуль ESP32, разъём USB, гребёнки."""
    x, y = P.PCB_POS
    z = P.BOSS_H
    pcb = at(box(P.PCB_L, P.PCB_W, P.PCB_T), x, y, z)
    module = at(box(25.5, 18.0, 3.2), x + 8.0, y, z + P.PCB_T)
    usb = at(box(7.5, 9.0, 3.2), x - P.PCB_L / 2.0 + 3.0, y, z + P.PCB_T)
    # Гребёнки по краям платы: именно они, а не чип, задают высоту шилда.
    pins = None
    for sy in (-1.0, 1.0):
        row = at(box(P.PCB_L - 6.0, 2.6, 8.5), x, y + sy * (P.PCB_W / 2.0 - 1.8),
                 z + P.PCB_T)
        pins = row if pins is None else pins + row
    return pcb + module + usb + pins


def shield():
    """Макетная плата-шилд: на ней кнопка, светодиод, ключ и обвязка."""
    x, y = P.PCB_POS
    z = P.BOSS_H + P.PCB_T + 8.5
    return at(box(P.PCB_L - 4.0, P.PCB_W, 1.6), x, y, z)


def battery():
    """Держатель 18650 с аккумулятором и разъёмом JST-PH."""
    x, y = P.BAT_POS
    holder = at(box(P.BAT_L, P.BAT_W, P.BAT_H), x, y, 0.0)
    jst = at(box(8.0, 6.0, 5.0), x + P.BAT_L / 2.0 + 4.0, y, 2.0)
    return holder + jst


def sensor_head():
    """Головка A02YYUW в гнезде вставки, с кабелем."""
    x, y = P.SENSOR_POS
    z = -P.FLOOR - P.INSERT_FLANGE_T - P.INSERT_SKIRT + 4.0
    head = at(cyl(P.A02_H, P.A02_D), x, y, z)
    cable = at(cyl(18.0, 4.0), x, y, z + P.A02_H)
    return head + cable


def button():
    """Тактовая кнопка 6х6 на шилде, напротив толкателя в стенке."""
    y, z = P.BTN_POS
    return at(box(P.BTN_SW, P.BTN_SW, 5.0), -P.IN_L / 2.0 + 4.0, y, z - 2.5)


def led():
    """Светодиод RGB 5 мм напротив световода."""
    y, z = P.LED_POS
    return at(cyl(8.0, P.LED_D).rotate([0.0, 90.0, 0.0]), -P.IN_L / 2.0 + 1.0, y, z)


def silica():
    """Пакетик силикагеля в своём отсеке."""
    x, y = P.SILICA_POS
    return at(box(P.SILICA_L, P.SILICA_W, 5.0), x, y, 0.0)


def dupont():
    """Объём, который занимают колодки Dupont над гребёнками платы."""
    x, y = P.PCB_POS
    z = P.BOSS_H + P.PCB_T + 10.1
    return at(prism(rrect(P.PCB_L - 6.0, P.PCB_W + 2.0, 2.0), 6.0, z), x, y)


MOCKUPS = {
    "esp32_board": (esp32_board, "плата ESP32 (LOLIN D32)"),
    "shield": (shield, "шилд с обвязкой"),
    "dupont": (dupont, "колодки Dupont"),
    "battery": (battery, "держатель 18650"),
    "sensor_head": (sensor_head, "датчик A02YYUW"),
    "button": (button, "кнопка 6х6"),
    "led": (led, "светодиод RGB"),
    "silica": (silica, "силикагель"),
}
