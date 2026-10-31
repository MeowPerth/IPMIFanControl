#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把作者原始 logo（src/ui/images/icon_256.png）缩放出其余尺寸。

**只做缩放，不改设计**：所有产出都是原图的等比缩小，用于 DSM 在不同位置
（列表 16/24、磁贴 32/48/64）按 `icon_{0}.png` 取图。
72 与 256 两张为作者原始素材，脚本不会覆盖它们。

用法：python3 tools/resize_icons.py [输出目录]
"""
import os
import struct
import sys
import zlib

SIZES = (16, 24, 32, 48, 64)          # 由 icon_256.png 派生
SOURCE = "icon_256.png"


# --------------------------------------------------------------------- PNG 读写
def read_png(path):
    """读取 8-bit RGB/RGBA 非隔行 PNG → (w, h, bytearray RGBA)。"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是 PNG：%s" % path)
    pos, idat, w = 8, b"", 0
    h = depth = ctype = interlace = 0
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", payload)
        elif tag == b"IDAT":
            idat += payload
        elif tag == b"IEND":
            break
    if depth != 8 or interlace != 0 or ctype not in (2, 6):
        raise ValueError("仅支持 8-bit RGB/RGBA 非隔行 PNG：%s" % path)

    channels = 4 if ctype == 6 else 3
    raw = zlib.decompress(idat)
    stride = w * channels
    prev = bytearray(stride)
    out = bytearray(w * h * 4)
    p = 0
    for y in range(h):
        ftype = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if ftype == 1:                      # Sub
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ftype == 2:                    # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:                    # Average
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:                    # Paeth
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        prev = line

        base = y * w * 4
        for x in range(w):
            s = x * channels
            d = base + x * 4
            out[d] = line[s]
            out[d + 1] = line[s + 1]
            out[d + 2] = line[s + 2]
            out[d + 3] = line[s + 3] if channels == 4 else 255
    return w, h, out


def png_chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path, w, h, rgba):
    raw = b"".join(b"\x00" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n"
                + png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + png_chunk(b"IDAT", zlib.compress(raw, 9))
                + png_chunk(b"IEND", b""))


# --------------------------------------------------------------------- 缩放
def resize_area(rgba, w, h, nw, nh):
    """面积平均（box）缩放：按源矩形的覆盖比例加权，缩小后仍然锐利。"""
    out = bytearray(nw * nh * 4)
    x_ratio, y_ratio = w / nw, h / nh
    for dy in range(nh):
        y0, y1 = dy * y_ratio, (dy + 1) * y_ratio
        sy0, sy1 = int(y0), min(h, int(y1) + 1)
        for dx in range(nw):
            x0, x1 = dx * x_ratio, (dx + 1) * x_ratio
            sx0, sx1 = int(x0), min(w, int(x1) + 1)
            acc = [0.0, 0.0, 0.0, 0.0]
            total = 0.0
            for sy in range(sy0, sy1):
                yw = min(y1, sy + 1) - max(y0, sy)
                if yw <= 0:
                    continue
                for sx in range(sx0, sx1):
                    xw = min(x1, sx + 1) - max(x0, sx)
                    if xw <= 0:
                        continue
                    weight = xw * yw
                    idx = (sy * w + sx) * 4
                    for k in range(4):
                        acc[k] += rgba[idx + k] * weight
                    total += weight
            idx = (dy * nw + dx) * 4
            if total:
                for k in range(4):
                    out[idx + k] = int(acc[k] / total + 0.5)
    return out


def main(outdir):
    src = os.path.join(outdir, SOURCE)
    w, h, rgba = read_png(src)
    for size in SIZES:
        path = os.path.join(outdir, "icon_%d.png" % size)
        write_png(path, size, size, resize_area(rgba, w, h, size, size))
        print("wrote %s (%d bytes)" % (path, os.path.getsize(path)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "src/ui/images")
