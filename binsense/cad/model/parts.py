"""Детали корпуса BinSense.

Система координат: начало — центр внутренней площадки пола, X вдоль корпуса,
Y поперёк, Z вверх. Пол занимает Z от −FLOOR до 0, стенки — до Z = IN_H.
Каждая функция возвращает деталь в той ориентации, в какой она стоит в сборке;
для печати build.py доворачивает их отдельно.
"""

from manifold3d import Manifold

from . import params as P
from .solid import (at, box, chamfer_hole, cyl, prism, rrect, rring,
                    trapezoid_bar)


# --- вспомогательное ------------------------------------------------------

def _screw_holes(diameter, z_from, z_to):
    """Шесть отверстий по контуру фланца."""
    holes = None
    for x, y in P.SCREW_POINTS:
        hole = at(cyl(z_to - z_from, diameter), x, y, z_from)
        holes = hole if holes is None else holes + hole
    return holes


def _groove_ring(width):
    """Кольцо уплотнительного паза по средней линии."""
    return rring(P.IN_L + 2 * P.GROOVE_OFF, P.IN_W + 2 * P.GROOVE_OFF,
                 P.IN_R + P.GROOVE_OFF, width)


def _pcb_hole_xy():
    cx, cy = P.PCB_POS
    dx = P.PCB_L / 2.0 - P.PCB_HOLE_INSET
    dy = P.PCB_W / 2.0 - P.PCB_HOLE_INSET
    return [(cx + sx * dx, cy + sy * dy) for sx in (-1, 1) for sy in (-1, 1)]


# --- 1. Основание ---------------------------------------------------------

def body():
    """Основание: стенки, пол, фланец под уплотнитель, крепёж платы и батареи."""
    # Оболочка и фланец. Между ними — конус под 45 градусов, чтобы фланец и
    # бобышки винтов печатались без поддержек и не отламывались от стенки.
    shell = prism(rrect(P.OUT_L, P.OUT_W, P.CORNER_R), P.FLOOR + P.IN_H, -P.FLOOR)
    z_flange = P.IN_H - P.FLANGE_H
    taper = Manifold.batch_hull([
        prism(rrect(P.OUT_L, P.OUT_W, P.CORNER_R), 0.01, z_flange - P.FLANGE_W),
        prism(rrect(P.FLANGE_L, P.FLANGE_W_TOTAL, P.FLANGE_R), 0.01, z_flange),
    ])
    flange = prism(rrect(P.FLANGE_L, P.FLANGE_W_TOTAL, P.FLANGE_R),
                   P.FLANGE_H, z_flange)
    solid = shell + taper + flange

    # Внутренняя полость.
    solid = solid - prism(rrect(P.IN_L, P.IN_W, P.IN_R), P.IN_H + 1.0, 0.0)

    # Бобышки платы ESP32: просвет BOSS_H под пайку и разводку проводов.
    for x, y in _pcb_hole_xy():
        solid = solid + at(cyl(P.BOSS_H, P.BOSS_D), x, y, 0.0)
    for x, y in _pcb_hole_xy():
        solid = solid - at(chamfer_hole(P.HOLE_M2, P.BOSS_H + P.FLOOR - 0.6),
                           x, y, -P.FLOOR + 0.6)

    # Рёбра вокруг держателя 18650 с окнами: под шлейф JST и под палец,
    # чтобы аккумулятор вынимался, не снимая держатель.
    bx, by = P.BAT_POS
    fence = at(prism(rring(P.BAT_L + P.BAT_FENCE_T, P.BAT_W + P.BAT_FENCE_T,
                           2.0, P.BAT_FENCE_T), P.BAT_FENCE_H), bx, by)
    gap = P.BAT_L / 2.0 + P.BAT_FENCE_T
    fence = fence - at(box(4.0, 14.0, 20.0), bx - gap, by, -1.0)
    fence = fence - at(box(4.0, 14.0, 20.0), bx + gap, by, -1.0)
    fence = fence - at(box(34.0, 6.0, 20.0), bx, by - P.BAT_W / 2.0 - 1.0, -1.0)
    solid = solid + fence

    # Отсек под пакетик силикагеля.
    sx, sy = P.SILICA_POS
    solid = solid + at(prism(rring(P.SILICA_L + P.BAT_FENCE_T,
                                   P.SILICA_W + P.BAT_FENCE_T, 1.5,
                                   P.BAT_FENCE_T), P.SILICA_FENCE_H), sx, sy)

    # Отверстие под вставку датчика.
    solid = solid - at(cyl(P.FLOOR + 2.0, P.INSERT_BORE),
                       P.SENSOR_POS[0], P.SENSOR_POS[1], -P.FLOOR - 1.0)

    # Кнопка и световод — в торцевой стенке −X: крышка прижата к крышке
    # контейнера, сверху до них не дотянуться.
    wall_x = -P.OUT_L / 2.0
    for (y, z), boss_d, boss_h, hole_d in (
            (P.BTN_POS, P.BTN_BOSS_D, P.BTN_BOSS_H, P.BTN_D + P.FIT_FREE),
            (P.LED_POS, P.LED_BOSS_D, P.LED_BOSS_H, P.LED_D + P.FIT_FREE)):
        boss = cyl(P.WALL + boss_h, boss_d).rotate([0.0, 90.0, 0.0])
        solid = solid + at(boss, wall_x, y, z)
        bore = cyl(P.WALL + boss_h + 4.0, hole_d).rotate([0.0, 90.0, 0.0])
        solid = solid - at(bore, wall_x - 2.0, y, z)

    # Паз уплотнителя — на фланце основания, а не в крышке: так обе половины
    # печатаются без поддержек, а шнур при сборке лежит в пазу сам.
    solid = solid - prism(_groove_ring(P.GROOVE_W), P.GROOVE_D,
                          P.IN_H - P.GROOVE_D)

    # Отверстия под винты корпуса — снаружи уплотнительного контура.
    solid = solid - _screw_holes(P.HOLE_M3, P.IN_H - 10.0, P.IN_H + 1.0)
    return solid


# --- 2. Крышка ------------------------------------------------------------

def cover():
    """Крышка: плита, «ласточкин хвост» и окно защёлки.

    Низ крышки — ровная плоскость: она ложится на шнур уплотнителя, а паз
    сделан в основании. Крышка печатается плитой на стол, «хвост» уходит
    вверх свесом 31 градус и обходится без поддержек.
    """
    z0 = P.IN_H
    plate = prism(rrect(P.FLANGE_L, P.FLANGE_W_TOTAL, P.FLANGE_R), P.COVER_T, z0)
    rail = at(trapezoid_bar(P.FLANGE_L, P.DT_BASE, P.DT_TOP, P.DT_H),
              0.0, 0.0, z0 + P.COVER_T)
    solid = plate + rail

    # Окно под зуб защёлки кронштейна.
    solid = solid - at(box(P.DT_NOTCH_L, P.DT_NOTCH_W, P.DT_NOTCH_D + 1.0),
                       P.DT_NOTCH_X, 0.0,
                       z0 + P.COVER_T + P.DT_H - P.DT_NOTCH_D)

    solid = solid - _screw_holes(P.CLEAR_M3, z0 - 1.0, z0 + P.COVER_T + 1.0)
    solid = solid - _screw_holes(P.HEAD_M3, z0 + P.COVER_T - 1.6,
                                 z0 + P.COVER_T + 1.0)
    return solid


# --- 3. Уплотнитель -------------------------------------------------------

def gasket():
    """Шнур TPU по контуру паза. Печатается лёжа, одной петлёй."""
    return prism(_groove_ring(P.GASKET_W), P.GASKET_H, P.IN_H)


# --- 4. Вставка под датчик ------------------------------------------------

def _insert_spigot(z_base):
    """Хвостовик с защёлкой, общий для обоих вариантов вставки."""
    top = z_base + P.FLOOR + 2.5
    stem = at(cyl(top - z_base, P.INSERT_BORE - 2 * P.FIT_PRESS), 0.0, 0.0, z_base)
    # Барб: широкой стороной вниз, чтобы при насадке лепестки сжимались, а
    # плоская площадка легла на пол изнутри.
    barb_z = z_base + P.FLOOR + 0.2
    barb = at(cyl(top - barb_z, P.INSERT_BORE + 1.4,
                  P.INSERT_BORE - 2 * P.FIT_PRESS), 0.0, 0.0, barb_z)
    solid = stem + barb
    for angle in (45.0, 135.0, 225.0, 315.0):
        slot = box(2.0, P.INSERT_BORE + 6.0, top - z_base + 2.0)
        solid = solid - at(slot.rotate([0.0, 0.0, angle]), 0.0, 0.0, z_base - 1.0)
    return solid


def sensor_insert_a02():
    """Вставка под A02YYUW/JSN-SR04T: гнездо с плотной посадкой без люфта."""
    skirt = cyl(P.INSERT_SKIRT, P.INSERT_BORE)
    # Конус вместо прямого выступа: фланец печатается без поддержек.
    taper = at(cyl(4.0, P.INSERT_BORE, P.INSERT_FLANGE_D), 0.0, 0.0,
               P.INSERT_SKIRT - 4.0)
    skirt = skirt + taper
    flange = at(cyl(P.INSERT_FLANGE_T, P.INSERT_FLANGE_D), 0.0, 0.0, P.INSERT_SKIRT)
    z_base = P.INSERT_SKIRT + P.INSERT_FLANGE_T
    solid = skirt + flange + _insert_spigot(z_base)
    # Гнездо головки: сверху, на всю оставшуюся высоту — кабель выходит внутрь.
    seat_z = P.INSERT_SKIRT - 4.0
    solid = solid - at(cyl(30.0, P.A02_D + P.FIT_PRESS), 0.0, 0.0, seat_z)
    # Акустическое окно и раструб: фаска не сужает луч.
    solid = solid - cyl(seat_z + 0.1, P.A02_D - 5.0)
    solid = solid - cyl(2.5, P.A02_D - 1.0, P.A02_D - 5.0)
    return solid


def sensor_insert_hcsr04():
    """Вставка под HC-SR04: два гнезда «глаз», тот же хвостовик и то же
    отверстие в полу — прототип ставится в штатный корпус без переделок."""
    span = P.SRF_PITCH + P.SRF_D + 6.0
    skirt = prism(rrect(span, P.SRF_D + 6.0, (P.SRF_D + 6.0) / 2.0),
                  P.INSERT_SKIRT, 0.0)
    skirt = skirt + Manifold.batch_hull([
        prism(rrect(span, P.SRF_D + 6.0, (P.SRF_D + 6.0) / 2.0), 0.01,
              P.INSERT_SKIRT - 4.0),
        prism(rrect(span + 8.0, P.SRF_D + 14.0, (P.SRF_D + 14.0) / 2.0), 0.01,
              P.INSERT_SKIRT),
    ])
    flange = prism(rrect(span + 8.0, P.SRF_D + 14.0, (P.SRF_D + 14.0) / 2.0),
                   P.INSERT_FLANGE_T, P.INSERT_SKIRT)
    z_base = P.INSERT_SKIRT + P.INSERT_FLANGE_T
    solid = skirt + flange + _insert_spigot(z_base)
    for sign in (-1.0, 1.0):
        solid = solid - at(cyl(P.INSERT_SKIRT + 2.0, P.SRF_D + P.FIT_PRESS),
                           sign * P.SRF_PITCH / 2.0, 0.0, -1.0)
    # Проход кабеля и выводов в корпус.
    solid = solid - at(cyl(20.0, P.INSERT_BORE - 10.0), 0.0, 0.0,
                       P.INSERT_SKIRT - 2.0)
    return solid


# --- 5. Кронштейн ---------------------------------------------------------

def bracket():
    """Кронштейн на крышку контейнера: паз «ласточкина хвоста» и защёлка.

    Печатается пазом вверх (как смоделирован), ставится перевёрнутым: плита
    прилегает к крышке контейнера, устройство вдвигается снизу.
    """
    plate = prism(rrect(P.BRK_L, P.BRK_W + 6.0, 5.0), P.BRK_T, 0.0)
    block = prism(rrect(P.BRK_L, P.BRK_W - 6.0, 5.0), P.DT_H + 3.0, P.BRK_T)
    solid = plate + block

    channel = at(trapezoid_bar(P.BRK_L + 20.0, P.DT_BASE + 2 * P.FIT_SLIDE,
                               P.DT_TOP + 2 * P.FIT_SLIDE, P.DT_H + P.FIT_SLIDE),
                 0.0, 0.0, P.BRK_T)
    solid = solid - channel

    # Консоль защёлки: две прорези вдоль, зуб с заходной фаской.
    z_ceil = P.BRK_T + P.DT_H + P.FIT_SLIDE
    slot_len = P.LATCH_L + 6.0
    slot_x = -P.BRK_L / 2.0 + slot_len / 2.0 - 1.0
    for sign in (-1.0, 1.0):
        solid = solid - at(box(slot_len, 2.0, 6.0), slot_x, sign * 5.0, z_ceil)
    tooth = Manifold.batch_hull([
        at(box(2.0, 8.0, 0.01), 0.0, 0.0, z_ceil - P.LATCH_TOOTH),
        at(box(8.0, 8.0, 0.01), 0.0, 0.0, z_ceil + 0.5),
    ])
    solid = solid + at(tooth, P.DT_NOTCH_X, 0.0, 0.0)

    # Винты М3 в крышку контейнера — в «ушах», мимо паза: отвёртка подходит
    # до того, как устройство вдвинуто.
    hx, hy = P.BRK_HOLE
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            solid = solid - at(cyl(P.BRK_T + 2.0, P.CLEAR_M3), sx * hx, sy * hy, -1.0)
            solid = solid - at(cyl(2.0, P.HEAD_M3), sx * hx, sy * hy, P.BRK_T - 2.0)
    return solid


# --- 6. Толкатель кнопки --------------------------------------------------

def button_cap():
    """Толкатель кнопки: печатается из TPU целиком.

    Уплотнение — коническая юбка на стержне, а не отдельное кольцо: юбка
    прижимается к бобышке изнутри, и чем сильнее давят на кнопку, тем плотнее
    она садится. Толкатель внутри упирается в тактовую кнопку 6х6 на шилде.
    """
    stem = cyl(P.CAP_H, P.BTN_D - P.FIT_FREE)
    head = at(cyl(2.0, P.CAP_FLANGE_D - 1.0, P.CAP_FLANGE_D - 3.0),
              0.0, 0.0, P.CAP_H)
    boot_h = P.CAP_FLANGE_T + 1.0
    boot = cyl(boot_h, P.CAP_FLANGE_D + 1.6, P.BTN_D - P.FIT_FREE)
    cavity = cyl(boot_h + 0.1, P.CAP_FLANGE_D + 1.6 - 2 * P.CAP_SKIRT_T,
                 P.BTN_D - P.FIT_FREE - 2 * P.CAP_SKIRT_T)
    solid = (stem + head + boot) - at(cavity, 0.0, 0.0, -0.1)
    # Толкатель добавляется после выборки юбки, иначе он повисал бы в воздухе.
    return solid + at(cyl(5.0 + boot_h, 4.0), 0.0, 0.0, -3.0)


# --- 7. Световод ----------------------------------------------------------

def light_pipe():
    """Световод: конус-собиратель над светодиодом, рассеивающий торец наружу."""
    rod = cyl(P.PIPE_H, P.LED_D - P.FIT_FREE)
    flange = cyl(P.PIPE_FLANGE_T, P.PIPE_FLANGE_D)
    tip = at(cyl(1.5, P.LED_D - P.FIT_FREE, P.LED_D - 2.0), 0.0, 0.0, P.PIPE_H)
    solid = rod + flange + tip
    return solid - cyl(3.0, P.LED_D, 0.001)


PARTS = {
    "body": body,
    "cover": cover,
    "gasket": gasket,
    "sensor_insert_a02yyuw": sensor_insert_a02,
    "sensor_insert_hcsr04": sensor_insert_hcsr04,
    "bracket": bracket,
    "button_cap": button_cap,
    "light_pipe": light_pipe,
}
