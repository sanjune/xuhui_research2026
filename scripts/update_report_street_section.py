# -*- coding: utf-8 -*-
"""
下降报告「街道章节」数据修正脚本
==================================

背景：`12345投诉量下降数据报告.html` 的街道相关区块（核心数据卡片第二条、副标题、
各街道投诉量对比图、6.2 街道表现表）在 8 月数据接入后**未同步更新**，且标签被改成
"1-8月"但数值仍是 **1-7月**口径，存在三处问题：

    1. 核心数据卡片：显示 "-15.67% / 13,618件 → 13,726件 / 减少2,134件"
       （-15.67% 是 1-6月 口径；13,618 与 2,134 均不匹配任何口径）
    2. 副标题：仍写"数据周期：2024年1月 — 2026年7月"
    3. 街道图表与 6.2 表：数值为 1-7月，标签标为"1-8月"；且"全部街道均实现同比下降"
       "田林是唯一同比上升" 的结论在 1-8月 口径下已不成立（漕河泾亦上升）

本脚本按权威数据（data/merged_cleaned.pkl）重算并就地修正上述区块，可重复执行。

用法：
    python scripts/update_report_street_section.py --dry-run   # 只打印将要修改的内容
    python scripts/update_report_street_section.py             # 实际修改
"""
import argparse
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "12345投诉量下降数据报告.html")
PKL = os.path.join(ROOT, "data", "merged_cleaned.pkl")

# 报告图表的街道顺序（华泾 = 华泾镇）
CHART_ORDER = ["长桥", "枫林路", "徐家汇", "漕河泾", "斜土路", "天平路", "田林",
               "华泾镇", "龙华", "凌云路", "康健新村", "湖南路", "虹梅路"]
CHART_LABEL = {"华泾镇": "华泾", "康健新村": "康健新村"}

LINK = ('<p style="font-size:12px;color:#1565c0;margin-top:6px;">'
        '📎 各街镇单独画像（趋势 / 下降归因 / 热点小区与企业 / 重复投诉 / 风险预警）：'
        '<a href="街镇专项分析报告.html" style="color:#1565c0;font-weight:600;">'
        '查看《街镇专项分析报告》 →</a></p>')


def fmt(v):
    return f"{int(round(float(v))):,}"


def signed(v):
    return f"{v:+.1f}%"


def color(v):
    return "#00a854" if v < 0 else "#ff4d4f"


def situation(v):
    if v > 10:
        return "#ffebee", "🔴 需重点关注"
    if v > 0:
        return "#fff3e0", "🟡 需关注"
    if v > -10:
        return "#ffffff", "🟢 改善"
    if v > -20:
        return "#e8f5e9", "🟢 显著改善"
    return "#e8f5e9", "🟢 大幅改善"


def compute():
    df = pd.read_pickle(PKL)
    d = df[df["street"] != "无"]

    def seg(y, m1, m2):
        return d[(d["year"] == y) & (d["month"] >= m1) & (d["month"] <= m2)].groupby("street").size()

    t = pd.DataFrame({
        "n24": seg(2024, 1, 8), "n25": seg(2025, 1, 8), "n26": seg(2026, 1, 8),
        "m7_25": seg(2025, 7, 7), "m7_26": seg(2026, 7, 7),
        "m8_25": seg(2025, 8, 8), "m8_26": seg(2026, 8, 8),
    })
    t["yoy"] = ((t["n26"] - t["n25"]) / t["n25"] * 100).round(1)
    t["yoy7"] = ((t["m7_26"] - t["m7_25"]) / t["m7_25"] * 100).round(1)
    t["yoy8"] = ((t["m8_26"] - t["m8_25"]) / t["m8_25"] * 100).round(1)

    # 全区口径（含街镇归属为空的工单）
    dist = {
        "n25": int(len(df[(df["year"] == 2025) & (df["month"] <= 8)])),
        "n26": int(len(df[(df["year"] == 2026) & (df["month"] <= 8)])),
    }
    dist["yoy"] = round((dist["n26"] - dist["n25"]) / dist["n25"] * 100, 1)
    return t, dist


def build_chart(t):
    """各街道投诉量对比图（三年同期 1-8月）。"""
    a = [int(t.loc[s, "n24"]) for s in CHART_ORDER]
    b = [int(t.loc[s, "n25"]) for s in CHART_ORDER]
    c = [int(t.loc[s, "n26"]) for s in CHART_ORDER]
    labels = "[" + ",".join(f"'{CHART_LABEL.get(s, s)}'" for s in CHART_ORDER) + "]"
    return labels, a, b, c


def build_table(t):
    """6.2 街道表现表（1-8月同期口径，按同比升序）。"""
    rows = []
    for st in t.sort_values("yoy").index:
        r = t.loc[st]
        bg, sit = situation(r["yoy"])
        rows.append(
            f'<tr style="background:{bg};">'
            f'<td>{st}</td>'
            f'<td>{fmt(r["n26"])}件</td>'
            f'<td>{fmt(r["n25"])}件</td>'
            f'<td style="color:{color(r["yoy"])};font-weight:700;">{signed(r["yoy"])}</td>'
            f'<td>{fmt(r["m7_26"])}件</td>'
            f'<td style="color:{color(r["yoy7"])};font-weight:700;">{signed(r["yoy7"])}</td>'
            f'<td>{fmt(r["m8_26"])}件</td>'
            f'<td style="color:{color(r["yoy8"])};font-weight:700;">{signed(r["yoy8"])}</td>'
            f'<td>{sit}</td></tr>')
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    t, dist = compute()
    dist25, dist26, dyoy = dist["n25"], dist["n26"], dist["yoy"]
    print(f"全区同期（含归属为空）：{dist25:,} → {dist26:,}，同比 {dyoy}%，减少 {dist25 - dist26:,} 件")
    print(f"13街镇明细合计：{int(t['n25'].sum()):,} → {int(t['n26'].sum()):,}")
    up = t[t["yoy"] > 0].sort_values("yoy", ascending=False)
    print("同比上升街镇：" + "、".join(f"{s} {signed(v)}" for s, v in up["yoy"].items()))

    s = open(REPORT, encoding="utf-8").read()
    orig = s

    # ── 1. 核心数据卡片（全区口径）
    new_card = ('<div class="stat-label">2026年1-8月同比去年同期</div>\n'
                f'        <div class="stat-value">-13.1<span class="stat-unit">%</span></div>\n'
                f'        <div class="stat-sub">{fmt(dist25)}件 → {fmt(dist26)}件</div>\n'
                f'        <div class="stat-change down">↓ 减少{fmt(dist25 - dist26)}件</div>')
    m = re.search(r'<div class="stat-label">2026年1-8月同比去年同期</div>\s*'
                  r'<div class="stat-value">.*?</div>\s*<div class="stat-sub">.*?</div>\s*'
                  r'<div class="stat-change down">.*?</div>', s)
    if m:
        s = s[:m.start()] + new_card.replace("\n        ", "\n") + s[m.end():]
        print("✔ 核心数据卡片已修正")
    else:
        print("· 核心数据卡片未匹配，请人工检查")

    # ── 2. 副标题数据周期
    if "2024年1月 — 2026年7月" in s:
        s = s.replace("数据周期：2024年1月 — 2026年7月", "数据周期：2024年1月 — 2026年8月")
        print("✔ 副标题数据周期已更新为 2026年8月")

    # ── 3. 各街道投诉量对比图
    labels, a, b, c = build_chart(t)
    s = re.sub(r"var streets = \[[^\]]*\];",
               f"var streets = {labels};", s, count=1)
    s = re.sub(r"var st2024 = \[[^\]]*\];", "var st2024 = [" + ",".join(map(str, a)) + "];", s, count=1)
    s = re.sub(r"var st2025 = \[[^\]]*\];", "var st2025 = [" + ",".join(map(str, b)) + "];", s, count=1)
    s = re.sub(r"var st2026 = \[[^\]]*\];", "var st2026 = [" + ",".join(map(str, c)) + "];", s, count=1)
    s = s.replace("legend: { data: ['2024年', '2025年', '2026年1-8月'], top: 10 },",
                  "legend: { data: ['2024年1-8月', '2025年1-8月', '2026年1-8月'], top: 10 },")
    s = s.replace("{ name: '2024年', type: 'bar', data: st2024",
                  "{ name: '2024年1-8月', type: 'bar', data: st2024")
    s = s.replace("{ name: '2025年', type: 'bar', data: st2025",
                  "{ name: '2025年1-8月', type: 'bar', data: st2025")
    s = s.replace('<div class="section-desc">13个街道2024-2026年投诉量对比，全部街道均实现同比下降</div>',
                  f'<div class="section-desc">13个街镇 2024-2026 年同期（1-8月）投诉量对比：'
                  f'11 个街镇同比下降，{"、".join(up.index)} 同比上升，需重点关注</div>')
    print("✔ 街道对比图数据已更新为 1-8月 同期口径")

    # ── 4. 6.2 街道表现表
    m = re.search(r'(<h3 style="font-size:15px;color:#1565c0;margin:15px 0 8px;">6\.2 街道2026年1-8月表现</h3>\s*'
                  r'<table[^>]*>\s*<tr[^>]*>.*?</tr>)(.*?)(</table>)', s, re.S)
    if m:
        s = s[:m.start(2)] + "\n" + build_table(t) + "\n" + s[m.end(2):]
        print("✔ 6.2 街道表现表已按 1-8月 同期口径重算")
    else:
        print("· 6.2 表未匹配，请人工检查")

    # ── 5. 结论文字
    old_note = "注：数据为12345热线物业类投诉全量（按街道汇总）。田林街道是唯一同比上升的街道，需重点关注。"
    new_note = (f"注：数据为12345热线物业类投诉全量（按街镇汇总），同比统一采用同期口径（1-8月 vs 1-8月）。"
                f"{'、'.join(up.index)} 同比上升，其中"
                + "、".join(f"{st} 8月单月 {signed(t.loc[st, 'yoy8'])}" for st in up.index)
                + "，需重点关注。")
    if old_note in s:
        s = s.replace(old_note, new_note)
        print("✔ 表下结论文字已修正")

    # ── 6. 插入专页链接
    if "街镇专项分析报告.html" not in s:
        anchor = '<div id="chart-street" class="chart-box tall"></div>'
        if anchor in s:
            s = s.replace(anchor, anchor + "\n" + LINK)
            print("✔ 已插入《街镇专项分析报告》链接")
    else:
        print("· 专页链接已存在")

    if args.dry_run:
        print("\n[DRY-RUN] 未写入文件")
        return
    if s != orig:
        open(REPORT, "w", encoding="utf-8").write(s)
        print(f"\n✔ 已写入 {REPORT}")
    else:
        print("\n· 无改动")


if __name__ == "__main__":
    main()
