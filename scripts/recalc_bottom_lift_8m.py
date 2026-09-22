# -*- coding: utf-8 -*-
"""
底部抬升小区 2026 年口径统一：上半年(1-6月) -> 1-8月

背景：
  《底部抬升小区热线数据分析报告》原有 2026 年统计一律采用"上半年(1-6月)"口径，
  与项目其余报告（2026年1-8月）不一致。本脚本按同一匹配口径重算 2026年1-8月 数据，
  并生成 bottom_lift_2026_8m.json 供报告回填使用。

匹配口径（与既有报告完全一致，已回归验证）：
  名单：scripts/bottom_lift_communities.json（84个小区）
  数据源：data/merged_cleaned.pkl（66,812条全量工单）
  匹配：小区名精确匹配 76 个 + 2 个别名映射 = 78 个匹配成功
       - 钦州路111弄小区 -> 钦州路111弄
       - 漓江花园       -> 漓江花园（领馆壹号院）
  回归校验：2024全年4510 / 2025全年4263 / 2025上半年2057 / 2026上半年1662 全部复现
"""
import json
import os
import sys

import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

DATA_PKL = os.path.join(BASE, "data", "merged_cleaned.pkl")
LIST_JSON = os.path.join(BASE, "scripts", "bottom_lift_communities.json")
OUT_JSON = os.path.join(BASE, "scripts", "bottom_lift_2026_8m.json")

# 别名映射：名单名 -> merged_cleaned 中的标准小区名
ALIAS = {
    "钦州路111弄小区": "钦州路111弄",
    "漓江花园": "漓江花园（领馆壹号院）",
}

M8 = 8  # 1-8月


def pct(new, old):
    """同比/变化率，old 为 0 时返回 None"""
    if old in (0, None):
        return None
    return round((new - old) / old * 100, 1)


def load():
    df = pd.read_pickle(DATA_PKL)
    blist = json.load(open(LIST_JSON, encoding="utf-8"))
    present = set(df["community_name"].dropna())
    # 名单名 -> 元数据（仅保留在数据源中真实命中的 78 个）
    name_map = {}
    for c in blist:
        std = ALIAS.get(c["name"], c["name"])
        if std in present:
            name_map[std] = c
    df["_is_bl"] = df["community_name"].isin(name_map.keys())
    return df, blist, name_map


def period_mask(df, year, max_month):
    return (df["year"] == year) & (df["month"] <= max_month)


def level_table(sub, name_map, prev_y, cur_y, max_month, thr=0.05):
    """小区级变化统计。

    有效对比：两期合计 > 0（即至少一期有工单）
    判定阈值：±5%（与既有报告"2026上半年 vs 2025上半年"口径一致，
              已回归复现 43个改善 / 29个恶化）
    """
    rows = []
    for std, meta in name_map.items():
        g = sub[sub["community_name"] == std]
        a = int(len(g[(g["year"] == prev_y) & (g["month"] <= max_month)]))
        b = int(len(g[(g["year"] == cur_y) & (g["month"] <= max_month)]))
        rows.append({"name": meta["name"], "street": meta["street"], "prev": a, "cur": b,
                     "chg": pct(b, a) if a else None})
    valid = [r for r in rows if r["prev"] + r["cur"] > 0]
    down = [r for r in valid if r["cur"] < r["prev"] * (1 - thr)]
    up = [r for r in valid if r["cur"] > r["prev"] * (1 + thr)]
    down_ids = {id(r) for r in down}
    up_ids = {id(r) for r in up}
    flat = [r for r in valid if id(r) not in down_ids and id(r) not in up_ids]
    n = len(valid)
    return {
        "valid": n,
        "down": len(down), "up": len(up), "flat": len(flat),
        "down_pct": round(len(down) / n * 100, 1) if n else 0,
        "up_pct": round(len(up) / n * 100, 1) if n else 0,
        "flat_pct": round(len(flat) / n * 100, 1) if n else 0,
        "rows": rows, "down_rows": down, "up_rows": up,
    }


def main():
    df, blist, name_map = load()
    sub = df[df["_is_bl"]].copy()
    sub["_street"] = sub["community_name"].map(lambda n: name_map[n]["street"])
    sub["_ctype"] = sub["community_name"].map(lambda n: name_map[n]["contradiction_type"])

    res = {}

    # ---------- 一、总体概况 ----------
    periods = [
        ("y2024", 2024, 12),
        ("y2025", 2025, 12),
        ("m8_2025", 2025, M8),
        ("m8_2026", 2026, M8),
        ("h1_2025", 2025, 6),   # 保留旧口径用于回归校验
        ("h1_2026", 2026, 6),
    ]
    overall, allx = {}, {}
    for key, y, m in periods:
        mk = period_mask(df, y, m)
        overall[key] = int(len(sub[period_mask(sub, y, m)]))
        allx[key] = int(mk.sum())
    res["overall"] = overall
    res["all_xuhui"] = allx
    res["share"] = {
        "y2024": round(overall["y2024"] / allx["y2024"] * 100, 1),
        "y2025": round(overall["y2025"] / allx["y2025"] * 100, 1),
        "m8_2025": round(overall["m8_2025"] / allx["m8_2025"] * 100, 1),
        "m8_2026": round(overall["m8_2026"] / allx["m8_2026"] * 100, 1),
    }
    res["yoy"] = {
        "y2025_vs_2024": pct(overall["y2025"], overall["y2024"]),
        "m8_2026_vs_m8_2025": pct(overall["m8_2026"], overall["m8_2025"]),
        "h1_2026_vs_h1_2025": pct(overall["h1_2026"], overall["h1_2025"]),
        "all_y2025_vs_2024": pct(allx["y2025"], allx["y2024"]),
        "all_m8_2026": pct(allx["m8_2026"], allx["m8_2025"]),
    }
    # 与全区的百分点差（pp）
    res["pp"] = {
        "y2025_vs_all": round(res["yoy"]["y2025_vs_2024"] - res["yoy"]["all_y2025_vs_2024"], 1),
        "m8_2026_vs_all": round(res["yoy"]["m8_2026_vs_m8_2025"] - res["yoy"]["all_m8_2026"], 1),
    }
    res["matched"] = len(name_map)

    # ---------- 三、街道分布 ----------
    streets = []
    for st in sorted(set(c["street"] for c in blist)):
        # 重点小区数 = 该街道在热线数据中真实匹配上的小区数（合计78个）
        n_comm = sum(1 for n, m in name_map.items() if m["street"] == st)
        s = sub[sub["_street"] == st]
        rec = {
            "street": st,
            "n_community": n_comm,
            "y2024": int(len(s[s["year"] == 2024])),
            "y2025": int(len(s[s["year"] == 2025])),
            "m8_2025": int(len(s[(s["year"] == 2025) & (s["month"] <= M8)])),
            "m8_2026": int(len(s[(s["year"] == 2026) & (s["month"] <= M8)])),
        }
        rec["yoy_2025"] = pct(rec["y2025"], rec["y2024"])
        rec["yoy_m8"] = pct(rec["m8_2026"], rec["m8_2025"])
        streets.append(rec)
    streets.sort(key=lambda x: (x["yoy_m8"] if x["yoy_m8"] is not None else 999))
    res["street_stats"] = streets

    # ---------- 四、问题类别 ----------
    cats = []
    for cat, g in sub.groupby("category_14"):
        rec = {
            "category": cat,
            "y2024": int(len(g[g["year"] == 2024])),
            "y2025": int(len(g[g["year"] == 2025])),
            "m8_2025": int(len(g[(g["year"] == 2025) & (g["month"] <= M8)])),
            "m8_2026": int(len(g[(g["year"] == 2026) & (g["month"] <= M8)])),
        }
        rec["yoy_2025"] = pct(rec["y2025"], rec["y2024"])
        rec["yoy_m8"] = pct(rec["m8_2026"], rec["m8_2025"])
        cats.append(rec)
    cats.sort(key=lambda x: -x["m8_2026"])
    res["category_stats"] = cats

    # ---------- 五、矛盾类型 ----------
    ct_label = {"1": "一类（收费/服务）", "2": "二类（设施/房屋）", "3": "三类（业委会/治理）"}
    ctypes = []
    for ct in ["1", "2", "3"]:
        n_comm = sum(1 for m in name_map.values() if str(m["contradiction_type"]) == ct)
        g = sub[sub["_ctype"] == ct]
        rec = {
            "type": ct,
            "label": ct_label[ct],
            "n_community": n_comm,
            "y2024": int(len(g[g["year"] == 2024])),
            "y2025": int(len(g[g["year"] == 2025])),
            "m8_2025": int(len(g[(g["year"] == 2025) & (g["month"] <= M8)])),
            "m8_2026": int(len(g[(g["year"] == 2026) & (g["month"] <= M8)])),
        }
        rec["yoy_2025"] = pct(rec["y2025"], rec["y2024"])
        rec["yoy_m8"] = pct(rec["m8_2026"], rec["m8_2025"])
        ctypes.append(rec)
    res["contradiction_stats"] = ctypes

    # ---------- 六、小区级变化 ----------
    res["community_change_2025"] = level_table(sub, name_map, 2024, 2025, 12)
    res["community_change_m8"] = level_table(sub, name_map, 2025, 2026, M8)
    # 回归校验用：旧"上半年"口径应复现 43个改善 / 29个恶化
    res["community_change_h1"] = level_table(sub, name_map, 2025, 2026, 6)

    # ---------- 七、重点小区榜单 ----------
    # 7.1 投诉量 Top10（2026年1-8月）
    top_vol = []
    for std, meta in name_map.items():
        g = sub[sub["community_name"] == std]
        rec = {
            "name": meta["name"], "street": meta["street"],
            "m8_2026": int(len(g[(g["year"] == 2026) & (g["month"] <= M8)])),
            "m8_2025": int(len(g[(g["year"] == 2025) & (g["month"] <= M8)])),
            "y2025": int(len(g[g["year"] == 2025])),
            "y2024": int(len(g[g["year"] == 2024])),
        }
        rec["yoy_m8"] = pct(rec["m8_2026"], rec["m8_2025"])
        top_vol.append(rec)
    top_vol.sort(key=lambda x: -x["m8_2026"])
    res["top10_volume_m8"] = top_vol[:10]

    # 7.2 改善幅度 Top10（2026年1-8月 vs 2025年1-8月），门槛 prev>=15
    cand = [r for r in top_vol if r["m8_2025"] >= 15 and r["yoy_m8"] is not None]
    cand.sort(key=lambda x: x["yoy_m8"])
    res["top10_improve_m8"] = cand[:10]

    # ---------- 七-2 底部抬升 vs 普通小区 ----------
    bl_set = set(name_map.keys())
    other = df[~df["_is_bl"] & df["community_name"].notna() & (df["community_name"] != "无")]
    n_other = other["community_name"].nunique()
    res["vs_normal"] = {
        "bl_m8_2026": overall["m8_2026"],
        "bl_m8_2025": overall["m8_2025"],
        "bl_yoy": pct(overall["m8_2026"], overall["m8_2025"]),
        "bl_avg": round(overall["m8_2026"] / len(bl_set), 1),
        "normal_m8_2026": int(len(other[(other["year"] == 2026) & (other["month"] <= M8)])),
        "normal_m8_2025": int(len(other[(other["year"] == 2025) & (other["month"] <= M8)])),
        "normal_comm": int(n_other),
    }
    res["vs_normal"]["normal_yoy"] = pct(res["vs_normal"]["normal_m8_2026"], res["vs_normal"]["normal_m8_2025"])
    res["vs_normal"]["normal_avg"] = round(res["vs_normal"]["normal_m8_2026"] / n_other, 1) if n_other else 0
    res["vs_normal"]["pp"] = round(res["vs_normal"]["bl_yoy"] - res["vs_normal"]["normal_yoy"], 1)

    # ---------- 月度序列（供图表核对） ----------
    monthly = {"2024": [], "2025": [], "2026": []}
    for y in (2024, 2025, 2026):
        for m in range(1, 13):
            n = int(len(sub[(sub["year"] == y) & (sub["month"] == m)]))
            monthly[str(y)].append(n if n else None)
    res["monthly"] = monthly

    json.dump(res, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------- 控制台输出 ----------
    print("=== 回归校验（应与既有报告一致）===")
    print(f"2024全年 {overall['y2024']} (期望4510) | 2025全年 {overall['y2025']} (期望4263)")
    print(f"2025上半年 {overall['h1_2025']} (期望2057) | 2026上半年 {overall['h1_2026']} (期望1662)")
    print(f"全区 2025上半年 {allx['h1_2025']} (期望11516) | 2026上半年 {allx['h1_2026']} (期望9387)")
    print()
    print("=== 2026年1-8月新口径 ===")
    print(f"底部抬升 2025年1-8月 {overall['m8_2025']} -> 2026年1-8月 {overall['m8_2026']} = {res['yoy']['m8_2026_vs_m8_2025']}%")
    print(f"全区     2025年1-8月 {allx['m8_2025']} -> 2026年1-8月 {allx['m8_2026']} = {res['yoy']['all_m8_2026']}%")
    print(f"pp差：2025年 {res['pp']['y2025_vs_all']}pp | 2026年1-8月 {res['pp']['m8_2026_vs_all']}pp")
    print()
    print("=== 街道（按2026年1-8月同比升序）===")
    for r in streets:
        print(f"{r['street']:<6} 小区{r['n_community']:>2} 2024={r['y2024']:>4} 2025={r['y2025']:>4} "
              f"2025年1-8月={r['m8_2025']:>4} 2026年1-8月={r['m8_2026']:>4} "
              f"2025同比={r['yoy_2025']}% 1-8月同比={r['yoy_m8']}%")
    print()
    print("=== 小区级变化回归（旧上半年口径，应≈43改善/29恶化）===")
    h1 = res["community_change_h1"]
    print(f"有效{h1['valid']} 改善{h1['down']} 恶化{h1['up']} 持平{h1['flat']}")
    print()
    print("=== 小区级变化（2026年1-8月 vs 2025年1-8月）===")
    cc = res["community_change_m8"]
    print(f"有效{cc['valid']}个 改善{cc['down']}({cc['down_pct']}%) 恶化{cc['up']}({cc['up_pct']}%) 持平{cc['flat']}({cc['flat_pct']}%)")
    print()
    print("=== 问题类别（2026年1-8月）===")
    for r in res["category_stats"]:
        print(f"{r['category']:<12} 2024={r['y2024']:>4} 2025={r['y2025']:>4} "
              f"2025年1-8月={r['m8_2025']:>4} 2026年1-8月={r['m8_2026']:>4} "
              f"2025同比={r['yoy_2025']}% 1-8月同比={r['yoy_m8']}%")
    print()
    print("=== 矛盾类型（2026年1-8月）===")
    for r in res["contradiction_stats"]:
        print(f"{r['label']:<14} 小区{r['n_community']:>2} 2024={r['y2024']:>4} 2025={r['y2025']:>4} "
              f"2025年1-8月={r['m8_2025']:>4} 2026年1-8月={r['m8_2026']:>4} "
              f"2025同比={r['yoy_2025']}% 1-8月同比={r['yoy_m8']}%")
    print()
    print("=== 投诉量Top10（2026年1-8月）===")
    for i, r in enumerate(res["top10_volume_m8"], 1):
        print(f"{i:>2} {r['name']:<12} {r['street']:<6} {r['m8_2026']:>3}件 (2025同期{r['m8_2025']:>3}) {r['yoy_m8']}%")
    print()
    print("=== 改善幅度Top10（2026年1-8月 vs 2025年1-8月, 基数>=15）===")
    for i, r in enumerate(res["top10_improve_m8"], 1):
        print(f"{i:>2} {r['name']:<12} {r['street']:<6} {r['m8_2025']:>3}->{r['m8_2026']:>3} {r['yoy_m8']}%")
    print()
    print("=== vs 普通小区 ===")
    print(res["vs_normal"])
    print()
    print("输出：", OUT_JSON)


if __name__ == "__main__":
    main()
