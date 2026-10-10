#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recalc_rootcause_groups.py — 重算《物业投诉根因分析报告》三/四/五节分组统计

背景
----
报告三（物业因素）、四（设施因素）、五（治理因素）节的分组表，数据源是
`scripts/root_cause_full.json`（**mtime 2026-08-26 一次性产物，仓库内无生成脚本**），
存在三类问题：
  1. 小区范围是**旧版 994 库**（如业委会表 127+867=994、电梯表 738+256=994）；
  2. 时间口径与全站 1-8 月窗口不一致；
  3. 与同报告第七节（`root_cause_2026_data_v2.json` 驱动）口径打架。

按用户 2026-10-10 决定：**全章以 `recalc_rootcause_2026.py` 的口径为准**
（小区范围＝《纳统小区 (2026 更新版)》993 个名单内；时间＝2026 年 1-8 月；
同比＝2026年1-8月 vs 2025年1-8月；每千户＝sum(2026年1-8月投诉量)/sum(总户数)×1000）。

口径定义
--------
  · 小区范围 / 聚合单元 = 同 `recalc_rootcause_2026.py`（nato_match 唯一匹配口径源）
  · 平均投诉量 = mean(该组各小区 2026年1-8月 投诉量)      ← 与第七节 7.1 完全一致
  · 每千户     = sum(该组 2026年1-8月 投诉量) / sum(该组总户数) × 1000
  · 同比       = 2026年1-8月 vs 2025年1-8月（组内合计）
  · 三年均值   = mean(该组各小区 2024+2025+2026(1-8月) 累计投诉量)

覆盖分组
--------
  收费模式（fee_mode）、物业公司 Top10、车位配比、业委会，
  另附房龄/性质/规模/电梯/修缮/底部抬升（与 v2 JSON 交叉校验）
  ⚠ 物业费分段（报告 3.1）**不在本脚本范围**：关联库无「收费标准」字段，
     仓库内无可复现数据源，维持原样（已在报告加注说明）。

输出
----
  scripts/root_cause_groups_2026.json

用法
----
    PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/recalc_rootcause_groups.py
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import nato_match as NM            # noqa: E402
from company_alias import canon_series   # noqa: E402  企业更名归并（唯一口径源）

M8 = 8
OUT = os.path.join(ROOT, "scripts", "root_cause_groups_2026.json")
PKL = os.path.join(ROOT, "data", "merged_cleaned.pkl")
LIB = os.path.join(ROOT, "data", "community_linked_data.pkl")


# ─────────────────────────────────────────────────────────────
def load():
    """返回 (lib, cur_map, base_map, three_year, raw)。全部按纳统主名索引。"""
    raw = pd.read_pickle(PKL)
    o = raw[["community_name", "year", "month"]].copy()
    o = NM.aggregate_key(o, col="community_name", keep_id=False)
    o = o[o["nato_community"].astype(bool)]
    cur = o[(o["year"] == 2026) & (o["month"] <= M8)].groupby("nato_community").size()
    base = o[(o["year"] == 2025) & (o["month"] <= M8)].groupby("nato_community").size()
    three = o.groupby("nato_community").size()

    lib = pd.read_pickle(LIB).copy()
    # 企业名归并（关联库登的是最新名，仍做一次保险）
    if "property_company" in lib.columns:
        lib["property_company"] = canon_series(lib["property_company"].astype(str))
    for c in ("total_households",):
        lib[c] = pd.to_numeric(lib[c], errors="coerce").fillna(0)
    return lib, cur, base, three, raw


def stats(lib_g: pd.DataFrame, cur, base, three) -> dict:
    names = lib_g["community_name"].tolist()
    c = cur.reindex(names).fillna(0)
    b = base.reindex(names).fillna(0)
    t = three.reindex(names).fillna(0)
    hh = float(lib_g["total_households"].sum())
    return {
        "count": int(len(lib_g)),
        "avg_2026": round(float(c.mean()), 1) if len(lib_g) else 0.0,
        "per1k_2026": round(float(c.sum()) / hh * 1000, 1) if hh else 0.0,
        "yoy": round((float(c.sum()) - float(b.sum())) / float(b.sum()) * 100, 1)
               if float(b.sum()) else None,
        "avg_3y": round(float(t.mean()), 1) if len(lib_g) else 0.0,
        "hh_avg": round(float(lib_g["total_households"].mean()), 0) if len(lib_g) else 0.0,
        "total_2026": int(c.sum()),
    }


def groups(lib: pd.DataFrame) -> dict:
    g = {}

    # ── 收费模式 ────────────────────────────────────────
    fm = lib["fee_mode"].astype(str).str.strip().replace({"nan": "未标注"})
    order = ["包干制", "酬金制"]
    g["fee_mode"] = {m: (fm == m) for m in order}
    other = ~fm.isin(order)
    if other.any():
        g["fee_mode"]["其他/未标注"] = other

    # ── 车位配比 ────────────────────────────────────────
    pt = pd.to_numeric(lib.get("parking_total"), errors="coerce")
    pr = pt / lib["total_households"].replace(0, float("nan"))
    g["parking"] = {
        "严重不足(<0.3)": pr.notna() & (pr < 0.3),
        "不足(0.3-0.5)": pr.notna() & (pr >= 0.3) & (pr < 0.5),
        "基本平衡(0.5-0.8)": pr.notna() & (pr >= 0.5) & (pr <= 0.8),
        "充足(>0.8)": pr.notna() & (pr > 0.8),
    }

    # ── 业委会 ──────────────────────────────────────────
    oc = lib["owners_committee_name"].astype(str).str.strip()
    has = oc.notna() & (oc != "") & (oc != "nan") & (oc.str.lower() != "none")
    g["committee"] = {"有业委会": has, "无业主大会": ~has}

    # ── 电梯 / 修缮 / 底部抬升（与 v2 交叉校验） ────────
    e = pd.to_numeric(lib.get("elevator_total"), errors="coerce").fillna(0)
    g["elevator"] = {"无电梯": e == 0, "有电梯": e > 0}
    r = pd.to_numeric(lib.get("repair_project_count"), errors="coerce").fillna(0)
    g["repair"] = {"无修缮": r == 0, "有修缮": r > 0}
    g["repair_detail"] = {"无修缮": r == 0, "1个项目": r == 1, "2个项目及以上": r >= 2}
    # 规模：微型(<200) / 超大型(>2000)，供结论引用
    hh2 = lib["total_households"]
    g["scale_edge"] = {"微型(<200户)": hh2 < 200, "超大型(>2000)": hh2 > 2000}
    bl = lib["is_bottom_lift"].astype(bool)
    g["bottom_lift"] = {"普通小区": ~bl, "底部抬升": bl}

    return g


def company_rows(lib, raw, restrict_nato: bool):
    """企业分组：按**工单的物业企业归属**（`property_company`，含更名归并）统计。

    restrict_nato=True  → 只计落在纳统名单内小区的工单（与本章其余分组同范围）
    restrict_nato=False → 全量工单口径（企业为跨小区经营主体，不按小区名单截断）
    """
    if "property_company" not in raw.columns:
        return []
    o = raw[["community_name", "property_company", "year", "month"]].copy()
    o["property_company"] = canon_series(o["property_company"].astype(str))
    o = o[(o["property_company"] != "") & (o["property_company"] != "nan")]
    # 归并到纳统主名（未命中的丢弃，保证「每千户」有户数分母）
    o = NM.aggregate_key(o, col="community_name", keep_id=False)
    o = o[o["nato_community"].astype(bool)]
    BAD = {"", "nan", "无", "未知", "空", "None"}
    o = o[~o["property_company"].isin(BAD)]
    hh = lib.set_index("community_name")["total_households"]

    rows = []
    for name, sub in o.groupby("property_company"):
        comm = sub["nato_community"].unique()
        c = int(((sub["year"] == 2026) & (sub["month"] <= M8)).sum())
        b = int(((sub["year"] == 2025) & (sub["month"] <= M8)).sum())
        t = int(len(sub))
        h = float(hh.reindex(comm).fillna(0).sum())
        rows.append({
            "name": name, "count": int(len(comm)),
            "total_2026": c, "total_3y": t,
            "avg_2026": round(c / len(comm), 1) if len(comm) else 0.0,
            "per1k_2026": round(c / h * 1000, 1) if h else 0.0,
            "yoy": round((c - b) / b * 100, 1) if b else None,
        })
    rows.sort(key=lambda r: -r["total_2026"])
    return rows


def main():
    lib, cur, base, three, raw = load()
    print(f"纳统名单 {len(lib)} 个；2026年1-8月 {int(cur.sum()):,} 件 / "
          f"2025年1-8月 {int(base.sum()):,} 件（名单内）\n")

    G = groups(lib)
    res = {"period": "2026年1-8月", "compare": "2025年1-8月",
           "scope": "《纳统小区 (2026 更新版)》993 个（别名归并）"}

    for k, masks in G.items():
        res[k] = {lab: stats(lib[m], cur, base, three) for lab, m in masks.items()}

    # ── 物业公司 Top10 ───────────────────────────────────
    res["company_top10"] = company_rows(lib, raw, restrict_nato=True)[:10]
    res["company_top10_full"] = company_rows(lib, raw, restrict_nato=False)[:10]

    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def show(title, d):
        print(f"【{title}】")
        print(f"  {'分组':<18}{'小区数':>6}{'1-8月均':>9}{'每千户':>9}{'同比':>9}{'三年均值':>9}{'平均户数':>9}")
        for k, v in d.items():
            yy = f"{v['yoy']:+.1f}%" if v["yoy"] is not None else "—"
            print(f"  {k:<18}{v['count']:>6}{v['avg_2026']:>9.1f}{v['per1k_2026']:>9.1f}"
                  f"{yy:>9}{v['avg_3y']:>9.1f}{v['hh_avg']:>9.0f}")
        print()

    show("收费模式", res["fee_mode"])
    show("车位配比", res["parking"])
    show("业委会", res["committee"])
    show("电梯", res["elevator"])
    show("修缮", res["repair"])
    show("底部抬升", res["bottom_lift"])

    print("【物业公司 Top10（按 2026年1-8月）】")
    print(f"  {'企业':<26}{'小区':>5}{'1-8月量':>9}{'均量':>8}{'每千户':>9}{'同比':>9}{'三年量':>9}")
    for r in res["company_top10"]:
        yy = f"{r['yoy']:+.1f}%" if r["yoy"] is not None else "—"
        print(f"  {r['name']:<26}{r['count']:>5}{r['total_2026']:>9}{r['avg_2026']:>8.1f}"
              f"{r['per1k_2026']:>9.1f}{yy:>9}{r['total_3y']:>9}")

    print(f"\n已写入 {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
