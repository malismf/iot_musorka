"""Библиотека условных обозначений для схем BinSense.

Рисуем в SVG напрямую: схема небольшая и целиком выводится из таблицы
`hardware/WIRING.md`, поэтому генератор дешевле, чем поддержка проекта KiCad,
который всё равно пришлось бы править руками при каждой правке распиновки.

Все функции складывают строки в список `out`. Координаты — в единицах SVG,
сетка 10 единиц; начало в левом верхнем углу листа.
"""

INK = "#14181c"       # линии схемы
WIRE = "#14181c"
REF = "#0b5ea8"       # позиционные обозначения (R1, C2, ...)
VAL = "#7a4600"       # номиналы
NET = "#0a6b4a"       # имена цепей
NOTE = "#6b737b"
FONT = "DejaVu Sans, Verdana, sans-serif"


def text(out, x, y, value, size=13, fill=INK, anchor="start", weight="normal",
         style="normal"):
    # font-family задан на корне <svg> и наследуется: повторять его в каждой
    # подписи — лишние килобайты, а схема встраивается в презентацию.
    extra = ""
    if anchor != "start":
        extra += f' text-anchor="{anchor}"'
    if weight != "normal":
        extra += f' font-weight="{weight}"'
    if style != "normal":
        extra += f' font-style="{style}"'
    out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
               f'fill="{fill}"{extra}>{value}</text>')


def wire(out, points, width=1.6, color=WIRE, dash=None):
    d = " ".join(f"{'M' if i == 0 else 'L'} {x:.1f} {y:.1f}"
                 for i, (x, y) in enumerate(points))
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<path d="{d}" fill="none" stroke="{color}" '
               f'stroke-width="{width}" stroke-linecap="round"{extra}/>')


def dot(out, x, y, r=4.0):
    out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{WIRE}"/>')


def box(out, x, y, w, h, fill="#ffffff", stroke=INK, width=1.8, dash=None, r=0):
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
               f'rx="{r}" fill="{fill}" stroke="{stroke}" '
               f'stroke-width="{width}"{extra}/>')


def ref_val(out, x, y, ref, value, anchor="start"):
    text(out, x, y, ref, 13, REF, anchor, "bold")
    if value:
        text(out, x, y + 15, value, 12, VAL, anchor)


# --- пассивные элементы ---------------------------------------------------

def resistor(out, x, y, ref, value, vertical=False, length=60, body=34,
             label_side=1):
    """Резистор по ГОСТ: прямоугольник 34 x 12. (x, y) — начало вывода."""
    pad = (length - body) / 2.0
    if vertical:
        wire(out, [(x, y), (x, y + pad)])
        box(out, x - 6, y + pad, 12, body, width=1.6)
        wire(out, [(x, y + pad + body), (x, y + length)])
        ref_val(out, x + 12 * label_side, y + pad + 12,
                ref, value, "start" if label_side > 0 else "end")
    else:
        wire(out, [(x, y), (x + pad, y)])
        box(out, x + pad, y - 6, body, 12, width=1.6)
        wire(out, [(x + pad + body, y), (x + length, y)])
        ref_val(out, x + length / 2.0, y - 26 if label_side > 0 else y + 34,
                ref, value, "middle")


def capacitor(out, x, y, ref, value, vertical=True, length=44, polar=False):
    """Конденсатор: две обкладки; у полярного вторая обкладка дугой."""
    if vertical:
        mid = y + length / 2.0
        wire(out, [(x, y), (x, mid - 5)])
        wire(out, [(x - 16, mid - 5), (x + 16, mid - 5)], width=2.4)
        if polar:
            out.append(f'<path d="M {x - 16:.1f} {mid + 8:.1f} '
                       f'Q {x:.1f} {mid - 2:.1f} {x + 16:.1f} {mid + 8:.1f}" '
                       f'fill="none" stroke="{INK}" stroke-width="2.4"/>')
            text(out, x - 22, mid - 10, "+", 14, INK, "end")
            wire(out, [(x, mid + 8), (x, y + length)])
        else:
            wire(out, [(x - 16, mid + 5), (x + 16, mid + 5)], width=2.4)
            wire(out, [(x, mid + 5), (x, y + length)])
        ref_val(out, x + 22, mid - 4, ref, value)
    else:
        mid = x + length / 2.0
        wire(out, [(x, y), (mid - 5, y)])
        wire(out, [(mid - 5, y - 16), (mid - 5, y + 16)], width=2.4)
        wire(out, [(mid + 5, y - 16), (mid + 5, y + 16)], width=2.4)
        wire(out, [(mid + 5, y), (x + length, y)])
        ref_val(out, mid, y + 34, ref, value, "middle")


# --- активные элементы ----------------------------------------------------

def npn(out, x, y, ref, value):
    """NPN-транзистор. (x, y) — вывод базы слева. Коллектор сверху."""
    bx, by = x + 46, y
    wire(out, [(x, y), (bx, by)])
    wire(out, [(bx, by - 26), (bx, by + 26)], width=2.4)
    wire(out, [(bx, by - 12), (bx + 34, by - 46), (bx + 34, by - 58)])
    wire(out, [(bx, by + 12), (bx + 34, by + 46), (bx + 34, by + 58)])
    out.append(f'<path d="M {bx + 20:.1f} {by + 24:.1f} L {bx + 32:.1f} '
               f'{by + 40:.1f} L {bx + 14:.1f} {by + 38:.1f} Z" fill="{INK}"/>')
    ref_val(out, bx + 48, by - 4, ref, value)
    return (bx + 34, by - 58), (bx + 34, by + 58)


def led(out, x, y, ref, value, vertical=True):
    """Светодиод: треугольник, полоса катода и две стрелки излучения."""
    if not vertical:
        raise ValueError("нужен только вертикальный вариант")
    top, bottom = y, y + 56
    wire(out, [(x, top), (x, top + 14)])
    out.append(f'<path d="M {x - 14:.1f} {top + 14:.1f} L {x + 14:.1f} '
               f'{top + 14:.1f} L {x:.1f} {top + 38:.1f} Z" fill="none" '
               f'stroke="{INK}" stroke-width="1.8"/>')
    wire(out, [(x - 15, top + 38), (x + 15, top + 38)], width=2.4)
    wire(out, [(x, top + 38), (x, bottom)])
    for i in (0, 1):
        ax = x + 18 + i * 9
        wire(out, [(ax, top + 30 - i * 6), (ax + 13, top + 17 - i * 6)], 1.4)
        out.append(f'<path d="M {ax + 13:.1f} {top + 17 - i * 6:.1f} '
                   f'l -6 1 l 5 4 Z" fill="{INK}"/>')
    ref_val(out, x + 44, top + 24, ref, value)
    return (x, top), (x, bottom)


def push_button(out, x, y, ref, value):
    """Тактовая кнопка: нормально разомкнутый контакт с толкателем."""
    wire(out, [(x, y), (x + 16, y)])
    wire(out, [(x + 44, y), (x + 60, y)])
    wire(out, [(x + 14, y - 12), (x + 46, y - 12)], width=2.2)
    wire(out, [(x + 16, y), (x + 16, y - 12)])
    wire(out, [(x + 44, y), (x + 44, y - 12)])
    wire(out, [(x + 30, y - 12), (x + 30, y - 26)])
    wire(out, [(x + 18, y - 26), (x + 42, y - 26)], width=2.2)
    ref_val(out, x + 30, y + 26, ref, value, "middle")
    return (x, y), (x + 60, y)


def buzzer(out, x, y, ref, value):
    """Активный зуммер: кружок с перемычкой."""
    out.append(f'<circle cx="{x + 26:.1f}" cy="{y:.1f}" r="22" fill="none" '
               f'stroke="{INK}" stroke-width="1.8"/>')
    wire(out, [(x + 26, y - 22), (x + 26, y - 40)])
    wire(out, [(x + 26, y + 22), (x + 26, y + 40)])
    wire(out, [(x + 10, y), (x + 42, y)], width=1.4)
    ref_val(out, x + 54, y - 4, ref, value)
    return (x + 26, y - 40), (x + 26, y + 40)


def gnd(out, x, y, label="GND"):
    wire(out, [(x, y), (x, y + 16)])
    for i, half in enumerate((16, 10, 5)):
        wire(out, [(x - half, y + 16 + i * 6), (x + half, y + 16 + i * 6)], 2.2)
    if label:
        text(out, x, y + 52, label, 11, NOTE, "middle")


def vcc(out, x, y, label="+3.3 В"):
    wire(out, [(x, y), (x, y - 16)])
    wire(out, [(x - 14, y - 16), (x + 14, y - 16)], width=2.4)
    text(out, x, y - 24, label, 12, NET, "middle", "bold")


def net_label(out, x, y, name, direction="right"):
    """Имя цепи: соединяет блоки без длинных проводов через весь лист."""
    width = 11.0 + len(name) * 7.6
    if direction == "right":
        pts = [(x, y - 11), (x + width - 10, y - 11), (x + width, y),
               (x + width - 10, y + 11), (x, y + 11)]
        tx, anchor = x + 8, "start"
    else:
        pts = [(x, y - 11), (x - width + 10, y - 11), (x - width, y),
               (x - width + 10, y + 11), (x, y + 11)]
        tx, anchor = x - 8, "end"
    d = " ".join(f"{'M' if i == 0 else 'L'} {px:.1f} {py:.1f}"
                 for i, (px, py) in enumerate(pts)) + " Z"
    out.append(f'<path d="{d}" fill="#eef6f2" stroke="{NET}" stroke-width="1.2"/>')
    text(out, tx, y + 4, name, 12, NET, anchor, "bold")


def ic(out, x, y, w, h, name, sub=""):
    box(out, x, y, w, h, fill="#f4f7f9", width=2.2, r=4)
    text(out, x + w / 2.0, y + 26, name, 16, INK, "middle", "bold")
    if sub:
        text(out, x + w / 2.0, y + 44, sub, 11, NOTE, "middle")


def ic_pin(out, x, y, name, side="left", length=34, number=""):
    """Вывод микросхемы: отрезок наружу, подпись внутри корпуса."""
    if side == "left":
        wire(out, [(x - length, y), (x, y)])
        text(out, x + 8, y + 4, name, 12)
        if number:
            text(out, x - 6, y - 6, number, 9, NOTE, "end")
        return x - length, y
    wire(out, [(x, y), (x + length, y)])
    text(out, x - 8, y + 4, name, 12, INK, "end")
    if number:
        text(out, x + 6, y - 6, number, 9, NOTE)
    return x + length, y


def frame(out, width, height, title, sheet, note=""):
    """Рамка листа и основная надпись."""
    box(out, 20, 20, width - 40, height - 40, fill="none", width=2.2)
    bx, by, bw, bh = width - 480, height - 132, 460, 112
    box(out, bx, by, bw, bh, fill="#ffffff", width=2.0)
    wire(out, [(bx, by + 38), (bx + bw, by + 38)], 1.2)
    wire(out, [(bx, by + 74), (bx + bw, by + 74)], 1.2)
    wire(out, [(bx + 300, by), (bx + 300, by + bh)], 1.2)
    text(out, bx + 12, by + 26, title, 15, INK, "start", "bold")
    text(out, bx + 12, by + 62, "BinSense — мониторинг заполненности "
                                "контейнеров", 12, NOTE)
    text(out, bx + 12, by + 98, note or "Источник: hardware/WIRING.md, "
                                        "hardware/BOM.csv", 11, NOTE)
    text(out, bx + 312, by + 26, sheet, 13, INK, "start", "bold")
    text(out, bx + 312, by + 62, "Учебный проект", 12, NOTE)
    text(out, bx + 312, by + 98, "Схему генерирует make_schematic.py", 11, NOTE)


def document(width, height):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" '
            f'font-family="{FONT}">',
            f'<rect width="{width}" height="{height}" fill="#ffffff"/>']


def save(out, path):
    out.append("</svg>")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(out))
