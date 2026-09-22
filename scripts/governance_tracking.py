# -*- coding: utf-8 -*-
"""
治理效果追踪分析 — 可复现脚本（v2，2026年1-8月同期口径）
==========================================================

v1 的问题（已修正）：
  1. 数据源为 Excel（2024全年 / 2025全年+2026年1-6月 / 2026年7月），2026 只到 7 月，
     且被当作「上半年」展示，名不副实。
  2. 「恶化」判定只看 2024全年→2025全年（improvement_2025 < -20），完全不看 2026。
     导致 2025 年暴涨、2026 年已大幅回落的小区（如永新城 13→61→12）被误标「恶化」。
  3. worsening_top10 的 JSON 漏输出 improvement_2026，报告同比列只能显示「—」。
  4. 2024 基数仅 5 件即可入榜，小基数把百分比放大到 -369%。
  5. top_category 用 2024-2026 三年合并首位，不反映当前矛盾。

v2 口径：
  · 数据源    data/merged_cleaned.pkl（66,812 条，2024.01–2026.08），与街镇报告同源
  · 同比规则  2025 同比 = 2025全年 vs 2024全年；2026 同比 = 2026年1-8月 vs 2025年1-8月
  · 主判定    以 2026 年同期同比（improvement_2026）为准：
               恶化 < -10% ｜ 改善 > +10% ｜ 稳定 ±10% 以内
  · 反弹      2025 年改善 >20% 但 2026 年同期恶化 >10%
  · 基数门槛  三年合计≥15 且 2024全年≥5 且 2025年1-8月≥10（抑制小基数放大）
  · 首位类别  取 2026年1-8月 的实际首位类别

产出：scripts/governance_tracking.json
"""
import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKL = os.path.join(ROOT, "data", "merged_cleaned.pkl")
OUT = os.path.join(ROOT, "scripts", "governance_tracking.json")

YEAR_NOW, MONTH_NOW = 2026, 8
YEAR_PREV, YEAR_BASE = 2025, 2024

# 主数据街镇名 → 派生资产街镇名（与 risk_scores.json、街镇报告保持一致）
STREET_ALIAS = {"华泾镇": "华泾"}

def load_data():
    """返回 (全量 df, 仅含有效小区名的 df)。

    口径与街镇专项分析报告保持一致：街道级 / 类别级统计用**全量**（不排除任何十四类），
    只有「按小区追踪」才要求 community_name 有效（否则无法归属到小区）。
    """
    df = pd.read_pickle(PKL)
    df["street"] = df["street"].map(lambda x: STREET_ALIAS.get(x, x))
    comm = df[df["community_name"].notna()
              & (df["community_name"] != "无") & (df["community_name"] != "")].copy()
    return df, comm

# 判定阈值
WORSE_TH = -10.0     # 2026年同期同比低于此值 → 恶化
BETTER_TH = 10.0     # 2026年同期同比高于此值 → 改善
MIN_TOTAL = 15       # 三年合计最小工单量
MIN_2024 = 5         # 2024 全年最小基数
MIN_2025_SAME = 10   # 2025年1-8月最小基数（抑制小基数放大百分比）


def eff(prev: int, curr: int):
    """改善率（正数=改善）。基数为 0 时返回 None。"""
    if not prev:
        return None
    return round((prev - curr) / prev * 100, 1)


def main():
    print("=" * 64)
    print("治理效果追踪分析 v2（2026年1-8月同期口径）")
    print("=" * 64)

    df, dfc = load_data()
    print(f"全量记录: {len(df):,}   ｜  可归属到小区: {len(dfc):,}")

    p24, p25, p26 = df[df["year"] == YEAR_BASE], df[df["year"] == YEAR_PREV], df[df["year"] == YEAR_NOW]
    # 同期（1-8月）
    p24s, p25s, p26s = (p24[p24["month"] <= MONTH_NOW], p25[p25["month"] <= MONTH_NOW],
                        p26[p26["month"] <= MONTH_NOW])

    # ─── 1. 小区层面追踪 ───
    print("\n" + "=" * 64)
    print("1. 小区治理效果追踪")
    print("=" * 64)

    tracking = []
    for community, g in dfc.groupby("community_name"):
        if len(g) < MIN_TOTAL:
            continue
        g24, g25, g26 = g[g["year"] == YEAR_BASE], g[g["year"] == YEAR_PREV], g[g["year"] == YEAR_NOW]
        g25s, g26s = g25[g25["month"] <= MONTH_NOW], g26[g26["month"] <= MONTH_NOW]

        n24, n25, n26 = len(g24), len(g25), len(g26s)
        n25_same = len(g25s)
        if n24 < MIN_2024 or n25_same < MIN_2025_SAME:
            continue

        imp_2025 = eff(n24, n25)              # 2025同比：全年 vs 全年
        imp_2026 = eff(n25_same, n26)         # 2026同比：1-8月 vs 1-8月
        if imp_2026 is None:
            continue

        # 2026年1-8月首位类别（当前矛盾）
        top_cat = (g26s["category_14"].value_counts().index[0]
                   if len(g26s) else (g["category_14"].value_counts().index[0]
                                      if len(g) else ""))

        tracking.append({
            "community": community,
            "street": g["street"].iloc[0],
            "company": str(g["property_company"].iloc[0])[:20]
                       if pd.notna(g["property_company"].iloc[0]) else "未知",
            "total": len(g),
            "n2024": n24, "n2025": n25,                    # 全年
            "n2025_same": n25_same, "n2026": n26,          # 同期（1-8月）
            "improvement_2025": imp_2025,
            "improvement_2026": imp_2026,
            "top_category": top_cat,
        })

    print(f"纳入追踪小区: {len(tracking)}")

    # ─── 2. 判定 ───
    def status_of(t):
        # 2026年同期零投诉：可能是拆迁、小区更名或数据归并，无法认定为治理成效，
        # 单独归类，不进入改善/恶化榜单（否则 +100% 会霸占改善榜首位）
        if t["n2026"] == 0:
            return "本期无投诉"
        if t["improvement_2026"] < WORSE_TH:
            return "恶化"
        if t["improvement_2026"] > BETTER_TH:
            return "改善"
        return "基本稳定"

    for t in tracking:
        t["status"] = status_of(t)

    nodata = [t for t in tracking if t["status"] == "本期无投诉"]
    success = sorted([t for t in tracking if t["status"] == "改善"],
                     key=lambda x: -x["improvement_2026"])
    worsening = sorted([t for t in tracking if t["status"] == "恶化"],
                       key=lambda x: x["improvement_2026"])
    rebound = sorted([t for t in tracking
                      if (t["improvement_2025"] or 0) > 20 and t["improvement_2026"] < WORSE_TH],
                     key=lambda x: x["improvement_2026"])
    stable = [t for t in tracking if t["status"] == "基本稳定"]

    print(f"  改善(>{BETTER_TH:+.0f}%): {len(success)}")
    print(f"  恶化(<{WORSE_TH:+.0f}%): {len(worsening)}")
    print(f"  反弹(2025改善>20% 且 2026恶化>10%): {len(rebound)}")
    print(f"  基本稳定: {len(stable)}")
    print(f"  本期无投诉(2026年1-8月零工单，不参与排名): {len(nodata)}")

    print("\n恶化 Top10（2026年1-8月 vs 2025年同期）:")
    for i, t in enumerate(worsening[:10], 1):
        print(f"  {i:2d}. {t['community'][:14]:14s} | {t['street']:6s} | "
              f"2025同期{t['n2025_same']:4d} → 2026同期{t['n2026']:4d} "
              f"({t['improvement_2026']:+.1f}%) | {t['top_category']}")

    print("\n改善 Top10:")
    for i, t in enumerate(success[:10], 1):
        print(f"  {i:2d}. {t['community'][:14]:14s} | {t['street']:6s} | "
              f"2025同期{t['n2025_same']:4d} → 2026同期{t['n2026']:4d} "
              f"({t['improvement_2026']:+.1f}%) | {t['top_category']}")

    # ─── 3. 十四类治理效果 ───
    print("\n" + "=" * 64)
    print("2. 十四类治理效果")
    print("=" * 64)

    category_effects = {}
    for cat in sorted(df["category_14"].dropna().unique()):
        c24 = int((p24["category_14"] == cat).sum())
        c25 = int((p25["category_14"] == cat).sum())
        c25s = int((p25s["category_14"] == cat).sum())
        c26 = int((p26s["category_14"] == cat).sum())
        category_effects[cat] = {
            "2024": c24, "2025": c25, "2025_h1": c25s, "2026_h1": c26,
            "effect_2025": eff(c24, c25), "effect_2026": eff(c25s, c26),
        }
        print(f"  {cat:12s}: 2024={c24:5d} → 2025={c25:5d} → 2026年1-8月={c26:5d} "
              f"(同期同比 {'-' if (category_effects[cat]['effect_2026'] or 0) > 0 else '+'}"
              f"{abs(category_effects[cat]['effect_2026'] or 0):.1f}%)")

    # ─── 4. 街镇治理效果 ───
    print("\n" + "=" * 64)
    print("3. 街镇治理效果")
    print("=" * 64)

    street_effects = {}
    for st in sorted(df["street"].dropna().unique()):
        if st in ("未知", "无", ""):
            continue
        c24 = int((p24["street"] == st).sum())
        c25 = int((p25["street"] == st).sum())
        c25s = int((p25s["street"] == st).sum())
        c26 = int((p26s["street"] == st).sum())
        street_effects[st] = {
            "2024": c24, "2025": c25, "2025_h1": c25s, "2026_h1": c26,
            "effect_2025": eff(c24, c25), "effect_2026": eff(c25s, c26),
        }

    for s in sorted(street_effects, key=lambda x: -(street_effects[x]["effect_2026"] or -999)):
        e = street_effects[s]
        print(f"  {s:6s}: 2025同期{e['2025_h1']:5d} → 2026同期{e['2026_h1']:5d} "
              f"(同期同比 {e['effect_2026']:+.1f}%)")

    # ─── 5. 输出 ───
    def pack(lst):
        return [{
            "community": t["community"], "street": t["street"], "company": t["company"],
            "n2024": t["n2024"], "n2025": t["n2025"],
            "n2025_same": t["n2025_same"], "n2026": t["n2026"],
            "improvement_2025": t["improvement_2025"],
            "improvement_2026": t["improvement_2026"],
            "top_category": t["top_category"], "status": t["status"],
        } for t in lst]

    result = {
        "meta": {
            "version": 2,
            "source": "data/merged_cleaned.pkl（66,812 条，2024.01–2026.08）",
            "period_label": f"{YEAR_NOW}年1-{MONTH_NOW}月",
            "rule": "2025同比=2025全年vs2024全年；2026同比=2026年1-8月vs2025年1-8月",
            "status_rule": f"以2026年同期同比判定：恶化<{WORSE_TH:+.0f}%｜改善>{BETTER_TH:+.0f}%｜稳定±{BETTER_TH:.0f}%",
            "thresholds": {"min_total": MIN_TOTAL, "min_2024": MIN_2024,
                           "min_2025_same": MIN_2025_SAME},
        },
        "total_tracking": len(tracking),
        "success_count": len(success),
        "worsening_count": len(worsening),
        "rebound_count": len(rebound),
        "stable_count": len(stable),
        "nodata_count": len(nodata),
        "success_top20": pack(success[:20]),
        "worsening_top10": pack(worsening[:10]),
        "rebound_top10": pack(rebound[:10]),
        "category_effects": category_effects,
        "street_effects": street_effects,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {OUT}")


if __name__ == "__main__":
    main()
