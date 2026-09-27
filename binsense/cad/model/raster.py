"""Растеризация сцены в PNG без внешних библиотек.

SVG с рендером весит пару мегабайт: каждый треугольник — отдельный полигон.
Для презентации и пояснительной записки нужна картинка, а не вектор, поэтому
те же треугольники заливаются сразу в растр: PNG выходит в десять раз меньше
и вставляется куда угодно.
"""

import struct
import zlib

import numpy as np


def write_png(path, image):
    """Сохранение массива (H, W, 3) uint8 в PNG без сжатия с потерями."""
    height, width, _ = image.shape
    raw = b"".join(b"\x00" + image[y].tobytes() for y in range(height))

    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(chunk(b"IHDR", header))
        handle.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        handle.write(chunk(b"IEND", b""))


def fill_triangles(image, tri2d, colors, supersample=1):
    """Заливка треугольников в порядке следования (дальние идут первыми).

    tri2d — (N, 3, 2) в пикселях, colors — (N, 3) uint8.
    """
    height, width, _ = image.shape
    xs = tri2d[:, :, 0]
    ys = tri2d[:, :, 1]
    x0 = np.clip(np.floor(xs.min(axis=1)).astype(int), 0, width)
    x1 = np.clip(np.ceil(xs.max(axis=1)).astype(int) + 1, 0, width)
    y0 = np.clip(np.floor(ys.min(axis=1)).astype(int), 0, height)
    y1 = np.clip(np.ceil(ys.max(axis=1)).astype(int) + 1, 0, height)

    for i in range(len(tri2d)):
        if x1[i] <= x0[i] or y1[i] <= y0[i]:
            continue
        ax, ay = tri2d[i, 0]
        bx, by = tri2d[i, 1]
        cx, cy = tri2d[i, 2]
        area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if abs(area) < 1e-9:
            continue
        yy, xx = np.mgrid[y0[i]:y1[i], x0[i]:x1[i]]
        px = xx + 0.5
        py = yy + 0.5
        w0 = ((bx - ax) * (py - ay) - (px - ax) * (by - ay)) / area
        w1 = ((cx - bx) * (py - by) - (px - bx) * (cy - by)) / area
        w2 = 1.0 - w0 - w1
        # Небольшой допуск закрывает щели между соседними треугольниками.
        mask = (w0 >= -0.004) & (w1 >= -0.004) & (w2 >= -0.004)
        if mask.any():
            image[y0[i]:y1[i], x0[i]:x1[i]][mask] = colors[i]


def downsample(image, factor):
    """Усреднение по блокам: дешёвое сглаживание краёв."""
    if factor <= 1:
        return image
    height, width, _ = image.shape
    height -= height % factor
    width -= width % factor
    block = image[:height, :width].astype(np.uint16)
    block = block.reshape(height // factor, factor, width // factor, factor, 3)
    return block.mean(axis=(1, 3)).astype(np.uint8)
