#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recalc_rootcause_2026.py — 重算《物业投诉根因分析报告》分组统计（993 口径 · 2026年1-8月）

背景
----
报告第七节「六维 2026 年数据对比」的数据源 `scripts/root_cause_2026_data.json`
是 2026-09-03 由一次性脚本产出的，存在两个问题：
  1. 时间口径是 **2026 年 1-7 月**（与全站统一的 1-8 月不一致，且节标题已写成 1-8 月）；
  2. 小区范围是 **旧版 994 库**（如房屋性质 商品房 407 个，新版为 404/991 口径）。
本节另有 (6) 底部抬升 表把分组算成「23 / 21」两个小组，与 84 / 82 名单严重不符，属取数错误。

本脚本按 2026-09-28 项目组口径**重算**：
  · 小区范围 = 《纳统小区 (2026 更新版)》993 个名单内（`scripts/nato_match.py` 为唯一匹配口径源）
  · 聚合单元 = 纳统小区（主名／别名／曾用名 精确匹配后归并到主名）
  · 投诉数据 = 热线数据表口径（`data/merged_cleaned.pkl`）
  · 时间     = 2026 年 1-8 月；同比 = 2026年1-8月 vs 2025年1-8月
  · 平均投诉量 = mean(该组各小区 2026年1-8月 投诉量)
  · 每千户    = sum(2026年1-8月投诉量) / sum(总户数) × 1000

输出
----
  scripts/root_cause_2026_data_v2.json   （供报告回填；键名与旧 JSON 对齐 + 新增 per1k_2026）

用法
----
    PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/recalc_rootcause_2026.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import nato_match as NM  # noqa: E402  唯一匹配口径源

M8 = 8
OUT = os.path.join(ROOT, "scripts", "root_cause_2026_data_v2.json")


# ─────────────────────────────────────────────────────────────
# 基础数据
# ─────────────────────────────────────────────────────────────
def load_orders() -> pd.DataFrame:
    """热线工单 → 纳统主名（未命中的丢弃）。返回带 nato_name / year / month 的 df。"""
    df = pd.read_pickle(os.path.join(ROOT, "data", "merged_cleaned.pkl"))
    df = df[["community_name", "year", "month"]].copy()
    df = NM.aggregate_key(df, col="community_name", keep_id=False)
    df = df[df["nato_community"].astype(bool)]
    return df


def load_lib() -> pd.DataFrame:
    """993 纳统关联库 + 竣工日期（关联库 build_year 字段为常量占位，此处从档案补回）。"""
    lib = pd.read_pickle(os.path.join(ROOT, "data", "community_linked_data.pkl"))

    nato = NM.load_nato()
    # 竣工日期：档案原始列（nato_match 未导出，此处直读一次）
    import xlrd

    sh = xlrd.open_workbook(NM.NATO_XLS_NEW).sheet_by_index(0)
    hdr = [str(sh.cell_value(0, c)).strip() for c in range(sh.ncols)]
    ci_name, ci_year = hdr.index("小区名称"), hdr.index("竣工日期")

    def yv(r):
        v = sh.cell_value(r, ci_year)
        try:
            y = int(float(v))
        except (TypeError, ValueError):
            return np.nan
        return y if 1900 <= y <= 2030 else np.nan

    build = {}
    for r in range(1, sh.nrows):
        nm = str(sh.cell_value(r, ci_name)).strip()
        if nm:
            build[NM.norm(nm)] = yv(r)

    lib = lib.copy()
    lib["build_year"] = lib["community_name"].map(lambda x: build.get(NM.norm(x), np.nan))
    lib["age"] = 2026 - lib["build_year"]
    return lib


def group_stats(g: pd.DataFrame, cur: pd.Series, base: pd.Series) -> dict:
    """g = 该组小区在 lib 中的行；cur/base = 该组 2026年1-8月 / 2025年1-8月 投诉量（与 g 同序）。"""
    hh = g["total_households"].fillna(0).sum()
    c, b = float(cur.sum()), float(base.sum())
    return {
        "count": int(len(g)),
        "avg_2026": round(float(cur.mean()), 1) if len(g) else 0.0,
        "per1k_2026": round(c / hh * 1000, 1) if hh else 0.0,
        "yoy": round((c - b) / b * 100, 1) if b else None,
        "avg_3y": round(float(g["complaint_total"].mean()), 1) if len(g) else 0.0,
        "hh_avg": round(float(g["total_households"].mean()), 0) if len(g) else 0.0,
    }


def build(groups: dict, lib: pd.DataFrame, cur_map: pd.Series, base_map: pd.Series) -> dict:
    out = {}
    for label, mask in groups.items():
        g = lib[mask]
        names = g["community_name"].tolist()
        cur = cur_map.reindex(names).fillna(0)
        base = base_map.reindex(names).fillna(0)
        out[label] = group_stats(g, cur, base)
    return out


def main():
    print("读取热线工单并归并到纳统小区…")
    orders = load_orders()
    cur_map = orders[(orders["year"] == 2026) & (orders["month"] <= M8)] \
        .groupby("nato_community").size()
    base_map = orders[(orders["year"] == 2025) & (orders["month"] <= M8)] \
        .groupby("nato_community").size()
    print(f"  · 2026年1-8月 {int(cur_map.sum()):,} 件 ／ 2025年1-8月 {int(base_map.sum()):,} 件"
          f"（933 名单内）")

    lib = load_lib()
    inside = set(cur_map.index) | set(base_map.index) | set(
        lib.loc[lib["complaint_total"] > 0, "community_name"])
    print(f"  · 名单内 993 个；有过投诉记录的 {len(inside)} 个")

    res = {"period": "2026年1-8月", "compare": "2025年1-8月",
           "scope": "《纳统小区 (2026 更新版)》993 个",
           "total_2026_m8": int(cur_map.sum()), "total_2025_m8": int(base_map.sum())}

    # ── 房龄 ──────────────────────────────────────────────
    age_bins = [0, 10, 20, 30, 40, 10 ** 9]
    age_lab = ["10年以内", "10-20年", "20-30年", "30-40年", "40年以上"]
    cut = pd.cut(lib["age"], bins=age_bins, labels=age_lab, right=False)
    res["age"] = build({l: (cut == l) for l in age_lab}, lib, cur_map, base_map)

    # ── 房屋性质（只保留报告在用的大类） ───────────────────
    nat = ["直管公房", "售后房", "商品房", "混合"]
    res["nature"] = build({n: (lib["property_nature"] == n) for n in nat}, lib, cur_map, base_map)

    # ── 小区规模 ──────────────────────────────────────────
    sc_bins = [0, 200, 500, 1000, 2000, 10 ** 9]
    sc_lab = ["微型(<200户)", "小型(200-500)", "中型(500-1000)", "大型(1000-2000)", "超大型(>2000)"]
    cut = pd.cut(lib["total_households"], bins=sc_bins, labels=sc_lab, right=False)
    res["scale"] = build({l: (cut == l) for l in sc_lab}, lib, cur_map, base_map)

    # ── 电梯台数 ──────────────────────────────────────────
    e = lib["elevator_total"].fillna(0)
    elev = {
        "无电梯": e == 0, "1-5台": (e > 0) & (e <= 5), "6-10台": (e > 5) & (e <= 10),
        "11-20台": (e > 10) & (e <= 20), "20台以上": e > 20,
    }
    res["elevator_detail"] = build(elev, lib, cur_map, base_map)
    res["elevator"] = {
        "无电梯": res["elevator_detail"]["无电梯"],
        "有电梯": group_stats(lib[e > 0], cur_map.reindex(lib.loc[e > 0, "community_name"]).fillna(0),
                          base_map.reindex(lib.loc[e > 0, "community_name"]).fillna(0)),
    }

    # ── 修缮 ──────────────────────────────────────────────
    r = lib["repair_project_count"].fillna(0)
    res["repair"] = build({"有修缮": r > 0, "无修缮": r == 0}, lib, cur_map, base_map)

    # ── 底部抬升（两级口径） ───────────────────────────────
    bl = lib["is_bottom_lift"].astype(bool)
    res["bottom_lift"] = build({"普通小区": ~bl, "底部抬升": bl}, lib, cur_map, base_map)
    res["bottom_lift"]["_caliber"] = (
        f"名单 84 个重点小区，其中 82 个在《纳统小区 (2026 更新版)》档案内、"
        f"{int((bl & (lib['complaint_total'] > 0)).sum())} 个全周期有投诉记录；"
        f"本表按档案内 82 个计，投诉量统计口径为 2026年1-8月 vs 2025年1-8月"
    )

    # ── 7.2 / 7.3 单月快照（7月、8月）+ 1-8月累计 ─────────────
    raw = pd.read_pickle(os.path.join(ROOT, "data", "merged_cleaned.pkl"))
    r26, r25 = raw[raw["year"] == 2026], raw[raw["year"] == 2025]

    def snap(keys, col):
        rows = []
        for k in keys:
            a, b = r26[r26[col] == k], r25[r25[col] == k]
            m7, p7 = int((a["month"] == 7).sum()), int((b["month"] == 7).sum())
            m8, p8m = int((a["month"] == 8).sum()), int((b["month"] == 8).sum())
            t8, p8 = int((a["month"] <= M8).sum()), int((b["month"] <= M8).sum())
            t7 = int((a["month"] <= 7).sum())
            ncom = a[a["month"] <= M8]["community_name"].nunique()
            rows.append({
                "name": k, "m7": m7, "m7_prev": p7,
                "m7_yoy": round((m7 - p7) / p7 * 100, 1) if p7 else None,
                "t7": t7, "avg7": round(t7 / ncom, 1) if ncom else 0.0,
                "t8": t8, "avg8": round(t8 / ncom, 1) if ncom else 0.0,
                "m8_yoy": round((t8 - p8) / p8 * 100, 1) if p8 else None,
                # 8 月单月（7.4 / 7.5 快照用）
                "aug": m8, "aug_prev": p8m,
                "aug_yoy": round((m8 - p8m) / p8m * 100, 1) if p8m else None,
            })
        rows.sort(key=lambda r: -(r["m8_yoy"] if r["m8_yoy"] is not None else -999))
        return rows

    streets = [s for s in r26["street"].dropna().unique() if str(s).strip()]
    cats = [c for c in r26["category_14"].dropna().unique() if str(c).strip()]
    res["street_snapshot"] = snap(sorted(streets), "street")
    res["category_snapshot"] = snap(sorted(cats), "category_14")
    res["july_total"] = {"m7": int((r26["month"] == 7).sum()),
                         "m7_prev": int((r25["month"] == 7).sum()),
                         "m6": int((r26["month"] == 6).sum())}
    res["august_total"] = {"m8": int((r26["month"] == 8).sum()),
                           "m8_prev": int((r25["month"] == 8).sum()),
                           "m7": int((r26["month"] == 7).sum())}

    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ── 打印校验 ──────────────────────────────────────────
    def show(title, d, keys=None):
        print(f"\n【{title}】")
        print(f"  {'分组':<16}{'小区数':>6}{'1-8月均值':>10}{'每千户':>9}{'同比':>9}{'三年均值':>9}{'平均户数':>9}")
        for k, v in d.items():
            if k.startswith("_"):
                continue
            yy = f"{v['yoy']:+.1f}%" if v["yoy"] is not None else "—"
            print(f"  {k:<16}{v['count']:>6}{v['avg_2026']:>10.1f}{v['per1k_2026']:>9.1f}"
                  f"{yy:>9}{v['avg_3y']:>9.1f}{v['hh_avg']:>9.0f}")

    show("（1）房龄", res["age"])
    show("（2）房屋性质", res["nature"])
    show("（3）小区规模", res["scale"])
    show("（4）电梯台数", res["elevator_detail"])
    show("（5）修缮", res["repair"])
    show("（6）底部抬升", res["bottom_lift"])
    print(f"\n  {res['bottom_lift']['_caliber']}")

    print(f"\n【7.2 街道快照】全区 7月 {res['july_total']['m7']:,}（{res['july_total']['m7_prev']:,}）"
          f"环比6月 {res['july_total']['m6']:,}")
    for r in res["street_snapshot"]:
        print(f"  {r['name']:<6} 7月={r['m7']:>4} 去年7月={r['m7_prev']:>4} {r['m7_yoy']:>+6.1f}%"
              f" | 1-8月={r['t8']:>5} 均值={r['avg8']:>5.1f} 同比={r['m8_yoy']:>+6.1f}%")
    print("\n【7.3 类别快照】")
    for r in res["category_snapshot"]:
        print(f"  {r['name']:<12} 7月={r['m7']:>4} 去年7月={r['m7_prev']:>4} {r['m7_yoy']:>+6.1f}%"
              f" | 1-8月={r['t8']:>5} 同比={r['m8_yoy']:>+6.1f}%")

    at = res["august_total"]
    print(f"\n【7.4 8月街道快照】全区 8月 {at['m8']:,}（{at['m8_prev']:,}）"
          f"环比7月 {at['m7']:,}")
    for r in res["street_snapshot"]:
        print(f"  {r['name']:<6} 8月={r['aug']:>4} 去年8月={r['aug_prev']:>4} {r['aug_yoy']:>+6.1f}%"
              f" | 1-8月={r['t8']:>5} 同比={r['m8_yoy']:>+6.1f}%")
    print("\n【7.5 8月类别快照】")
    for r in res["category_snapshot"]:
        print(f"  {r['name']:<12} 8月={r['aug']:>4} 去年8月={r['aug_prev']:>4} {r['aug_yoy']:>+6.1f}%"
              f" | 1-8月={r['t8']:>5} 同比={r['m8_yoy']:>+6.1f}%")

    print(f"\n已写入 {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
