#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_monthly_collection.py — 重建《数据分析月报合集》月度榜单 + 2026 年逐月明细

问题背景
--------
1. 页面内 `const monthlyData` 的 streets / comms / cats / issues 四组榜单为早期手填的
   示例值，与热线工单主数据（`data/merged_cleaned.pkl`）逐月核对 **32/32 月全部不符**
   （如 2024-01 页面写「长桥 275 件」，实际 307 件；2026-07 写「长桥 275 件」，实际 214 件）；
   「热点问题」根本没有对应字段来源。
2. `detail-panel` 的四张榜表由页面 JS 运行时填充（`<ul>` 初始为空），
   导出 Word 时四条小标题下面没有任何内容。
3. JS 里 `data.streets` 同时被当「覆盖街道数」和「街道榜单数组」用（对象字面量后键覆盖前键），
   「覆盖街道数」实际渲染成了数组字符串。
4. 折线图的 y 坐标与标注值不符（「谷值 888」落在 viewBox 之外，被裁掉）。

本脚本做什么
------------
1. 用主数据重算 32 个月的四组榜单，口径：
     streets  街道投诉排名 Top5     （`street` 字段，剔除空值与「无」归属）
     comms    小区投诉排名 Top10    （`community_name` + 当月所属街道）
     cats     投诉类别分布 Top5     （`level2` 市级归口）
     issues   热点问题 Top5         （`level4` 市局细分）
   并同时保证 `total` / `comm` 与主数据一致。
2. 回填 `monthlyData` 块（标记 `MD-DATA-BEGIN/END`），修正 JS 的 `nstreet` 取值。
3. 生成「2026 年逐月明细」静态区（8 节 × 4 张表，标记 `MD-DETAIL-BEGIN/END`），
   供 Word 导出；原 `detail-panel` 加 `no-print`（网页保留点击交互，Word 用静态明细）。
4. 按真实数据重建「一、投诉量月度趋势总览」折线图几何。

口径
----
· 全量口径（按热线工单字段统计，不排除「其他」），与全站「街道/类别统计用全量 df」一致
· 占比 = 该单位当月投诉量 ÷ 当月全区投诉总量
· 榜内并列时按投诉量降序，同值按名称升序（保证可复现）

用法
----
    PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/gen_monthly_collection.py
    ... --check     只体检不改文件
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import datetime

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKL = os.path.join(ROOT, "data", "merged_cleaned.pkl")
HTML = os.path.join(ROOT, "数据分析月报合集.html")

M_DB = "<!-- MD-DATA-BEGIN -->"
M_DE = "<!-- MD-DATA-END -->"
M_TB = "<!-- MD-DETAIL-BEGIN -->"
M_TE = "<!-- MD-DETAIL-END -->"
M_SB = "<!-- MD-SVG-BEGIN -->"
M_SE = "<!-- MD-SVG-END -->"

TOP_STREET, TOP_COMM, TOP_CAT, TOP_ISSUE = 5, 10, 5, 5


# ─────────────────────────────────── 数据
def load() -> pd.DataFrame:
    df = pd.read_pickle(PKL)
    df["street"] = df["street"].fillna("").astype(str).str.strip()
    df["community_name"] = df["community_name"].fillna("").astype(str).str.strip()
    df["level2"] = df["level2"].fillna("").astype(str).str.strip()
    df["level4"] = df["level4"].fillna("").astype(str).str.strip()
    return df


def rank(series, topn):
    """按「数量降序、名称升序」返回 [[名称, 数量], ...]（同值排序稳定可复现）。"""
    vc = series.value_counts()
    items = [(str(k), int(v)) for k, v in vc.items() if str(k).strip()]
    items.sort(key=lambda x: (-x[1], x[0]))
    return [[k, v] for k, v in items[:topn]]


def build(df: pd.DataFrame) -> dict:
    keys = sorted({(int(y), int(m)) for y, m in zip(df["year"], df["month"])})
    street_of = (df[df["street"] != ""]
                 .groupby("community_name")["street"]
                 .agg(lambda s: s.mode().iat[0] if len(s.mode()) else "")
                 .to_dict())
    out = {}
    for i, (y, m) in enumerate(keys):
        cur = df[(df["year"] == y) & (df["month"] == m)]
        prev = df[(df["year"] == y) & (df["month"] == m - 1)] if m > 1 else None
        base = df[(df["year"] == y - 1) & (df["month"] == m)]
        total = len(cur)
        st = cur[cur["street"] != "无"]      # 归属为空的工单不进街道榜（与全站口径一致）
        out["%04d-%02d" % (y, m)] = {
            "total": total,
            # 有小区名的工单数（空名不计，与页面月份卡的「涉及 N 个小区」同口径）
            "comm": int(cur.loc[cur["community_name"] != "", "community_name"].nunique()),
            "nstreet": int(st["street"].nunique()),
            "mom": round((total - len(prev)) / len(prev) * 100, 1) if prev is not None and len(prev) else None,
            "yoy": round((total - len(base)) / len(base) * 100, 1) if len(base) else None,
            "streets": rank(st["street"], TOP_STREET),
            "comms": [[n, c, street_of.get(n, "")] for n, c in rank(cur["community_name"], TOP_COMM)],
            "cats": rank(cur["level2"], TOP_CAT),
            "issues": rank(cur["level4"], TOP_ISSUE),
        }
    return out


# ─────────────────────────────────── 片段生成
def js_num(v):
    return "null" if v is None else ("%g" % v)


def js_arr(rows, quoted=True):
    inner = []
    for r in rows:
        parts = []
        for x in r:
            parts.append("'%s'" % x.replace("'", "\\'") if isinstance(x, str) else str(x))
        inner.append("[%s]" % ",".join(parts))
    return "[" + ",".join(inner) + "]"


def gen_data_block(D) -> str:
    L = [M_DB, "const monthlyData = {"]
    ks = sorted(D)
    for i, k in enumerate(ks):
        d = D[k]
        tail = "," if i < len(ks) - 1 else ""
        L.append("  '%s': { total:%d, comm:%d, nstreet:%d, yoy:%s, mom:%s,"
                 % (k, d["total"], d["comm"], d["nstreet"], js_num(d["yoy"]), js_num(d["mom"])))
        L.append("    streets:%s," % js_arr(d["streets"]))
        L.append("    comms:%s," % js_arr(d["comms"]))
        L.append("    cats:%s," % js_arr(d["cats"]))
        L.append("    issues:%s }%s" % (js_arr(d["issues"]), tail))
    L.append("};")
    L.append(M_DE)
    return "\n".join(L)


def table(rows, heads, note=None):
    """标准 data-table 片段（首行即真表头，无表题行）。"""
    L = ['    <table class="data-table">',
         '      <thead><tr>%s</tr></thead>' % "".join("<th>%s</th>" % h for h in heads),
         '      <tbody>']
    for r in rows:
        L.append('        <tr>%s</tr>' % "".join("<td>%s</td>" % c for c in r))
    L.append('      </tbody></table>')
    if note:
        L.append('    <div class="table-note">%s</div>' % note)
    return "\n".join(L)


def gen_detail_section(D, year=2026, upto=8) -> str:
    ks = [k for k in sorted(D) if k.startswith("%d-" % year) and int(k[5:]) <= upto]
    tot = sum(D[k]["total"] for k in ks)
    L = [M_TB,
         '  <!-- ===== 逐月明细（静态，供 Word 导出） ===== -->',
         '  <div class="section" id="sec-year-detail">',
         '    <div class="section-title"><span class="icon">🗂️</span>'
         '三、%d 年逐月明细（1-%d 月）</div>' % (year, upto),
         '    <p class="desc">下表按月列出 %d 年 1-%d 月各月的街道投诉排名 Top%d、'
         '小区投诉排名 Top%d、投诉类别分布 Top%d、热点问题 Top%d。'
         '口径：热线工单主数据全量口径，当月独立统计；占比＝该单位当月投诉量 ÷ 当月全区投诉总量。'
         '%d 年 1-%d 月合计 %s 件。</p>'
         % (year, upto, TOP_STREET, TOP_COMM, TOP_CAT, TOP_ISSUE, year, upto, format(tot, ","))]
    for k in ks:
        d = D[k]
        y, m = int(k[:4]), int(k[5:])
        L.append('    <h3>%d 年 %d 月</h3>' % (y, m))
        L.append('    <p class="desc">投诉总量 <b>%s</b> 件 ｜ 涉及小区 <b>%d</b> 个 ｜ '
                 '覆盖街道 <b>%d</b> 个 ｜ 环比 <b>%s</b> ｜ 同比 <b>%s</b></p>'
                 % (format(d["total"], ","), d["comm"], d["nstreet"],
                    ("%+.1f%%" % d["mom"]) if d["mom"] is not None else "—",
                    ("%+.1f%%" % d["yoy"]) if d["yoy"] is not None else "—"))

        L.append('    <h4>街道投诉排名 Top%d</h4>' % TOP_STREET)
        L.append(table([[i + 1, n, format(v, ","), "%.1f%%" % (v / d["total"] * 100)]
                        for i, (n, v) in enumerate(d["streets"])],
                       ["排名", "街道", "投诉量（件）", "占当月比"]))

        L.append('    <h4>小区投诉排名 Top%d</h4>' % TOP_COMM)
        L.append(table([[i + 1, n, st or "—", format(v, ","), "%.1f%%" % (v / d["total"] * 100)]
                        for i, (n, v, st) in enumerate(d["comms"])],
                       ["排名", "小区", "所属街道", "投诉量（件）", "占当月比"]))

        L.append('    <h4>投诉类别分布 Top%d</h4>' % TOP_CAT)
        L.append(table([[i + 1, n, format(v, ","), "%.1f%%" % (v / d["total"] * 100)]
                        for i, (n, v) in enumerate(d["cats"])],
                       ["排名", "类别（市级归口）", "投诉量（件）", "占当月比"]))

        L.append('    <h4>热点问题 Top%d</h4>' % TOP_ISSUE)
        L.append(table([[i + 1, n, format(v, ","), "%.1f%%" % (v / d["total"] * 100)]
                        for i, (n, v) in enumerate(d["issues"])],
                       ["排名", "热点问题（市局细分）", "投诉量（件）", "占当月比"]))
    L.append('  </div>')
    L.append(M_TE)
    return "\n".join(L)


def gen_trend_svg(D) -> str:
    """按真实月度数据重建折线图几何。y 轴刻度沿用原图：y = 304 - (val-1000)*0.13。"""
    ks = sorted(D)
    vals = [D[k]["total"] for k in ks]
    n = len(ks)
    x0, x1 = 65.0, 950.0
    yv = lambda v: 304 - (v - 1000) * 0.13
    xs = [x0 + i * (x1 - x0) / (n - 1) for i in range(n)]
    pts = [(round(x, 1), round(yv(v), 1)) for x, v in zip(xs, vals)]
    line = "M " + " L ".join("%s,%s" % p for p in pts)
    area = line + " L %s,300 L %s,300 Z" % (pts[-1][0], pts[0][0])
    ipk = vals.index(max(vals))
    ivl = vals.index(min(vals))
    year_x = {"2024": (xs[0] + xs[11]) / 2, "2025": (xs[12] + xs[23]) / 2,
              "2026": (xs[24] + xs[-1]) / 2}
    div1, div2 = (xs[12] + xs[11]) / 2, (xs[24] + xs[23]) / 2

    L = []
    L.append('      <svg viewBox="0 0 1000 396" class="trend-svg" role="img" '
             'aria-label="%s—%s 月度投诉量折线图">' % (ks[0], ks[-1]))
    L.append('        <!-- 网格与坐标轴 -->')
    L.append('        <line x1="50" y1="40" x2="50" y2="330" stroke="#eee" stroke-width="1"/>')
    L.append('        <line x1="50" y1="330" x2="960" y2="330" stroke="#ccc" stroke-width="1"/>')
    for lab in (3000, 2500, 2000, 1500, 1000):
        y = round(yv(lab), 1)
        L.append('        <line x1="50" y1="%s" x2="960" y2="%s" stroke="#f0f0f0" '
                 'stroke-width="1" stroke-dasharray="4,4"/>' % (y, y))
        L.append('        <text x="45" y="%s" text-anchor="end" font-size="10" fill="#999">%d</text>'
                 % (round(y + 4, 1), lab))
    L.append('        <line x1="%s" y1="35" x2="%s" y2="335" stroke="#bbdefb" stroke-width="1.5" '
             'stroke-dasharray="6,4"/>' % (round(div1, 1), round(div1, 1)))
    L.append('        <line x1="%s" y1="35" x2="%s" y2="335" stroke="#bbdefb" stroke-width="1.5" '
             'stroke-dasharray="6,4"/>' % (round(div2, 1), round(div2, 1)))
    for y, x in year_x.items():
        L.append('        <text x="%s" y="25" text-anchor="middle" font-size="12" '
                 'font-weight="700" fill="#1565c0">%s年</text>' % (round(x, 1), y))
    L.append('        <defs><linearGradient id="areaGrad" x1="0%%" y1="0%%" x2="0%%" y2="100%%">')
    L.append('          <stop offset="0%%" style="stop-color:#1976d2;stop-opacity:0.3"/>')
    L.append('          <stop offset="100%%" style="stop-color:#1976d2;stop-opacity:0.02"/>')
    L.append('        </linearGradient></defs>')
    L.append('        <!-- 面积与折线（32 个月真实值） -->')
    L.append('        <path d="%s" fill="url(#areaGrad)"/>' % area)
    L.append('        <path d="%s" fill="none" stroke="#1976d2" stroke-width="2.5" '
             'stroke-linecap="round" stroke-linejoin="round"/>' % line)
    px, py = pts[ipk]
    L.append('        <circle cx="%s" cy="%s" r="6" fill="#fff" stroke="#c62828" stroke-width="2.5"/>'
             % (px, py))
    L.append('        <text x="%s" y="%s" text-anchor="middle" font-size="10" font-weight="700" '
             'fill="#c62828">峰值 %s（%s）</text>'
             % (px, round(py - 12, 1), format(vals[ipk], ","), ks[ipk]))
    vx, vy = pts[ivl]
    L.append('        <circle cx="%s" cy="%s" r="6" fill="#fff" stroke="#2e7d32" stroke-width="2.5"/>'
             % (vx, vy))
    L.append('        <text x="%s" y="%s" text-anchor="middle" font-size="10" font-weight="700" '
             'fill="#2e7d32">谷值 %s（%s）</text>'
             % (vx, round(vy + 18, 1), format(vals[ivl], ","), ks[ivl]))
    for i, k in enumerate(ks):
        if int(k[5:]) in (1, 4, 7, 10):
            L.append('        <text x="%s" y="348" text-anchor="middle" font-size="10" '
                     'fill="#888">%d月</text>' % (round(xs[i], 1), int(k[5:])))
    L.append('        <path d="M 80,255 Q 400,285 750,310" fill="none" stroke="#ff9800" '
             'stroke-width="1.5" stroke-dasharray="5,3" opacity="0.7"/>')
    L.append('        <text x="500" y="378" text-anchor="middle" font-size="11" '
             'fill="#ff9800" font-weight="600">→ 整体呈下降趋势 →</text>')
    L.append('      </svg>')
    return "\n".join(L)


# ─────────────────────────────────── 回填
def patch(html: str, D) -> tuple[str, list[str]]:
    log = []
    # 1) monthlyData
    if M_DB in html:
        html = re.sub(re.escape(M_DB) + r".*?" + re.escape(M_DE),
                      lambda m: gen_data_block(D), html, flags=re.S)
    else:
        i = html.index("const monthlyData = {")
        j = html.index("\n};", i) + 3
        html = html[:i] + gen_data_block(D) + html[j:]
    log.append("monthlyData 回填 %d 个月" % len(D))

    # 2) 逐月明细静态区（插在「三、月度数据关键发现」之前）
    sec = gen_detail_section(D)
    if M_TB in html:
        html = re.sub(re.escape(M_TB) + r".*?" + re.escape(M_TE), lambda m: sec, html, flags=re.S)
    else:
        anchor = '  <!-- ===== 三、关键发现 ===== -->'
        assert anchor in html, "未找到关键发现锚点"
        html = html.replace(anchor, sec + "\n\n" + anchor, 1)
    log.append("逐月明细区写入 8 节 × 4 表")

    # 3) 原「三、月度数据关键发现」顺延为「四、」
    old = '💡</span>三、月度数据关键发现'
    if old in html:
        html = html.replace(old, '💡</span>四、月度数据关键发现', 1)
        log.append("关键发现章号 三 → 四")

    # 4) detail-panel 标 no-print（网页保留交互，Word 走静态明细）
    if '<div class="detail-panel" id="detailPanel">' in html:
        html = html.replace('<div class="detail-panel" id="detailPanel">',
                            '<div class="detail-panel no-print" id="detailPanel">', 1)
        log.append("detail-panel 标记 no-print")
    if '<div class="detail-panel show no-print" id="detailPanel">' in html:
        html = html.replace('<div class="detail-panel show no-print" id="detailPanel">',
                            '<div class="detail-panel no-print" id="detailPanel">', 1)

    # 5) JS：nstreet 修正（原把街道榜单数组当「覆盖街道数」）
    if "data.nstreet" not in html:
        html = html.replace("document.getElementById('dsStreet').textContent = data.streets;",
                            "document.getElementById('dsStreet').textContent = data.nstreet;", 1)
        log.append("JS 覆盖街道数改用 nstreet")

    # 6) 折线图几何重建（标记包裹，保证幂等）
    svg = M_SB + "\n" + gen_trend_svg(D) + "\n" + M_SE
    if M_SB in html:
        html = re.sub(re.escape(M_SB) + r".*?" + re.escape(M_SE), lambda m: svg, html, flags=re.S)
    else:
        m = re.search(r'<svg viewBox="0 0 1000 \d+" class="trend-svg"[^>]*>.*?</svg>', html, re.S)
        assert m, "未找到趋势折线图 svg"
        html = html[:m.start()] + svg + html[m.end():]
    log.append("折线图几何按真实值重建")

    # 7) 页脚期数
    for a, b in [("2024.01 — 2026.07 · 共31期", "2024.01 — 2026.08 · 共32期"),
                 ("2024.01 — 2026.08 · 共31期", "2024.01 — 2026.08 · 共32期")]:
        if a in html:
            html = html.replace(a, b, 1)
            log.append("页脚期数修正")
            break

    # 8) 明细表样式（幂等）
    if ".data-table th" not in html:
        css = ('  .data-table { width:100%; border-collapse:collapse; font-size:12px; margin:8px 0 14px; }\n'
               '  .data-table th { background:#1a3a5f; color:#fff; font-weight:700; padding:7px 8px; '
               'border:1px solid #d5dde8; }\n'
               '  .data-table td { padding:6px 8px; border:1px solid #e6ecf3; text-align:center; }\n'
               '  .data-table tbody tr:nth-child(even) { background:#f7f9fc; }\n'
               '  .desc { font-size:12.5px; color:#555; line-height:1.9; margin:6px 0 10px; }\n'
               '  .desc b { color:#1565c0; }\n'
               '  .section h3 { font-size:15px; color:#0d47a1; margin:22px 0 6px; '
               'border-left:4px solid #90caf9; padding-left:9px; }\n'
               '  .section h4 { font-size:13px; color:#1565c0; margin:14px 0 4px; }\n'
               '  .table-note { font-size:11.5px; color:#888; margin-top:4px; }\n')
        html = html.replace("  .section-title {", css + "  .section-title {", 1)
        log.append("明细表样式注入")
    # 8) 叙事文字与数据不符处（幂等；改前逐条与主数据核对）
    #    a. 首页写 -13.1%、关键发现写 -15.7%，同页自相矛盾 → 统一为 -13.1%
    #    b. 「2025 年各月同比均下降」不成立（2025-02 为 +5.9%）
    #    c. 「三年累计降幅达33%」无对应口径 → 改为可核的「2026年1-8月月均较2024年月均 -30.1%」
    for a, b in [
        ("2026年1-8月月均1,716件（较2025同期-15.7%）",
         "2026年1-8月月均1,716件（较2025同期-13.1%）"),
        ("2025年各月同比2024年均实现下降，降幅从-5.9%（2月）扩大至-32.5%（11月）。下半年降幅普遍超过20%，治理效果下半年更显著。",
         "2025年除 2 月小幅上升（+5.9%，春节基数偏低）外，其余 11 个月同比上一年均实现下降，"
         "降幅从 -11.0%（3 月）扩大至 -32.5%（11 月）。下半年降幅普遍超过 20%，治理效果下半年更显著。"),
        ("三年累计降幅达33%", "2026年1-8月月均投诉量较基期下降30.1%"),
        # 二次修正：兼容已按上一版替换过的文件（避免新引入「2024 年」反例）
        ("其余 11 个月同比 2024 年均实现下降", "其余 11 个月同比上一年均实现下降"),
        ("2026年1-8月月均较2024年基期下降30.1%", "2026年1-8月月均投诉量较基期下降30.1%"),
    ]:
        if a in html:
            html = html.replace(a, b, 1)
            log.append("叙事文字修正：%s…" % a[:14])
    return html, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只体检，不改文件")
    a = ap.parse_args()

    df = load()
    D = build(df)
    html = open(HTML, encoding="utf-8").read()
    new, log = patch(html, D)

    print("=== 月度榜单重建 ===")
    for k in sorted(D):
        d = D[k]
        print("  %s  %5d 件  %3d 小区  %2d 街道  街道榜首 %s(%d)"
              % (k, d["total"], d["comm"], d["nstreet"],
                 d["streets"][0][0], d["streets"][0][1]))
    print("\n=== 变更 ===")
    for x in log:
        print("  ·", x)
    if a.check:
        print("\n(--check 只体检，未写入)")
        return 0
    if new != html:
        bak = os.path.join(ROOT, "_archive",
                           "数据分析月报合集_备份_%s.html" % datetime.now().strftime("%Y%m%d_%H%M"))
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        shutil.copy2(HTML, bak)
        open(HTML, "w", encoding="utf-8").write(new)
        print("\n备份 → %s" % os.path.relpath(bak, ROOT))
        print("已写入 %s（%.1f KB）" % (os.path.relpath(HTML, ROOT), len(new.encode()) / 1024))
    else:
        print("\n无变化")
    return 0


if __name__ == "__main__":
    sys.exit(main())
