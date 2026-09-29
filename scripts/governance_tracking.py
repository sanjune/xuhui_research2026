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

v3 口径（2026-09-28 项目组决策）：
  · **参评范围**：仅《纳统小区 (2026 更新版).xls》名单内的小区；不在名单中的不做统计
  · **统计单元**：按纳统小区聚合（别名/曾用名归并）—— `--scope aggregate` 默认；
                 `--scope filter` 仅过滤名单；`--scope all` 为改造前旧口径

产出：scripts/governance_tracking.json
"""
import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nato_match as NM  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKL = os.path.join(ROOT, "data", "merged_cleaned.pkl")
OUT = os.path.join(ROOT, "scripts", "governance_tracking.json")

_ap = argparse.ArgumentParser(add_help=True)
_ap.add_argument("--scope", choices=["aggregate", "filter", "all"], default="aggregate",
                 help="aggregate=按纳统小区聚合（默认）；filter=仅过滤名单；all=旧口径")
_ap.add_argument("--dry-run", action="store_true", help="只打印，不写 json")
ARGS, _unknown = _ap.parse_known_args()

YEAR_NOW, MONTH_NOW = 2026, 8
YEAR_PREV, YEAR_BASE = 2025, 2024

# 主数据街镇名 → 派生资产街镇名（与 risk_scores.json、街镇报告保持一致）
STREET_ALIAS = {"华泾镇": "华泾"}

# 收窄范围后的匹配表（模块级，供输出时取纳统档案街道）
NATO_MAP = None
NATO_STREET = {}

def load_data():
    """返回 (全量 df, 仅含有效小区名的 df)。

    口径与街镇专项分析报告保持一致：街道级 / 类别级统计用**全量**（不排除任何十四类），
    只有「按小区追踪」才要求 community_name 有效（否则无法归属到小区）。
    v3：按项目组决策，小区级追踪再叠加「仅纳统名单 + 按纳统小区聚合」。
    """
    global NATO_MAP, NATO_STREET
    df = pd.read_pickle(PKL)
    df["street"] = df["street"].map(lambda x: STREET_ALIAS.get(x, x))
    comm = df[df["community_name"].notna()
              & (df["community_name"] != "无") & (df["community_name"] != "")].copy()
    comm["community_name"] = comm["community_name"].astype(str).str.strip()

    if ARGS.scope == "all":
        comm["_unit"] = comm["community_name"]
        return df, comm

    _st = comm.groupby("community_name")["street"].agg(
        lambda s: s.mode().iloc[0] if len(s.mode()) else "").to_dict()
    NATO_MAP = NM.build_map(sorted(_st), streets=_st)
    NATO_STREET = dict(zip(NATO_MAP["nato_name"], NATO_MAP["nato_street"]))
    ok = set(NATO_MAP.loc[NATO_MAP["matched"], "hotline_name"])
    n0 = len(comm)
    comm = comm[comm["community_name"].isin(ok)].copy()
    if ARGS.scope == "aggregate":
        comm = NM.aggregate_key(comm, col="community_name", mp=NATO_MAP)
        comm["_unit"] = comm["nato_community"]
        comm = comm[comm["_unit"] != ""]
    else:
        comm["_unit"] = comm["community_name"]
    print(f"参评范围收窄（{ARGS.scope}）：{n0:,} → {len(comm):,} 条"
          f"（剔除 {n0-len(comm):,} 条）｜统计单元 {comm['_unit'].nunique()} 个")
    return df, comm

# 判定阈值
WORSE_TH = -10.0     # 2026年同期同比低于此值 → 恶化
BETTER_TH = 10.0     # 2026年同期同比高于此值 → 改善
MIN_TOTAL = 15       # 三年合计最小工单量
MIN_2024 = 5         # 2024 全年最小基数
MIN_2025_SAME = 10   # 2025年1-8月最小基数（抑制小基数放大百分比）

# 物业服务态度专项排名（整改清单第 12 项）
SA_CAT = "物业服务态度"
SA_MIN = 3           # 入榜门槛：两年同期（2025年1-8月 + 2026年1-8月）合计 ≥ 此值
SA_BASE_PCT = 5      # 2025 同期基数 < 此值时不展示同比（否则 3→11 会变成 +266.7%）


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
    for community, g in dfc.groupby("_unit"):
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
            "street": (NATO_STREET.get(community) or g["street"].iloc[0]).replace("街道", "").replace("镇", "").strip()
                      if (NATO_STREET.get(community) or g["street"].iloc[0]) else "未知",
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

    # ─── 4.5 物业服务态度投诉专项排名（整改清单第 12 项）───
    print("\n" + "=" * 64)
    print("4. 物业服务态度投诉专项排名")
    print("=" * 64)

    sa = df[df["category_14"] == SA_CAT].copy()
    sa["_pc"] = sa["property_company"].astype(str).str.strip()
    sa["_cm"] = sa["community_name"].astype(str).str.strip()

    def _chg(prev: int, curr: int):
        """同比变化率（正=上升=红，负=下降=绿）。基数为 0 时返回 None。"""
        if not prev:
            return None
        return round((curr - prev) / prev * 100, 1)

    def _sa_rows(key_col, extra_fn):
        rows = []
        for key, g in sa.groupby(key_col):
            if key in ("", "无", "nan", "None", "NoneType"):
                continue
            n26 = int(((g["year"] == YEAR_NOW) & (g["month"] <= MONTH_NOW)).sum())
            n25 = int(((g["year"] == YEAR_PREV) & (g["month"] <= MONTH_NOW)).sum())
            if n26 + n25 < SA_MIN:
                continue
            row = {"name": str(key), "n2026": n26, "n2025_same": n25, "total": n26 + n25}
            # 2025 同期基数太小时百分比会被放大成 +700%，故不出同比
            row["change"] = _chg(n25, n26) if n25 >= SA_BASE_PCT else None
            row.update(extra_fn(g))
            rows.append(row)
        rows.sort(key=lambda r: (-r["n2026"], -r["n2025_same"], r["name"]))
        return rows

    sa_companies = _sa_rows("_pc", lambda g: {
        "n_community": int(g["_cm"].nunique()),
        "n_street": int(g["street"].nunique()),
    })
    sa_communities = _sa_rows("_cm", lambda g: {
        "street": (str(g["street"].mode().iloc[0]).replace("街道", "").replace("镇", "").strip()
                   if len(g["street"].mode()) else ""),
        "company": (str(g["_pc"].mode().iloc[0]) if len(g["_pc"].mode()) else ""),
    })

    _sa26 = sa[(sa["year"] == YEAR_NOW) & (sa["month"] <= MONTH_NOW)]
    _sa25 = sa[(sa["year"] == YEAR_PREV) & (sa["month"] <= MONTH_NOW)]
    sa_totals = {
        "n2024": int((sa["year"] == YEAR_BASE).sum()),
        "n2025": int((sa["year"] == YEAR_PREV).sum()),
        "n2025_same": int(len(_sa25)),
        "n2026": int(len(_sa26)),
        "change": _chg(int(len(_sa25)), int(len(_sa26))),
        "company_missing": int(_sa26["_pc"].isin(["", "无", "nan", "None"]).sum()),
        "community_missing": int(_sa26["_cm"].isin(["", "无", "nan", "None"]).sum()),
        "n_company": len(sa_companies),
        "n_community": len(sa_communities),
        "communities_all": int(_sa26["_cm"].nunique()),
        "companies_all": int(_sa26[~_sa26["_pc"].isin(["", "无", "nan", "None"])]["_pc"].nunique()),
    }
    print(f"  全量 {sa_totals['n2026']} 件（2025 同期 {sa_totals['n2025_same']} 件，"
          f"同比 {sa_totals['change']:+.1f}%）")
    print(f"  入榜公司 {sa_totals['n_company']} 家（两年合计≥{SA_MIN}）｜"
          f"入榜小区 {sa_totals['n_community']} 个")
    print("\n  物业公司 Top10:")
    for i, r in enumerate(sa_companies[:10], 1):
        ch = "基数不足" if r["change"] is None else f"{r['change']:+.1f}%"
        print(f"   {i:2d}. {r['name'][:22]:22s} 2026={r['n2026']:3d} 2025同期={r['n2025_same']:3d} "
              f"({ch}) 涉 {r['n_community']} 个小区")
    print("\n  小区 Top10:")
    for i, r in enumerate(sa_communities[:10], 1):
        ch = "基数不足" if r["change"] is None else f"{r['change']:+.1f}%"
        print(f"   {i:2d}. {r['name'][:16]:16s} {r['street']:6s} 2026={r['n2026']:3d} "
              f"2025同期={r['n2025_same']:3d} ({ch})")

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
            "version": 3,
            "source": "data/merged_cleaned.pkl（66,812 条，2024.01–2026.08）",
            "scope": {
                "unit": ("纳统小区（《纳统小区 (2026 更新版).xls》）" if ARGS.scope != "all"
                         else "热线小区名（旧口径，未收窄）"),
                "mode": ARGS.scope,
                "exclude_outside_nato": ARGS.scope != "all",
                "note": "仅统计纳统名单内小区；不在名单中的小区不做统计",
            },
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
        "service_attitude": {
            "category": SA_CAT,
            "scope": "全量工单（含纳统名单外小区），与「三、十四类治理效果」同源；"
                     "小区为热线上报名称，未与纳统档案归并",
            "period": f"{YEAR_NOW}年1-{MONTH_NOW}月 vs {YEAR_PREV}年1-{MONTH_NOW}月",
            "min_total": SA_MIN,
            "min_base_for_pct": SA_BASE_PCT,
            "totals": sa_totals,
            "companies": sa_companies,
            "communities": sa_communities,
        },
    }

    if ARGS.dry_run:
        print("\n[dry-run] 未写入 json")
    else:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存: {OUT}")


if __name__ == "__main__":
    main()
