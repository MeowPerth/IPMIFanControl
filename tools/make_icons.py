#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯标准库生成套件图标（无 PIL / ImageMagick 依赖）。

设计语言与 IP-Monitor-DSM 保持一致：蓝绿渐变圆角底 + 白色图形 + 4x 超采样抗锯齿。
图形为风扇：外环（机箱/护罩）+ 四片扇叶 + 中心轮毂，小尺寸下仍可辨识。

用法：python3 tools/make_icons.py src/ui/images
输出：ipmifan_{16,24,32,48,64,72,256}.png（RGBA）
"""
import math
import os
import struct
import sys
import zlib

SIZES = [16, 24, 32, 48, 64, 72, 256]
SS = 4  # 超采样倍数

C1 = (47, 138, 240)     # 左上：蓝
C2 = (23, 179, 154)     # 右下：青绿
WHITE = (255, 255, 255)


def lerp(a, b, t):
    return a + (b - a) * t


def rounded_rect_sdf(px, py, cx, cy, hw, hh, r):
    """到圆角矩形边缘的有符号距离（负=内部）。"""
    qx = abs(px - cx) - (hw - r)
    qy = abs(py - cy) - (hh - r)
    ox, oy = max(qx, 0.0), max(qy, 0.0)
    return math.hypot(ox, oy) + min(max(qx, qy), 0.0) - r


def seg_dist(px, py, x1, y1, x2, y2):
    """点到线段的距离。"""
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def render(size):
    """按 64 单位设计稿渲染一张 size×size 的 RGBA 图。"""
    s = size * SS
    u = s / 64.0                      # 1 设计单位 = u 像素
    pad = 3.0 * u
    radius = 14.0 * u
    cx = cy = s / 2.0
    img = bytearray(s * s * 4)

    # ---- 几何（64 设计坐标）----
    fc = (32.0, 31.5)                 # 风扇圆心
    ring_r, ring_w = 20.5, 2.4        # 护罩：外半径 / 线宽
    hub_r = 5.0                       # 轮毂
    blade_len = 13.0                  # 扇叶长度（自 hub 起）
    blade_w = 5.4                     # 扇叶宽度
    blade_n = 4
    blade_phase = 20.0                # 扇叶旋转相位（度），形成风车感
    dot_c, dot_r = (32.0, 31.5), 2.0  # 轮毂中心点

    blades = []
    for i in range(blade_n):
        a = math.radians(blade_phase + i * (360.0 / blade_n))
        x1 = fc[0] + math.cos(a) * (hub_r - 1.2)
        y1 = fc[1] + math.sin(a) * (hub_r - 1.2)
        # 扇叶末端向旋转方向偏移，像被气流带动
        a2 = a + math.radians(16.0)
        x2 = fc[0] + math.cos(a2) * (hub_r + blade_len)
        y2 = fc[1] + math.sin(a2) * (hub_r + blade_len)
        blades.append((x1 * u, y1 * u, x2 * u, y2 * u))

    for j in range(s):
        py = j + 0.5
        for i in range(s):
            px = i + 0.5
            # ---- 底板（圆角方形 + 对角渐变）----
            d_bg = rounded_rect_sdf(px, py, cx, cy, s / 2.0 - pad, s / 2.0 - pad, radius)
            if d_bg > 0.75:
                continue
            alpha = 255 if d_bg < -0.75 else int(255 * (0.5 - d_bg / 1.5))
            alpha = max(0, min(255, alpha))
            t = ((px / s) + (py / s)) / 2.0
            cr = lerp(C1[0], C2[0], t)
            cg = lerp(C1[1], C2[1], t)
            cb = lerp(C1[2], C2[2], t)

            # ---- 白色图层：护罩环 / 扇叶 / 轮毂 ----
            cover = 0.0
            d_ring = abs(math.hypot(px - fc[0] * u, py - fc[1] * u)
                         - ring_r * u) - (ring_w / 2.0) * u
            if d_ring <= 0:
                cover = 1.0
            for (x1, y1, x2, y2) in blades:
                if seg_dist(px, py, x1, y1, x2, y2) <= (blade_w / 2.0) * u:
                    cover = 1.0
            if math.hypot(px - fc[0] * u, py - fc[1] * u) <= hub_r * u:
                cover = 1.0

            if cover > 0:
                cr = lerp(cr, WHITE[0], cover)
                cg = lerp(cg, WHITE[1], cover)
                cb = lerp(cb, WHITE[2], cover)

            # ---- 轮毂中心点：用渐变底色挖出来，形成"轴心"效果 ----
            if math.hypot(px - dot_c[0] * u, py - dot_c[1] * u) <= dot_r * u:
                t2 = ((px / s) + (py / s)) / 2.0
                cr = lerp(C1[0], C2[0], t2)
                cg = lerp(C1[1], C2[1], t2)
                cb = lerp(C1[2], C2[2], t2)

            idx = (j * s + i) * 4
            img[idx] = int(cr)
            img[idx + 1] = int(cg)
            img[idx + 2] = int(cb)
            img[idx + 3] = alpha

    # ---- 盒式降采样（4x4 → 1）得到抗锯齿 ----
    out = bytearray(size * size * 4)
    n = SS * SS
    for j in range(size):
        for i in range(size):
            r_ = g_ = b_ = a_ = 0
            for dj in range(SS):
                base = ((j * SS + dj) * s + i * SS) * 4
                for di in range(SS):
                    idx = base + di * 4
                    r_ += img[idx]
                    g_ += img[idx + 1]
                    b_ += img[idx + 2]
                    a_ += img[idx + 3]
            idx = (j * size + i) * 4
            out[idx] = r_ // n
            out[idx + 1] = g_ // n
            out[idx + 2] = b_ // n
            out[idx + 3] = a_ // n
    return bytes(out)


def png_chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path, w, h, rgba):
    raw = b"".join(b"\x00" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    data = (b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(raw, 9))
            + png_chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(data)


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    for size in SIZES:
        path = os.path.join(outdir, "ipmifan_%d.png" % size)
        write_png(path, size, size, render(size))
        print("wrote %s (%d bytes)" % (path, os.path.getsize(path)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "src/ui/images")
