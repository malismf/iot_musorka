"""Примитивы и запись STL.

Тонкая прослойка над manifold3d: все примитивы центрированы по X и Y и растут
вверх от Z = 0 — так позиции деталей читаются как координаты на чертеже.
"""

import numpy as np
from manifold3d import CrossSection, Error, JoinType, Manifold

from . import params as P


# --- 2D ------------------------------------------------------------------

def rrect(length, width, radius, segments=P.SEG):
    """Прямоугольник со скруглёнными углами, центр в начале координат."""
    if radius <= 0:
        return CrossSection.square([length, width], True)
    inner = CrossSection.square([length - 2 * radius, width - 2 * radius], True)
    return inner.offset(radius, JoinType.Round, 2.0, segments)


def rring(length, width, radius, thickness):
    """Замкнутая рамка постоянной толщины по средней линии rrect."""
    half = thickness / 2.0
    outer = rrect(length + thickness, width + thickness, radius + half)
    inner = rrect(length - thickness, width - thickness, max(radius - half, 0.01))
    return outer - inner


# --- 3D ------------------------------------------------------------------

def box(length, width, height):
    """Параллелепипед: центр в XY, основание на Z = 0."""
    return Manifold.cube([length, width, height], False).translate(
        [-length / 2.0, -width / 2.0, 0.0])


def cyl(height, diameter, top_diameter=None, segments=P.SEG):
    """Цилиндр или усечённый конус: ось Z, основание на Z = 0."""
    top = diameter if top_diameter is None else top_diameter
    return Manifold.cylinder(height, diameter / 2.0, top / 2.0, segments, False)


def at(solid, x=0.0, y=0.0, z=0.0):
    return solid.translate([float(x), float(y), float(z)])


def prism(section, height, z=0.0):
    """Выдавливание 2D-контура вверх от заданной высоты."""
    return section.extrude(height).translate([0.0, 0.0, float(z)])


def chamfer_hole(diameter, depth, chamfer=0.6, segments=P.SEG):
    """Отверстие с фаской сверху: снимает первый слой и убирает заусенец."""
    body = cyl(depth, diameter, segments=segments)
    lip = cyl(chamfer, diameter + 2 * chamfer, diameter, segments=segments)
    return body + at(lip, z=depth - chamfer)


def trapezoid_bar(length, base, top, height):
    """Брус трапециевидного сечения вдоль оси X — профиль «ласточкина хвоста»."""
    poly = [[-base / 2.0, 0.0], [base / 2.0, 0.0],
            [top / 2.0, height], [-top / 2.0, height]]
    section = CrossSection([poly])
    bar = section.extrude(length)
    # сечение построено в XY и выдавлено по Z; разворачиваем так, чтобы длина
    # легла на X, ширина — на Y, а высота профиля росла вверх от Z = 0
    bar = bar.rotate([90.0, 0.0, 0.0]).rotate([0.0, 0.0, 90.0])
    return bar.translate([-length / 2.0, 0.0, 0.0])


# --- STL -----------------------------------------------------------------

def triangles(solid):
    """Треугольники детали как массив (N, 3, 3) — общий вход для STL и рендера."""
    mesh = solid.to_mesh()
    verts = np.asarray(mesh.vert_properties)[:, :3].astype(np.float64)
    faces = np.asarray(mesh.tri_verts).astype(np.int64)
    return verts[faces]


def write_stl(solid, path, name="binsense"):
    """Двоичный STL. Нормали считаются заново по обходу против часовой стрелки."""
    tri = triangles(solid)
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    length[length == 0.0] = 1.0
    normals = normals / length

    count = len(tri)
    block = np.empty((count, 12), dtype=np.float32)
    block[:, 0:3] = normals
    block[:, 3:12] = tri.reshape(-1, 9)
    records = np.zeros((count, 50), dtype=np.uint8)
    records[:, 0:48] = block.view(np.uint8).reshape(count, 48)

    header = f"binsense {name}".encode("ascii", "replace")[:79].ljust(80, b" ")
    with open(path, "wb") as handle:
        handle.write(header)
        handle.write(np.uint32(count).tobytes())
        handle.write(records.tobytes())
    return count


def check(solid, name):
    """Проверка перед экспортом: деталь непуста, замкнута и одним куском."""
    problems = []
    if solid.is_empty():
        problems.append("пустая геометрия")
    if solid.status() != Error.NoError:
        problems.append(f"status={solid.status()}")
    if solid.volume() <= 0.0:
        problems.append("нулевой объём")
    pieces = len(solid.decompose())
    if pieces > 1:
        problems.append(f"деталь распалась на {pieces} кусков")
    return name, solid.volume(), pieces, problems
