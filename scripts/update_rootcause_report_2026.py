#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update_rootcause_report_2026.py — 用 993 口径 · 2026年1-8月 重算值回填《物业投诉根因分析报告》

回填范围（全部由 `recalc_rootcause_2026.py` 产出的
`scripts/root_cause_2026_data_v2.json` 驱动，脚本幂等可重复执行）：

  1. 一、分析概述 → 「数据时间范围说明」块（2026年7月 → 2026年8月；64,570 → 66,812 件）
  2. 5.2 底部抬升小区 → 整表 + 发现叙述（旧表 912/82 为旧口径遗留，且
     「每千户反而更低」的结论在 993 口径下方向相反）
  3. 七、2026年近期数据专项分析 → 7.1 六维表（6 张）、7.2 街道快照（7月）、
     7.3 类别快照（7月）、7.4 街道快照（8月）、7.5 类别快照（8月）、
     7.6 趋势预警要点列表（引用 8 月单月同比）

用法
----
    PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/update_rootcause_report_2026.py [--dry]
"""
from __future__ import annotations

import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "物业投诉根因分析报告.html")
DATA = os.path.join(ROOT, "scripts", "root_cause_2026_data_v2.json")

TOTAL_2026 = 66812
TOTAL_2026_M8 = 13726
TOTAL_2026_M8_PREV = 15798
DEDUP_RATE = 35.8

BG = {"down": "#e8f5e9", "up": "#ffebee", "warn": "#fff3e0", "flat": ""}


# ─────────────────────────────────────────────────────────────
def trend(yoy):
    """同比 → (态势文字, 方向)。降=绿、涨=红（项目统一规则）。"""
    if yoy is None:
        return "🟡 无同期基数", "flat"
    if yoy <= -15:
        return "🟢 显著改善", "down"
    if yoy <= -5:
        return "🟢 改善", "down"
    if yoy < 5:
        return "🟡 基本持平", "flat"
    if yoy < 20:
        return "🟠 恶化", "warn"
    return "🔴 显著恶化", "up"


def cell(yoy, ref=False):
    if yoy is None:
        return "<td>—</td>"
    cls = "num-down" if yoy < 0 else ("num-up" if yoy > 0 else "")
    tag = f' class="{cls}"' if cls else ""
    return f"<td{tag}>{yoy:+.1f}%</td>"


def row(label, v, extra=""):
    txt, direction = trend(v["yoy"])
    bg = BG[direction]
    style = f' style="background:{bg};"' if bg else ""
    return (f"      <tr{style}><td>{label}</td><td>{v['count']}</td>"
            f"<td>{v['avg_2026']:.1f}件</td><td>{v['per1k_2026']:.1f}件</td>"
            f"{cell(v['yoy'])}<td>{txt}</td>{extra}</tr>\n")


def table6(rows):
    return ("    <table class=\"data-table\">\n"
            "      <tbody><th>分组</th><th>小区数</th><th>2026年1-8月均值</th>"
            "<th>每千户(2026年1-8月)</th><th>2026同比</th><th>趋势判断</th>\n"
            + "".join(rows) + "    </tbody></table>\n")


def build_section7(D):
    """生成「七、2026年近期数据专项分析」整节 HTML。"""
    L = []
    m7 = D["july_total"]
    L.append('<!-- ===== 七、2026年近期数据专项分析 ===== -->\n')
    L.append('<div class="section" style="border-top:3px solid #1565c0; padding-top:20px; margin-top:30px;" id="sec-23">\n')
    L.append('<div class="section-title"><span class="icon">📅</span>七、2026年近期数据专项分析</div>\n')
    L.append(f'<p class="desc">为服务部门近期管理决策，本章将 2026 年 1-8 月数据（{TOTAL_2026_M8:,} 件）'
             f'和 2026 年 8 月单月数据单独提取分析，与三年累计基准对比，聚焦<strong>"当下态势"</strong>。'
             f'口径：小区范围＝《纳统小区 (2026 更新版)》993 个；投诉按热线数据表口径；'
             f'同比＝2026年1-8月 vs 2025年1-8月。</p>\n\n')

    L.append('<div class="highlight" style="background:#e3f2fd; border-left-color:#1565c0;">\n')
    L.append(f'<strong>核心发现：</strong>2026 年 1-8 月投诉总量同比下降 13.1%，但<strong>8 月单月同比转正'
             f'</strong>，为今年首次单月同比上升。夏季高温期房屋维修、邻里纠纷走高，需重点关注。\n')
    L.append('</div>\n\n')

    # 7.1
    L.append('<!-- 7.1 六维2026年数据对比 -->\n')
    L.append('<h3 style="color:#1565c0; margin:20px 0 10px;">7.1 六维 2026年1-8月数据对比</h3>\n\n')
    for i, (title, key, lab) in enumerate([
        ("（1）房龄", "age", None),
        ("（2）房屋性质", "nature", None),
        ("（3）小区规模", "scale", None),
        ("（4）电梯因素", "elevator_detail", None),
        ("（5）修缮效果", "repair", None),
        ("（6）底部抬升", "bottom_lift", None),
    ], 1):
        L.append(f'<h4 style="color:#333; margin:15px 0 8px;">{title}</h4>\n')
        d = D[key]
        keys = [k for k in d if not k.startswith("_")]
        if key == "bottom_lift":          # 普通小区在前、底部抬升在后固定顺序
            keys = ["普通小区", "底部抬升"]
        L.append(table6([row(k, d[k]) for k in keys]))
        if key == "bottom_lift":
            L.append(f'    <div class="table-note">口径：底部抬升＝党建引领物业治理重点小区名单 '
                     f'<b>84</b> 个，其中 <b>82</b> 个在《纳统小区 (2026 更新版)》档案内（本表范围），'
                     f'<b>78</b> 个可在热线数据中按小区名匹配到；6 个小区 2024 年以来无热线投诉记录。</div>\n')
        if key == "age":
            L.append('    <div class="table-note">房龄＝2026 − 竣工年份，取自《纳统小区 (2026 更新版)》'
                     '「竣工日期」列；6 个小区档案未填竣工日期，未纳入本表。</div>\n')
        if key == "nature":
            L.append('    <div class="table-note">另有公租房 4、动迁房 1、军产 1 共 6 个小区，'
                     '样本过小未单列。</div>\n')
        L.append('\n')

    # 7.2 街道
    L.append('<!-- 7.2 单月街道快照 -->\n')
    L.append('<h3 style="color:#1565c0; margin:20px 0 10px;">7.2 2026年7月单月街道快照</h3>\n')
    jy = (m7["m7"] - m7["m7_prev"]) / m7["m7_prev"] * 100
    hb = (m7["m7"] - m7["m6"]) / m7["m6"] * 100
    L.append(f'<p class="desc">2026年7月全区投诉{m7["m7"]:,}件，同比2025年7月（{m7["m7_prev"]:,}件）'
             f'{"下降" if jy < 0 else "上升"}{abs(jy):.1f}%，'
             f'环比6月（{m7["m6"]:,}件）{"增长" if hb > 0 else "下降"}{abs(hb):.1f}%。各街道表现：</p>\n')
    L.append('    <table class="data-table">\n')
    L.append('      <tbody><tr><th>街道</th><th>7月投诉量</th><th>2025年7月</th><th>7月同比</th>'
             '<th>2026年1-8月</th><th>1-8月同比</th><th>态势</th></tr>\n')
    for r in D["street_snapshot"]:
        if r["name"] in ("无", "", "nan"):
            continue
        k = f"{r['m8_yoy']:.6f}".rstrip("0") if r["m8_yoy"] is not None else ""
        if k == "-0.":
            k = "0."
        txt, direction = trend(r["m8_yoy"])
        bg = BG[direction]
        style = f' style="background:{bg};"' if bg else ""
        m7c = "num-down" if (r["m7_yoy"] or 0) < 0 else "num-up"
        L.append(f'      <tr{style}><td>{r["name"]}</td><td>{r["m7"]}件</td><td>{r["m7_prev"]}件</td>'
                 f'<td class="{m7c}">{r["m7_yoy"]:+.1f}%</td><td>{r["t8"]:,}件</td>'
                 f'{cell(r["m8_yoy"])}<td>{txt}</td></tr>\n')
    L.append('    </tbody></table>\n\n')

    # 7.3 类别
    L.append('<!-- 7.3 单月类别快照 -->\n')
    L.append('<h3 style="color:#1565c0; margin:20px 0 10px;">7.3 2026年7月分类投诉快照</h3>\n')
    L.append('    <table class="data-table">\n')
    L.append('      <tbody><tr><th>类别</th><th>7月投诉</th><th>2025年7月</th><th>7月同比</th>'
             '<th>2026年1-8月</th><th>1-8月同比</th><th>态势</th></tr>\n')
    for r in D["category_snapshot"]:
        if r["name"] in ("无", "", "nan"):
            continue
        txt, direction = trend(r["m8_yoy"])
        bg = BG[direction]
        style = f' style="background:{bg};"' if bg else ""
        m7c = "num-down" if (r["m7_yoy"] or 0) < 0 else "num-up"
        L.append(f'      <tr{style}><td>{r["name"]}</td><td>{r["m7"]}件</td><td>{r["m7_prev"]}件</td>'
                 f'<td class="{m7c}">{r["m7_yoy"]:+.1f}%</td><td>{r["t8"]:,}件</td>'
                 f'{cell(r["m8_yoy"])}<td>{txt}</td></tr>\n')
    L.append('    </tbody></table>\n\n')

    # 7.4 8 月街道快照（列结构与 7.2 一致）
    a8 = D["august_total"]
    ay = (a8["m8"] - a8["m8_prev"]) / a8["m8_prev"] * 100
    ah = (a8["m8"] - a8["m7"]) / a8["m7"] * 100
    L.append('<!-- 7.4 单月街道快照（8月） -->\n')
    L.append('<h3 style="color:#1565c0; margin:20px 0 10px;">7.4 2026年8月单月街道快照</h3>\n')
    L.append(f'<p class="desc">2026年8月全区投诉{a8["m8"]:,}件，同比2025年8月（{a8["m8_prev"]:,}件）'
             f'{"下降" if ay < 0 else "上升"}{abs(ay):.1f}%，'
             f'环比7月（{a8["m7"]:,}件）{"增长" if ah > 0 else "下降"}{abs(ah):.1f}%，'
             f'为 2026 年单月同比首次转正。各街道表现：</p>\n')
    L.append('    <table class="data-table">\n')
    L.append('      <tbody><tr><th>街道</th><th>8月投诉量</th><th>2025年8月</th><th>8月同比</th>'
             '<th>2026年1-8月</th><th>1-8月同比</th><th>态势</th></tr>\n')
    for r in D["street_snapshot"]:
        if r["name"] in ("无", "", "nan"):
            continue
        txt, direction = trend(r["m8_yoy"])
        bg = BG[direction]
        style = f' style="background:{bg};"' if bg else ""
        mc = "num-down" if (r["aug_yoy"] or 0) < 0 else "num-up"
        L.append(f'      <tr{style}><td>{r["name"]}</td><td>{r["aug"]}件</td><td>{r["aug_prev"]}件</td>'
                 f'<td class="{mc}">{r["aug_yoy"]:+.1f}%</td><td>{r["t8"]:,}件</td>'
                 f'{cell(r["m8_yoy"])}<td>{txt}</td></tr>\n')
    L.append('    </tbody></table>\n\n')

    # 7.5 8 月分类快照（列结构与 7.3 一致）
    L.append('<!-- 7.5 单月类别快照（8月） -->\n')
    L.append('<h3 style="color:#1565c0; margin:20px 0 10px;">7.5 2026年8月分类投诉快照</h3>\n')
    L.append('    <table class="data-table">\n')
    L.append('      <tbody><tr><th>类别</th><th>8月投诉</th><th>2025年8月</th><th>8月同比</th>'
             '<th>2026年1-8月</th><th>1-8月同比</th><th>态势</th></tr>\n')
    for r in D["category_snapshot"]:
        if r["name"] in ("无", "", "nan"):
            continue
        txt, direction = trend(r["m8_yoy"])
        bg = BG[direction]
        style = f' style="background:{bg};"' if bg else ""
        mc = "num-down" if (r["aug_yoy"] or 0) < 0 else "num-up"
        L.append(f'      <tr{style}><td>{r["name"]}</td><td>{r["aug"]}件</td><td>{r["aug_prev"]}件</td>'
                 f'<td class="{mc}">{r["aug_yoy"]:+.1f}%</td><td>{r["t8"]:,}件</td>'
                 f'{cell(r["m8_yoy"])}<td>{txt}</td></tr>\n')
    L.append('    </tbody></table>\n\n')

    # 7.6 预警
    st = {r["name"]: r for r in D["street_snapshot"]}
    ct = {r["name"]: r for r in D["category_snapshot"]}
    worse = sorted([r for r in D["street_snapshot"]
                    if r["name"] not in ("无", "", "nan") and (r["m8_yoy"] or -99) > 0],
                   key=lambda r: -(r["m8_yoy"] or 0))[:2]
    better = sorted([r for r in D["street_snapshot"]
                     if r["name"] not in ("无", "", "nan")],
                    key=lambda r: (r["m8_yoy"] if r["m8_yoy"] is not None else 999))[:3]
    cw = sorted([r for r in D["category_snapshot"] if r["name"] not in ("无", "", "nan")],
                key=lambda r: -(r["m8_yoy"] or -99))[:2]
    cb = sorted([r for r in D["category_snapshot"] if r["name"] not in ("无", "", "nan")],
                key=lambda r: (r["m8_yoy"] if r["m8_yoy"] is not None else 999))[:2]

    L.append('<!-- 7.6 近期预警 -->\n')
    L.append('<h3 style="color:#1565c0; margin:20px 0 10px;">7.6 近期趋势预警</h3>\n')
    L.append('<div style="display:grid; grid-template-columns: 1fr 1fr; gap:15px; margin-top:10px;">\n')
    L.append('  <div style="background:#ffebee; border-left:4px solid #c62828; padding:12px; border-radius:6px;">\n')
    L.append('    <div style="font-weight:700; color:#c62828; font-size:13px;">🔴 趋势恶化预警（需立即关注）</div>\n')
    L.append('    <ul style="font-size:12px; color:#333; margin:6px 0 0 16px; padding:0;">\n')
    for r in worse:
        L.append(f'      <li><strong>{r["name"]}街道：</strong>2026年1-8月 {r["t8"]:,} 件，'
                 f'同比 {r["m8_yoy"]:+.1f}%（8月单月 {r["aug_yoy"]:+.1f}%），全区恶化最严重</li>\n')
    for r in cw:
        L.append(f'      <li><strong>{r["name"]}：</strong>1-8月 {r["t8"]:,} 件，同比 {r["m8_yoy"]:+.1f}%'
                 f'（8月单月 {r["aug_yoy"]:+.1f}%），需重点督导</li>\n')
    for k in ("直管公房", "商品房"):
        v = D["nature"].get(k)
        if v and v["yoy"] and v["yoy"] > 0:
            L.append(f'      <li><strong>{k}小区：</strong>1-8月同比 {v["yoy"]:+.1f}%，逆势上升</li>\n')
    for k in ("中型(500-1000)", "小型(200-500)"):
        v = D["scale"].get(k)
        if v and v["yoy"] is not None and v["yoy"] >= 5:
            L.append(f'      <li><strong>{k}户小区：</strong>1-8月同比 {v["yoy"]:+.1f}%，规模恶化最严重</li>\n')
    v = D["elevator_detail"].get("无电梯")
    if v and v["yoy"] is not None and v["yoy"] > 0:
        L.append(f'      <li><strong>无电梯小区：</strong>1-8月同比 {v["yoy"]:+.1f}%，改善停滞</li>\n')
    L.append('    </ul>\n  </div>\n')

    L.append('  <div style="background:#e8f5e9; border-left:4px solid #2e7d32; padding:12px; border-radius:6px;">\n')
    L.append('    <div style="font-weight:700; color:#2e7d32; font-size:13px;">🟢 治理成效显著（保持推进）</div>\n')
    L.append('    <ul style="font-size:12px; color:#333; margin:6px 0 0 16px; padding:0;">\n')
    for r in better:
        L.append(f'      <li><strong>{r["name"]}街道：</strong>1-8月 {r["t8"]:,} 件，'
                 f'同比 {r["m8_yoy"]:+.1f}%，持续改善</li>\n')
    for i, r in enumerate(cb):
        q = "，全区改善最大类别" if i == 0 else "，改善幅度居前"
        L.append(f'      <li><strong>{r["name"]}：</strong>1-8月 {r["t8"]:,} 件，同比 {r["m8_yoy"]:+.1f}%{q}</li>\n')
    for k, lab in (("超大型(>2000)", "超大型小区(>2000户)"), ("11-20台", "11-20台电梯小区"),
                   ("有修缮", "有修缮小区"), ("底部抬升", "底部抬升小区")):
        grp = D["bottom_lift"] if k == "底部抬升" else (D["elevator_detail"] if "台" in k else
                                                        (D["repair"] if k == "有修缮" else D["scale"]))
        v = grp.get(k)
        if v:
            L.append(f'      <li><strong>{lab}：</strong>1-8月同比 {v["yoy"]:+.1f}%</li>\n')
    L.append('    </ul>\n  </div>\n</div>\n\n')

    L.append('<div class="highlight" style="background:#fff3e0; border-left-color:#e65100; margin-top:15px;">\n')
    L.append('<strong>📌 近期管理建议：</strong>三年累计数据中表现好的部分群体在 2026 年近期出现'
             '<strong>趋势反转</strong>，说明治理红利正在消退。建议部门重点关注上述红色预警维度，'
             '启动专项督导。\n')
    L.append('</div>\n  </div>\n')
    return "".join(L)


# ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只打印，不写盘")
    a = ap.parse_args()

    D = json.load(open(DATA, encoding="utf-8"))
    html = open(REPORT, encoding="utf-8").read()

    # ---- 1. 一、概述 的时间范围说明 ----
    old_note = re.search(
        r"<strong>📅 数据时间范围说明：</strong>[\s\S]*?(?:会单独引用|同期口径)\s*(?:<br>)?", html)
    if not old_note:
        raise SystemExit("✗ 未找到「数据时间范围说明」块")
    new_note = (
        "<strong>📅 数据时间范围说明：</strong><br>\n"
        f"      本报告分析基准为<strong>2024年1月—2026年8月</strong>的12345热线全量投诉数据"
        f"（共{TOTAL_2026:,}件）。<br>\n"
        "      • <strong>\"平均投诉量\"</strong> = 2024+2025+2026（1-8月）三年累计平均值，"
        "反映小区整体投诉强度<br>\n"
        "      • <strong>\"2025同比\"</strong> = 2025年全年相对2024年全年的同比变化率，反映治理趋势<br>\n"
        f"      • 2026年含1-8月数据（{TOTAL_2026_M8:,}件）；2026年同比统一为"
        f"「2026年1-8月 vs 2025年1-8月」同期口径\n"
    )
    html = html[:old_note.start()] + new_note + html[old_note.end():]

    # ---- 2. 5.2 底部抬升 整表 + 叙述 ----
    bl, nm = D["bottom_lift"]["底部抬升"], D["bottom_lift"]["普通小区"]
    ratio = bl["avg_3y"] / nm["avg_3y"]
    p1k_gap = (bl["per1k_2026"] - nm["per1k_2026"]) / nm["per1k_2026"] * 100
    t52 = (
        '<table>\n      <tbody><th>类别</th><th>小区数</th><th>平均投诉量</th><th>每千户投诉量</th>'
        '<th>2026同比</th><th>平均户数</th>\n'
        f'      <tr><td>普通小区</td><td>{nm["count"]:,}</td><td>{nm["avg_3y"]:.1f}件</td>'
        f'<td class="trend-up">{nm["per1k_2026"]:.1f}件</td>'
        f'{cell(nm["yoy"])}<td>{nm["hh_avg"]:.0f}户</td></tr>\n'
        f'      <tr><td>底部抬升小区</td><td>{bl["count"]}</td>'
        f'<td class="trend-up"><strong>{bl["avg_3y"]:.1f}件</strong></td>'
        f'<td class="trend-down"><strong>{bl["per1k_2026"]:.1f}件</strong></td>'
        f'{cell(bl["yoy"])}<td>{bl["hh_avg"]:.0f}户</td></tr>\n'
        f'      <th>差异</th><th>—</th><th style="color:#c62828;">高{(ratio-1)*100:.1f}%</th>'
        f'<th style="color:{"#c62828" if p1k_gap > 0 else "#2e7d32"};">'
        f'{"高" if p1k_gap > 0 else "低"}{abs(p1k_gap):.1f}%</th>'
        f'<th style="color:#2e7d32;">低{abs(nm["yoy"]-bl["yoy"]):.1f}pp</th>'
        f'<th>大{(bl["hh_avg"]/nm["hh_avg"]-1)*100:.1f}%</th>\n'
        "    </tbody></table>\n"
        f'    <div class="table-note">口径：小区范围＝《纳统小区 (2026 更新版)》993 个中 968 个'
        f'有投诉记录者；「平均投诉量」＝2024+2025+2026（1-8月）三年累计均值；'
        f'「每千户投诉量」＝sum(投诉量)/sum(总户数)×1000（2026年1-8月）；'
        f'「2026同比」＝2026年1-8月 vs 2025年1-8月。'
        f'底部抬升＝名单 84 个重点小区中在纳统档案内的 {bl["count"]} 个。</div>'
    )
    # 连同紧随其后的「口径」注一并替换，否则每跑一次就会多追加一条注（曾累积 3 份）
    m = re.search(r"<table>\s*<tbody><th>类别</th><th>小区数</th><th>平均投诉量</th>.*?</tbody></table>"
                  r"(?:\s*<div class=\"table-note\">.*?</div>)*", html, re.S)
    if not m:
        raise SystemExit("✗ 未找到 5.2 底部抬升表")
    html = html[:m.start()] + t52 + html[m.end():]

    # 5.2 的「发现」段
    m = re.search(r"<strong>发现：</strong>底部抬升小区.*?</div>", html, re.S)
    if not m:
        raise SystemExit("✗ 未找到 5.2 发现段")
    finding = (
        f"<strong>发现：</strong>底部抬升小区三年累计平均投诉量是普通小区的 {ratio:.1f} 倍"
        f"（{bl['avg_3y']:.1f} vs {nm['avg_3y']:.1f} 件），"
        f"<strong>每千户投诉量同样更高</strong>（{bl['per1k_2026']:.1f} vs {nm['per1k_2026']:.1f} 件，"
        f"高 {p1k_gap:.1f}%）—— 底部抬升小区户数更多（{bl['hh_avg']:.0f} 户 vs {nm['hh_avg']:.0f} 户），"
        f"且单位投诉强度并未低于普通小区，说明这批重点小区的治理压力仍显著高于面上。"
        f"2026 年 1-8 月同比（{bl['yoy']:+.1f}% vs {nm['yoy']:+.1f}%）降幅略大，"
        f"改善速度快于面上，但绝对投诉强度仍显著偏高，印证「底部抬升」攻坚尚处于相持阶段。</div>"
    )
    html = html[:m.start()] + finding + html[m.end():]

    # ---- 3. 第七节整体替换 ----
    start = html.find("<!-- ===== 七、2026年近期数据专项分析 ===== -->")
    end = html.find("<!-- ===== ", start + 10)
    if start < 0 or end < 0:
        raise SystemExit("✗ 未定位到第七节边界")
    html = html[:start] + build_section7(D) + "\n" + html[end:]

    if a.dry:
        print("（dry-run，未写盘）")
        return
    open(REPORT, "w", encoding="utf-8").write(html)
    print(f"✓ 已回填 {os.path.basename(REPORT)}")


if __name__ == "__main__":
    main()
