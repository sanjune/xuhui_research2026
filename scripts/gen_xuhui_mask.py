#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成徐汇区行政边界词云遮罩图。

边界数据来源：高德开放平台行政区划数据（GeoAtlas），徐汇区 adcode=310104。
仅用于词云轮廓示意，不作为界址依据。

输出：
  assets/xuhui_mask.png      遮罩图（黑色形状 + 透明背景）
  assets/xuhui_mask.b64      base64（供 HTML 内联）

遮罩规则（依据 echarts-wordcloud 2.1.0 源码）：
  插件先取 alpha>128 像素的 RGB 平均亮度 s，再筛选「alpha>=128 且 RGB和 <= s」的像素为可用区。
  因此必须是「深色不透明形状 + 全透明背景」——纯黑(0,0,0,255) 形状 + (0,0,0,0) 背景。
  反例：白形状+黑底（alpha全255）会导致判定失效、形状无效。

用法：/usr/bin/python3 scripts/gen_xuhui_mask.py
"""
import base64
import json
import math
import os
import struct
import zlib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(BASE, "data", "geo", "xuhui_district_310104.json")
OUT_PNG = os.path.join(BASE, "assets", "xuhui_mask.png")
OUT_B64 = os.path.join(BASE, "assets", "xuhui_mask.b64")

LONG_SIDE = 600     # 画布长边像素（短边按形状真实比例，紧致裁剪不留白）
SHRINK = 0.97       # 形状相对质心内缩，避免词紧贴边界


def load_rings():
    geo = json.load(open(GEO, encoding="utf-8"))
    geom = geo["features"][0]["geometry"]
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    rings = []
    for poly in polys:
        for ring in poly:
            if len(ring) >= 3:
                rings.append(ring)
    return rings


def project(rings):
    """等距圆柱投影（按质心纬度校正经度尺度）→ 紧致裁剪到画布像素坐标。

    返回 (rings_px, W, H)。画布宽高严格等于形状包围盒比例，
    这样 echarts-wordcloud 的 keepAspect 才能把形状按其真实比例铺满。
    """
    lats = [p[1] for r in rings for p in r]
    lat0 = sum(lats) / len(lats)
    k = math.cos(math.radians(lat0))

    pts = [[(p[0] * k, -p[1]) for p in r] for r in rings]
    xs = [x for r in pts for x, _ in r]
    ys = [y for r in pts for _, y in r]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)

    scale = LONG_SIDE / max(maxx - minx, maxy - miny)   # 长边铺满
    W = max(8, int(round((maxx - minx) * scale)))
    H = max(8, int(round((maxy - miny) * scale)))

    out = [[((x - minx) * scale, (y - miny) * scale) for x, y in r] for r in pts]

    # 绕质心内缩，避免词紧贴边界
    cx = sum(x for r in out for x, _ in r) / sum(len(r) for r in out)
    cy = sum(y for r in out for _, y in r) / sum(len(r) for r in out)
    out = [[(cx + (x - cx) * SHRINK, cy + (y - cy) * SHRINK) for x, y in r] for r in out]
    return out, W, H


def rasterize(rings, W, H):
    """扫描线填充（even-odd），返回逐行 (start, end) 区间列表。"""
    edges = []
    for r in rings:
        n = len(r)
        for i in range(n):
            x1, y1 = r[i]
            x2, y2 = r[(i + 1) % n]
            if y1 != y2:
                edges.append((x1, y1, x2, y2))

    rows = [None] * H
    for py in range(H):
        yc = py + 0.5
        xs = []
        for x1, y1, x2, y2 in edges:
            if (y1 <= yc < y2) or (y2 <= yc < y1):
                t = (yc - y1) / (y2 - y1)
                xs.append(x1 + t * (x2 - x1))
        if not xs:
            continue
        xs.sort()
        spans = []
        for i in range(0, len(xs) - 1, 2):
            ia = max(0, int(math.ceil(xs[i] - 0.5)))
            ib = min(W, int(math.floor(xs[i + 1] - 0.5)))
            if ib > ia:
                spans.append((ia, ib))
        if spans:
            rows[py] = spans
    return rows


def png_bytes(rows, W, H):
    """RGBA PNG：形状=黑(0,0,0,255)，背景=透明(0,0,0,0)。

    必须用「透明背景」区分内外——插件按 alpha>=128 且亮度不超过均值来判可用区，
    若背景不透明会整体失效。
    """
    lines = []
    for py in range(H):
        spans = rows[py] or []
        buf = bytearray()
        cur = 0
        for start, end in spans:
            if start > cur:
                buf += b"\x00\x00\x00\x00" * (start - cur)
            buf += b"\x00\x00\x00\xff" * (end - start)
            cur = end
        if cur < W:
            buf += b"\x00\x00\x00\x00" * (W - cur)
        lines.append(b"\x00" + bytes(buf))
    raw = b"".join(lines)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    rings = load_rings()
    pts, W, H = project(rings)
    rows = rasterize(pts, W, H)
    png = png_bytes(rows, W, H)

    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    open(OUT_PNG, "wb").write(png)
    open(OUT_B64, "w").write(base64.b64encode(png).decode("ascii"))

    filled = sum((e - s) for r in rows if r for s, e in r)
    print(f"✔ {OUT_PNG}  {len(png)/1024:.1f} KB  {W}x{H}  宽高比 {W/H:.3f}")
    print(f"✔ {OUT_B64}  {os.path.getsize(OUT_B64)/1024:.1f} KB (base64)")
    print(f"  形状填充率 {filled/(W*H)*100:.1f}%（圆形为 78.5%）")
    print(f"  环数 {len(pts)} | 顶点 {sum(len(r) for r in pts)}")


if __name__ == "__main__":
    main()
