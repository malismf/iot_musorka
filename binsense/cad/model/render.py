"""Картинки для отчёта: сборка, разнесённый вид, чертёж расположения.

Рендер свой, без внешних библиотек: ортографическая проекция, отсечение
нелицевых граней и «алгоритм художника». Этого достаточно для иллюстраций
в презентации и пояснительной записке, а зависимостей не добавляет.
"""

import math

import numpy as np

from . import params as P
from . import raster
from .solid import triangles

LIGHT = (0.35, 0.45, 0.82)   # направление света в системе камеры
AMBIENT = 0.38


def _basis(azim, elev):
    a, e = math.radians(azim), math.radians(elev)
    right = np.array([-math.sin(a), math.cos(a), 0.0])
    up = np.array([-math.cos(a) * math.sin(e), -math.sin(a) * math.sin(e),
                   math.cos(e)])
    view = np.array([math.cos(a) * math.cos(e), math.sin(a) * math.cos(e),
                     math.sin(e)])
    return right, up, view


def _hex_to_rgb(value):
    value = value.lstrip("#")
    return np.array([int(value[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)


def _shade(rgb, factor):
    out = np.clip(rgb * factor, 0.0, 255.0).astype(int)
    return "#%02x%02x%02x" % tuple(out)


def project_scene(items, azim, elev):
    """Проекция набора тел на плоскость экрана.

    Возвращает отсортированные по глубине треугольники (дальние первыми),
    их цвета и точки привязки выносок. Этим пользуются и SVG, и PNG.
    """
    right, up, view = _basis(azim, elev)
    light = np.array(LIGHT)
    light = light / np.linalg.norm(light)
    world_light = light[0] * right + light[1] * up + light[2] * view

    all_pts, all_colors, all_depth = [], [], []
    labels = []
    for label, solid, color, shift in items:
        shift = np.array(shift, dtype=float)
        tri = triangles(solid)
        normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        norm = np.linalg.norm(normals, axis=1, keepdims=True)
        norm[norm == 0.0] = 1.0
        normals = normals / norm
        visible = normals @ view > 1e-9
        tri, normals = tri[visible], normals[visible]
        if len(tri) == 0:
            continue
        moved = tri + shift
        depth = (moved @ view).mean(axis=1)
        pts = np.stack([moved @ right, -(moved @ up)], axis=-1)
        factor = AMBIENT + (1.0 - AMBIENT) * np.clip(normals @ world_light,
                                                     0.0, 1.0)
        rgb = _hex_to_rgb(color)
        colors = np.clip(rgb[None, :] * factor[:, None], 0, 255).astype(np.uint8)
        all_pts.append(pts)
        all_colors.append(colors)
        all_depth.append(depth)
        centre = tri.reshape(-1, 3).mean(axis=0) + shift
        labels.append((label, (centre @ right, -(centre @ up))))

    if not all_pts:
        raise ValueError("нечего рисовать")
    pts = np.concatenate(all_pts)
    colors = np.concatenate(all_colors)
    depth = np.concatenate(all_depth)
    order = np.argsort(depth)
    labels.sort(key=lambda item: item[1][1])
    return pts[order], colors[order], labels


def _fit(pts, width, margin, extra_right=0.0, extra_top=0.0):
    """Масштаб и смещение, вписывающие проекцию в лист заданной ширины."""
    x0, y0 = pts[:, :, 0].min(), pts[:, :, 1].min()
    x1, y1 = pts[:, :, 0].max() + extra_right, pts[:, :, 1].max()
    scale = (width - 2 * margin) / (x1 - x0)
    height = int((y1 - y0) * scale + 2 * margin + extra_top)
    top = margin + extra_top

    def to_px(point):
        return ((point[0] - x0) * scale + margin, (point[1] - y0) * scale + top)

    return scale, height, to_px


def scene_svg(path, items, azim=38.0, elev=24.0, width=1500, margin=70,
              title="", caption="", callouts=True):
    """Изометрический вид набора деталей в вектор.

    items — список (подпись, тело, цвет, вектор сдвига). Сдвиг используется
    для разнесённого вида.
    """
    pts, colors, labels = project_scene(items, azim, elev)
    scale, height, to_px = _fit(pts, width, margin, 78.0 if callouts else 0.0,
                                52.0 if title else 0.0)
    top = margin + (52 if title else 0)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
           f'height="{height}" viewBox="0 0 {width} {height}" '
           f'font-family="DejaVu Sans, Verdana, sans-serif">',
           f'<rect width="{width}" height="{height}" fill="#f7f8f9"/>']
    if title:
        out.append(f'<text x="{margin}" y="38" font-size="24" fill="#1d2329">'
                   f'{title}</text>')
    for i in range(len(pts)):
        colour = "#%02x%02x%02x" % tuple(int(v) for v in colors[i])
        corners = " ".join("%.1f,%.1f" % to_px(pt) for pt in pts[i])
        out.append(f'<polygon points="{corners}" fill="{colour}" '
                   f'stroke="{colour}" stroke-width="0.4"/>')
    if callouts:
        for index, (label, anchor) in enumerate(labels):
            mx, my = to_px(anchor)
            tx = width - margin - 8.0
            ty = top + 22.0 + index * 25.0
            out.append(f'<line x1="{mx:.1f}" y1="{my:.1f}" x2="{tx - 8:.1f}" '
                       f'y2="{ty - 4:.1f}" stroke="#7a838c" stroke-width="1" '
                       f'stroke-dasharray="4 3"/>')
            out.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="3" '
                       f'fill="#1d2329"/>')
            out.append(f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="15" '
                       f'text-anchor="end" fill="#1d2329">{label}</text>')
    if caption:
        out.append(f'<text x="{margin}" y="{height - 22}" font-size="14" '
                   f'fill="#5c666f">{caption}</text>')
    out.append("</svg>")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(out))
    return len(pts)


def scene_png(path, items, azim=38.0, elev=24.0, width=1400, margin=40,
              supersample=2, background=(247, 248, 249)):
    """Тот же вид растром: в десять раз меньше SVG, вставляется куда угодно."""
    pts, colors, _ = project_scene(items, azim, elev)
    big = width * supersample
    _, height, to_px = _fit(pts, big, margin * supersample)
    image = np.empty((height, big, 3), dtype=np.uint8)
    image[:, :] = np.array(background, dtype=np.uint8)
    flat = np.empty_like(pts)
    for i in range(len(pts)):
        for j in range(3):
            flat[i, j] = to_px(pts[i, j])
    raster.fill_triangles(image, flat, colors)
    raster.write_png(path, raster.downsample(image, supersample))
    return len(pts)


# --- чертёж расположения элементов ---------------------------------------

def _dim(out, x1, y1, x2, y2, text, offset=0.0, vertical=False):
    """Размерная линия со стрелками и подписью."""
    if vertical:
        x = x1 + offset
        out.append(f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" '
                   f'stroke="#c0392b" stroke-width="1"/>')
        out.append(f'<line x1="{x - 4}" y1="{y1}" x2="{x + 4}" y2="{y1}" '
                   f'stroke="#c0392b" stroke-width="1"/>')
        out.append(f'<line x1="{x - 4}" y1="{y2}" x2="{x + 4}" y2="{y2}" '
                   f'stroke="#c0392b" stroke-width="1"/>')
        out.append(f'<text x="{x + 6}" y="{(y1 + y2) / 2:.1f}" font-size="13" '
                   f'fill="#c0392b">{text}</text>')
    else:
        y = y1 + offset
        out.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" '
                   f'stroke="#c0392b" stroke-width="1"/>')
        out.append(f'<line x1="{x1}" y1="{y - 4}" x2="{x1}" y2="{y + 4}" '
                   f'stroke="#c0392b" stroke-width="1"/>')
        out.append(f'<line x1="{x2}" y1="{y - 4}" x2="{x2}" y2="{y + 4}" '
                   f'stroke="#c0392b" stroke-width="1"/>')
        out.append(f'<text x="{(x1 + x2) / 2:.1f}" y="{y - 6}" font-size="13" '
                   f'fill="#c0392b" text-anchor="middle">{text}</text>')


def layout_svg(path, scale=3.2, margin=90):
    """Чертёж расположения элементов: вид сверху со снятой крышкой.

    Требование пункта 4 задания. Строится из тех же параметров, что и модель,
    поэтому не может разойтись с ней.
    """
    span_x, span_y = P.FLANGE_L, P.FLANGE_W_TOTAL
    width = int(span_x * scale + 2 * margin)
    height = int(span_y * scale + 2 * margin + 150)
    cx = margin + span_x * scale / 2.0
    cy = margin + 40 + span_y * scale / 2.0

    def px(x, y):
        return cx + x * scale, cy - y * scale

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
           f'height="{height}" viewBox="0 0 {width} {height}" '
           f'font-family="DejaVu Sans, Verdana, sans-serif">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           f'<text x="{margin}" y="42" font-size="22" fill="#1d2329">'
           f'BinSense — схема расположения элементов, вид сверху '
           f'(крышка снята)</text>']

    def rect(x, y, w, h, fill, stroke="#41505c", dash=None, r=2):
        px0, py0 = px(x - w / 2.0, y + h / 2.0)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(f'<rect x="{px0:.1f}" y="{py0:.1f}" width="{w * scale:.1f}" '
                   f'height="{h * scale:.1f}" rx="{r}" fill="{fill}" '
                   f'stroke="{stroke}" stroke-width="1.2"{d}/>')

    def circle(x, y, d, fill, stroke="#41505c"):
        px0, py0 = px(x, y)
        out.append(f'<circle cx="{px0:.1f}" cy="{py0:.1f}" '
                   f'r="{d * scale / 2.0:.1f}" fill="{fill}" stroke="{stroke}" '
                   f'stroke-width="1.2"/>')

    def label(x, y, text, anchor="middle", size=13, fill="#1d2329"):
        px0, py0 = px(x, y)
        out.append(f'<text x="{px0:.1f}" y="{py0 + 4:.1f}" font-size="{size}" '
                   f'text-anchor="{anchor}" fill="{fill}">{text}</text>')

    rect(0, 0, P.FLANGE_L, P.FLANGE_W_TOTAL, "#eef1f3", r=14)
    rect(0, 0, P.OUT_L, P.OUT_W, "#e2e7ea", r=8)
    rect(0, 0, P.IN_L, P.IN_W, "#ffffff", r=4)

    for sx, sy in P.SCREW_POINTS:
        circle(sx, sy, P.HOLE_M3 + 1.4, "#ffffff", "#7a838c")

    bx, by = P.BAT_POS
    rect(bx, by, P.BAT_L, P.BAT_W, "#dbe4ea")
    label(bx, by, "держатель 18650 (79 × 21.5 × 20)")

    ex, ey = P.PCB_POS
    rect(ex, ey, P.PCB_L, P.PCB_W, "#d6e8dc")
    label(ex, ey + 4.0, "плата ESP32 LOLIN D32")
    label(ex, ey - 4.0, "50.5 × 25.5, М2 по углам", size=11, fill="#5c666f")
    for hx, hy in [(ex + sx * (P.PCB_L / 2 - P.PCB_HOLE_INSET),
                    ey + sy * (P.PCB_W / 2 - P.PCB_HOLE_INSET))
                   for sx in (-1, 1) for sy in (-1, 1)]:
        circle(hx, hy, P.BOSS_D, "none", "#7a838c")

    sx_, sy_ = P.SENSOR_POS
    circle(sx_, sy_, P.INSERT_FLANGE_D, "none", "#9aa4ad")
    circle(sx_, sy_, P.INSERT_BORE, "#e8f0e9")
    circle(sx_, sy_, P.A02_D, "#cfe0d3")
    label(sx_, sy_ - 12.0, "вставка датчика", size=12)
    label(sx_, sy_ - 20.0, "отв. 30, головка 23", size=11, fill="#5c666f")

    gx, gy = P.SILICA_POS
    rect(gx, gy, P.SILICA_L, P.SILICA_W, "#f3ecda")
    label(gx, gy, "силикагель", size=11)

    wall_x = -P.OUT_L / 2.0
    circle(wall_x, P.BTN_POS[0], P.BTN_BOSS_D, "#fdf0cf")
    label(wall_x - 16.0, P.BTN_POS[0], "кнопка", "end", 12)
    circle(wall_x, P.LED_POS[0], P.LED_BOSS_D, "#e5f2fb")
    label(wall_x - 16.0, P.LED_POS[0], "световод", "end", 12)

    # Зона, которую занимают колодки Dupont над гребёнками, — самая частая
    # причина, по которой корпус приходится переделывать.
    rect(ex, ey, P.PCB_L - 6.0, P.PCB_W + 2.0, "none", "#c0392b", dash="6 4")
    label(ex, ey - 16.0, "габарит колодок Dupont", size=11, fill="#c0392b")

    x_left, y_top = px(-P.FLANGE_L / 2, P.FLANGE_W_TOTAL / 2)
    x_right, _ = px(P.FLANGE_L / 2, 0)
    _, y_bot = px(0, -P.FLANGE_W_TOTAL / 2)
    _dim(out, x_left, y_top, x_right, y_top, f"{P.FLANGE_L:.0f}", offset=-24)
    _dim(out, x_right, y_top, x_right, y_bot, f"{P.FLANGE_W_TOTAL:.0f}",
         offset=22, vertical=True)
    xi_l, yi_t = px(-P.IN_L / 2, P.IN_W / 2)
    xi_r, yi_b = px(P.IN_L / 2, -P.IN_W / 2)
    _dim(out, xi_l, yi_t, xi_r, yi_t, f"внутри {P.IN_L:.0f}", offset=-10)

    legend = [
        f"Стенка {P.WALL} · пол {P.FLOOR} · крышка {P.COVER_T} · "
        f"внутренняя высота {P.IN_H}",
        f"Уплотнитель: шнур {P.GASKET_W}×{P.GASKET_H} в пазу крышки "
        f"{P.GROOVE_W}×{P.GROOVE_D}",
        f"Винты корпуса: {len(P.SCREW_POINTS)} × М3 по фланцу, снаружи "
        f"уплотнительного контура",
        "Датчик смотрит вниз, кнопка и световод — в торцевой стенке −X",
        "Все размеры в миллиметрах. Источник: cad/model/params.py",
    ]
    for i, line in enumerate(legend):
        out.append(f'<text x="{margin}" y="{height - 96 + i * 18}" '
                   f'font-size="13" fill="#41505c">{line}</text>')
    out.append("</svg>")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(out))
    return path
