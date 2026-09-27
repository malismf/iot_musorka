#!/usr/bin/env python
"""Сборка моделей корпуса BinSense.

    pip install -r requirements.txt
    python build.py

Пишет отдельный STL на каждую деталь в stl/ и картинки в render/.
Каждая деталь перед выгрузкой проверяется: замкнутая поверхность, ненулевой
объём, один кусок — модель с оторванной защёлкой до принтера не доедет.
"""

import argparse
import sys
from pathlib import Path

from model import params as P
from model import render
from model.mockups import MOCKUPS
from model.parts import PARTS
from model.solid import at, check, write_stl

ROOT = Path(__file__).parent
STL_DIR = ROOT / "stl"
RENDER_DIR = ROOT / "render"

# Материал и ориентация при печати. Ориентация не косметика: она решает, нужны
# поддержки или нет, и куда придётся слой раздела — по нему деталь и ломается.
PRINT = {
    "body":                  ("PETG/ASA", "как есть, дном на стол", 0.0),
    "cover":                 ("PETG/ASA", "плитой на стол, «хвост» вверх", 0.0),
    "gasket":                ("TPU 95A", "плашмя, петлёй", 0.0),
    "sensor_insert_a02yyuw": ("PETG/ASA", "юбкой на стол", 0.0),
    "sensor_insert_hcsr04":  ("PETG/ASA", "юбкой на стол", 0.0),
    "bracket":               ("PETG/ASA", "плитой на стол, пазом вверх", 0.0),
    "button_cap":            ("TPU 95A", "шляпкой на стол", 180.0),
    "light_pipe":            ("прозрачный PETG", "фланцем на стол", 0.0),
}

COLORS = {
    "body": "#aeb9c2", "cover": "#97a6b1", "gasket": "#c1543f",
    "sensor_insert_a02yyuw": "#5f8a6b", "sensor_insert_hcsr04": "#5f8a6b",
    "bracket": "#c79a4e",
    "button_cap": "#d9a93c", "light_pipe": "#b9dcef",
    "esp32_board": "#2f6b4c", "shield": "#3a7a58", "dupont": "#8a6f4e",
    "battery": "#3d4b58", "sensor_head": "#3a3a3a",
    "button": "#c8a14a", "led": "#7fb5d8", "silica": "#e0d7b8",
}

TITLES = {
    "body": "основание", "cover": "крышка", "gasket": "уплотнитель",
    "sensor_insert_a02yyuw": "вставка датчика A02YYUW",
    "sensor_insert_hcsr04": "вставка датчика HC-SR04",
    "bracket": "кронштейн",
    "button_cap": "толкатель кнопки", "light_pipe": "световод",
}


def for_print(name, solid):
    """Разворот детали в положение печати и посадка на плоскость стола."""
    angle = PRINT[name][2]
    if angle:
        solid = solid.rotate([angle, 0.0, 0.0])
    box = solid.bounding_box()
    return at(solid, -(box[0] + box[3]) / 2.0, -(box[1] + box[4]) / 2.0, -box[2])


def bracket_in_place(solid):
    """Кронштейн в сборке: перевёрнут и надет на «ласточкин хвост» крышки."""
    top = P.IN_H + P.COVER_T + P.DT_H
    return at(solid.rotate([180.0, 0.0, 0.0]), 0.0, 0.0, top + P.BRK_T)


def build_parts(verbose=True):
    STL_DIR.mkdir(exist_ok=True)
    rows, bad = [], []
    for name, factory in PARTS.items():
        solid = factory()
        _, volume, pieces, problems = check(solid, name)
        oriented = for_print(name, solid)
        box = oriented.bounding_box()
        triangles = write_stl(oriented, STL_DIR / f"{name}.stl", name)
        rows.append((name, volume / 1000.0,
                     (box[3] - box[0], box[4] - box[1], box[5] - box[2]),
                     triangles, PRINT[name][0], PRINT[name][1], problems))
        if problems:
            bad.append((name, problems))
    if verbose:
        head = f"{'деталь':24s} {'см³':>6s} {'габарит, мм':>22s} {'△':>7s}  материал"
        print(head)
        print("-" * len(head))
        for name, vol, size, tris, material, _, problems in rows:
            size_text = f"{size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f}"
            mark = "  ОШИБКА: " + "; ".join(problems) if problems else ""
            print(f"{name:24s} {vol:6.1f} {size_text:>22s} {tris:7d}  "
                  f"{material}{mark}")
        total = sum(row[1] for row in rows)
        print("-" * len(head))
        print(f"{'итого':24s} {total:6.1f} см³ пластика на одно устройство")
    return rows, bad


def scene_items(include_cover, exploded=False, gasket=True):
    """Набор тел для картинки: детали корпуса плюс макеты компонентов."""
    shift = (lambda v: v) if exploded else (lambda v: (0.0, 0.0, 0.0))
    items = [
        ("основание", PARTS["body"](), COLORS["body"], shift((0.0, 0.0, 0.0))),
        ("плата ESP32", MOCKUPS["esp32_board"][0](), COLORS["esp32_board"],
         shift((0.0, 0.0, 26.0))),
        ("шилд с обвязкой", MOCKUPS["shield"][0](), COLORS["shield"],
         shift((0.0, 0.0, 42.0))),
        ("держатель 18650", MOCKUPS["battery"][0](), COLORS["battery"],
         shift((0.0, 0.0, 30.0))),
        ("силикагель", MOCKUPS["silica"][0](), COLORS["silica"],
         shift((26.0, 26.0, 22.0))),
        ("кнопка 6×6", MOCKUPS["button"][0](), COLORS["button"],
         shift((-30.0, -46.0, 50.0))),
        ("светодиод RGB", MOCKUPS["led"][0](), COLORS["led"],
         shift((-30.0, -46.0, 30.0))),
        ("датчик A02YYUW", MOCKUPS["sensor_head"][0](), COLORS["sensor_head"],
         shift((0.0, 0.0, -78.0))),
        ("вставка датчика", PARTS["sensor_insert_a02yyuw"]().translate(
            [P.SENSOR_POS[0], P.SENSOR_POS[1],
             -P.FLOOR - P.INSERT_FLANGE_T - P.INSERT_SKIRT]),
         COLORS["sensor_insert_a02yyuw"], shift((0.0, 0.0, -42.0))),
        ("толкатель кнопки", PARTS["button_cap"]().rotate([0.0, -90.0, 0.0])
         .translate([-P.OUT_L / 2.0 - P.WALL - P.BTN_BOSS_H + 2.0,
                     P.BTN_POS[0], P.BTN_POS[1]]),
         COLORS["button_cap"], shift((-74.0, 0.0, 10.0))),
        ("световод", PARTS["light_pipe"]().rotate([0.0, -90.0, 0.0])
         .translate([-P.OUT_L / 2.0 - P.WALL - P.LED_BOSS_H + 4.0,
                     P.LED_POS[0], P.LED_POS[1]]),
         COLORS["light_pipe"], shift((-74.0, 0.0, -18.0))),
    ]
    if include_cover:
        if gasket:
            items.append(("уплотнитель", PARTS["gasket"]().translate(
                [0.0, 0.0, -P.GROOVE_D + 0.2]), COLORS["gasket"],
                shift((0.0, 0.0, 66.0))))
        items += [
            ("крышка", PARTS["cover"](), COLORS["cover"], shift((0.0, 0.0, 84.0))),
            ("кронштейн", bracket_in_place(PARTS["bracket"]()), COLORS["bracket"],
             shift((0.0, 0.0, 104.0))),
        ]
    return items


def build_renders(verbose=True):
    RENDER_DIR.mkdir(exist_ok=True)
    made = []

    render.scene_svg(
        RENDER_DIR / "assembly_open.svg", scene_items(False),
        azim=36.0, elev=30.0, title="BinSense — сборка со снятой крышкой",
        caption="Модели компонентов габаритные: по ним проверяется, что всё "
                "помещается вместе с колодками Dupont.")
    made.append("assembly_open.svg")

    render.scene_svg(
        RENDER_DIR / "assembly_closed.svg", scene_items(True, gasket=False),
        azim=214.0, elev=18.0, callouts=False,
        title="BinSense — устройство в сборе с кронштейном",
        caption="Кронштейн привинчивается к крышке контейнера, устройство "
                "вдвигается в «ласточкин хвост» и фиксируется защёлкой.")
    made.append("assembly_closed.svg")

    render.scene_svg(
        RENDER_DIR / "exploded.svg", scene_items(True, exploded=True),
        azim=36.0, elev=16.0, width=1600,
        title="BinSense — разнесённый вид",
        caption="Порядок сборки снизу вверх: вставка датчика, плата, "
                "аккумулятор, шилд, уплотнитель, крышка, кронштейн.")
    made.append("exploded.svg")

    # PNG для презентации и записки: SVG с рендером весит пару мегабайт.
    for name, azim, elev, items in (
            ("assembly_open", 36.0, 30.0, scene_items(False)),
            ("assembly_closed", 214.0, 18.0, scene_items(True, gasket=False)),
            ("exploded", 36.0, 16.0, scene_items(True, exploded=True))):
        render.scene_png(RENDER_DIR / f"{name}.png", items, azim=azim, elev=elev)
        made.append(f"{name}.png")

    render.layout_svg(RENDER_DIR / "layout.svg")
    made.append("layout.svg")

    if verbose:
        print("\nчертежи:", ", ".join(made))
        print("PDF: откройте SVG в браузере или Inkscape и напечатайте в файл.")
    return made


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stl-only", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    bad = []
    if not args.render_only:
        _, bad = build_parts()
    if not args.stl_only:
        build_renders()
    if bad:
        print("\nНЕ ВЫГРУЖАТЬ В ПЕЧАТЬ:", bad)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
