#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_linked_data.py — 以《纳统小区 (2026 更新版)》为主表重建小区级关联库（唯一口径源）

背景
----
项目组 2026-09-28 决策：**全站统一到《纳统小区 (2026 更新版).xls》（993 个）**，
不再使用旧版关联库的 994 口径；**所有投诉按热线数据表口径统计**。

旧库 `data/community_linked_data.pkl` 建于 2026-09-03，热线字段是**截至 2026 年 7 月**
的快照（complaint 合计 61,348 件；报告中「64,570 件」＝ 2024.1–2026.7 工单总数）。

⚠️ 实测发现：**旧库主表并非《纳统小区.xls》** —— 二者虽同为 994 行，但户数有 8 处不同
（园南一村 1372/1373、吉象小区 10/107、华容苑 85/162 等）、名称用半角括号
（`梅陇十一村(A块)` vs 档案 `梅陇十一村（A块）`）、且「钦州大厦」只在旧库存在。
故本脚本**不复现旧库**，而是以档案为准**独立重建**，仅失信/hotline_2025 两项无源字段从旧库迁移。

本脚本以 2026 更新版档案为主表，**重跑匹配链路**：
  主表 21 列 ← 《纳统小区 (2026 更新版).xls》
  电梯     ← 徐汇各科室业务数据/电梯基本信息.xlsx
  修缮     ← 徐汇各科室业务数据/修缮项目.xlsx
  底部抬升 ← 徐汇各科室业务数据/底部抬升84个小区0403.xlsx（82 个小区 / 5 类问题）
  热线投诉 ← data/merged_cleaned.pkl（按纳统小区聚合，2024 / 2025 / 2026年1-8月）
  失信计分、hotline_2025 ← 从旧库**迁移**（原始数据源已不在项目目录内，仅 18 / 82 个小区）

口径要点
--------
· 匹配单元＝纳统小区：统一走 `nato_match.build_map()`（主名 + 别名 + 2026 版曾用名，精确匹配）
· 投诉：2026 年取 **1-8 月**（与全站口径一致）；旧库为 1-7 月快照，本脚本会同步更新
· 994 → 993 的三处差异：删「钦州大厦」、合并「尚海湾二期+尚海湾豪庭」→「尚海湾豪庭小区（北区）」、
  新增「宛南家园」

输出
----
  data/community_linked_data.pkl        993 行 × 45 列（覆盖旧库，旧库自动备份）
  data/community_linked_data.csv        同内容 CSV
  data/data_link_quality.json           9 类数据源的匹配质量（复算）

用法
----
  python3 scripts/build_linked_data.py --dry-run       # 只对比，不写文件
  python3 scripts/build_linked_data.py                 # 正式重建（默认 2026 更新版）
  python3 scripts/build_linked_data.py --version old   # 用旧档案重建，用于复现验证
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
import nato_match as NM  # noqa: E402

DEPT = os.path.join(ROOT, "徐汇各科室业务数据")
DATA = os.path.join(ROOT, "data")
PKL = os.path.join(DATA, "community_linked_data.pkl")
CSV = os.path.join(DATA, "community_linked_data.csv")
QLTY = os.path.join(DATA, "data_link_quality.json")
MAIN = os.path.join(DATA, "merged_cleaned.pkl")

NATO_XLS = {
    "new": os.path.join(DEPT, "纳统小区 (2026 更新版).xls"),
    "old": os.path.join(DEPT, "纳统小区.xls"),
}

# 旧库 45 列的固定顺序（新库必须与之逐列对齐，下游脚本按列名取值）
COLS = [
    "community_id", "community_name", "street", "property_nature", "property_type",
    "build_year", "total_build_area", "total_households", "total_buildings",
    "property_company", "property_qualification", "property_service_type", "fee_mode",
    "parking_ground", "parking_underground", "owners_committee_name", "committee_term",
    "is_closed", "commercial_area_ratio", "district_area", "community_addr",
    "elevator_total", "elevator_done", "elevator_building",
    "repair_project_count", "repair_total_invest", "repair_total_area",
    "repair_years", "repair_types",
    "dishonest_count", "dishonest_total_score",
    "is_bottom_lift", "bottom_lift_type",
    "hotline_2025",
    "bl_cat_hotline", "bl_cat_low_fee", "bl_cat_fall_risk", "bl_cat_single_prop",
    "bl_cat_no_committee",
    "complaint_total", "complaint_2024", "complaint_2025", "complaint_2026",
    "complaint_yoy_2025", "parking_total",
]

# 档案列 → 旧库列（主表 21 列）
ARCHIVE_MAP = {
    "小区sectId": "community_id",
    "小区名称": "community_name",
    "街道": "street",
    "小区性质": "property_nature",
    "小区类型": "property_type",
    "总建筑面积（平方米）": "total_build_area",
    "总户数": "total_households",
    "总门牌数": "total_buildings",
    "物业企业名称": "property_company",
    "物业公司原资质等级": "property_qualification",
    "物业服务类型": "property_service_type",
    "收费模式": "fee_mode",
    "地上车位数": "parking_ground",
    "地下车位数": "parking_underground",
    "业主大会名称": "owners_committee_name",
    "第几届": "committee_term",
    "小区封闭与否": "is_closed",
    "商品房面积占比": "commercial_area_ratio",
    "归属片区": "district_area",
    "小区地址": "community_addr",
}


def log(msg=""):
    print(msg)


# ─────────────────────────── 主表 ───────────────────────────
def load_main(version: str) -> pd.DataFrame:
    """读纳统小区档案 → 旧库主表 21 列（含 build_year 从竣工日期取年份）。"""
    p = NATO_XLS[version]
    raw = pd.read_excel(p)
    n = len(raw)
    out = pd.DataFrame(index=raw.index)
    for src, dst in ARCHIVE_MAP.items():
        out[dst] = raw[src] if src in raw.columns else np.nan

    # 竣工日期 → build_year（只取年份；保留档案原始脏值形态，与旧库一致）
    yr = pd.to_datetime(raw["竣工日期"], errors="coerce").dt.year
    out["build_year"] = yr.astype(float)

    # 名称/街道去空白
    out["community_name"] = out["community_name"].astype(str).str.strip()
    out["street"] = out["street"].astype(str).str.replace("街道", "", regex=False).str.strip()
    for c in ["total_households", "total_buildings", "parking_ground",
              "parking_underground"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype("int64")
    out["total_build_area"] = pd.to_numeric(out["total_build_area"], errors="coerce")
    out["property_qualification"] = pd.to_numeric(out["property_qualification"], errors="coerce")
    out["committee_term"] = pd.to_numeric(out["committee_term"], errors="coerce")
    log(f"  主表：{p.split('/')[-1]} → {n} 行 × {len(ARCHIVE_MAP)+1} 列")
    return out


def nato_mapper(names, street_of=None):
    """小区名 → 纳统小区名 映射（统一走 nato_match，主名/别名/曾用名精确匹配）。

    所有关联函数的返回 Series 都以**纳统小区名**为索引；主流程再用
    `key_of = 主表名 → 纳统小区名` 把结果 reindex 回主表行。
    这样新旧档案的命名风格差异（全角/半角括号）不会造成错配。
    """
    names = sorted({str(x).strip() for x in names if str(x).strip() not in ("", "nan", "None")})
    mp = NM.build_map(names, version="new", streets=street_of)
    return mp, dict(zip(mp["hotline_name"], mp["nato_name"]))


# ─────────────────────────── 电梯 ───────────────────────────
def link_elevator(main: pd.DataFrame) -> dict:
    p = os.path.join(DEPT, "电梯基本信息.xlsx")
    e = pd.read_excel(p)
    st = main.set_index("community_name")["street"].to_dict()
    mp, m = nato_mapper(e["小区名称"].dropna().unique(), st)
    e["_nato"] = e["小区名称"].astype(str).str.strip().map(m)
    h = e[e["_nato"].notna()]
    n_all_comm = e["小区名称"].astype(str).str.strip().nunique()
    done = h["电梯加装状态"].astype(str).str.contains("完工", na=False)
    res = {
        "elevator_total": h.groupby("_nato").size(),
        "elevator_done": h[done].groupby("_nato").size(),
    }
    q = {"records": int(len(e)), "communities": int(n_all_comm),
         "matched": int(h["_nato"].nunique()),
         "match_rate": round(h["_nato"].nunique() / n_all_comm * 100, 1) if n_all_comm else 0.0}
    log(f"  电梯：{q['records']} 条 / {q['communities']} 小区 → 匹配 {q['matched']} 个（{q['match_rate']}%）")
    return {"elevator_total": res["elevator_total"], "elevator_done": res["elevator_done"], "quality": q}


# ─────────────────────────── 修缮 ───────────────────────────
def link_repair(main: pd.DataFrame) -> dict:
    p = os.path.join(DEPT, "修缮项目.xlsx")
    r = pd.read_excel(p)
    nm = r["小区名称"] if "小区名称" in r.columns else pd.Series(dtype=object)
    valid = nm.notna() & (nm.astype(str).str.strip() != "")
    h = r[valid].copy()
    st = main.set_index("community_name")["street"].to_dict()
    mp, m = nato_mapper(h["小区名称"].dropna().unique(), st)
    h["_nato"] = h["小区名称"].astype(str).str.strip().map(m)
    h = h[h["_nato"].notna()]
    g = h.groupby("_nato")
    n_all_comm = int(r.loc[valid, "小区名称"].astype(str).str.strip().nunique())
    res = {
        "repair_project_count": g.size(),
        "repair_total_invest": pd.to_numeric(h["总投资(万元)"], errors="coerce").groupby(h["_nato"]).sum(),
        "repair_total_area": pd.to_numeric(h["建筑面积(平方米)"], errors="coerce").groupby(h["_nato"]).sum(),
        "repair_years": g["年份"].apply(lambda s: ",".join(sorted({str(int(x)) for x in s if pd.notna(x)}))),
        "repair_types": g["修缮性质"].apply(
            lambda s: ",".join(sorted({str(x).strip() for x in s if pd.notna(x) and str(x).strip()}))),
    }
    q = {"records": int(len(r)), "communities": n_all_comm,
         "matched": int(h["_nato"].nunique()),
         "match_rate": round(h["_nato"].nunique() / n_all_comm * 100, 1) if n_all_comm else 0.0}
    log(f"  修缮：{q['records']} 条 / {q['communities']} 小区 → 匹配 {q['matched']} 个（{q['match_rate']}%）")
    res["quality"] = q
    return res


# ─────────────────────────── 底部抬升 ───────────────────────────
def link_bottom_lift(main: pd.DataFrame) -> dict:
    """底部抬升重点小区清单（表头占 3 行：标题 / 一级表头 / 二级表头）。"""
    p = os.path.join(DEPT, "底部抬升84个小区0403.xlsx")
    raw = pd.read_excel(p, header=None)
    body = raw.iloc[3:].copy()
    body = body[body[1].notna() & (body[1].astype(str).str.strip() != "")]
    body = body[~body[1].astype(str).str.strip().isin(["小区名", "序号"])]
    st = main.set_index("community_name")["street"].to_dict()
    mp, m = nato_mapper(body[1].astype(str).str.strip().unique(), st)
    body["_nato"] = body[1].astype(str).str.strip().map(m)
    hit = body[body["_nato"].notna()]
    # 问题类别：col5–col9 打「●」；矛盾类别：col12（1/2/3）
    cats = ["bl_cat_hotline", "bl_cat_low_fee", "bl_cat_fall_risk",
            "bl_cat_single_prop", "bl_cat_no_committee"]
    flags = {}
    for i, c in enumerate(cats):
        col = 5 + i
        s = hit[col].astype(str).str.contains("●", na=False)
        flags[c] = hit[s].groupby("_nato").size()
    res = {
        "is_bottom_lift": set(hit["_nato"]),
        "bottom_lift_type": pd.to_numeric(hit[12], errors="coerce").groupby(hit["_nato"]).first(),
        "cats": flags,
        "quality": {"records": int(len(body)), "communities": int(body[1].astype(str).str.strip().nunique()),
                    "matched": int(hit["_nato"].nunique()),
                    "match_rate": round(hit["_nato"].nunique() / body[1].astype(str).str.strip().nunique() * 100, 1)},
    }
    log(f"  底部抬升：{res['quality']['records']} 行 / {res['quality']['communities']} 小区 → "
        f"匹配 {res['quality']['matched']} 个（{res['quality']['match_rate']}%）")
    return res


# ─────────────────────────── 旧库迁移字段 ───────────────────────────
def migrate_from_old() -> pd.DataFrame:
    """迁移失信计分 / hotline_2025（原始数据源已不在项目目录，只能沿用旧库值）。

    旧库行按 nato_match 归并到 2026 更新版纳统小区；被合并的组（尚海湾二期 + 尚海湾豪庭）
    对计数类字段求和。返回以**纳统小区名**为索引的 DataFrame。
    """
    old = pd.read_pickle(PKL)
    st = old.groupby("community_name")["street"].agg(
        lambda s: s.mode().iloc[0] if len(s.mode()) else "").to_dict()
    mp_old = NM.build_map(sorted(st), version="new", streets=st)
    m_old = dict(zip(mp_old["hotline_name"], mp_old["nato_name"]))
    old = old.copy()
    old["_nato"] = old["community_name"].map(m_old)
    hit = old[old["_nato"].notna()]
    g = hit.groupby("_nato")
    out = pd.DataFrame({
        "dishonest_count": g["dishonest_count"].sum(),
        "dishonest_total_score": g["dishonest_total_score"].sum(),
        "hotline_2025": g["hotline_2025"].sum(),
    })
    log(f"  迁移：失信 {int((out['dishonest_count']>0).sum())} 个小区 / hotline_2025 "
        f"{int((out['hotline_2025']>0).sum())} 个小区（1:1 承继旧库，无源可重跑）")
    return out


# ─────────────────────────── 热线投诉 ───────────────────────────
def link_hotline(main: pd.DataFrame) -> dict:
    """按纳统小区聚合统计投诉量。2026 取 1-8 月（与全站口径一致）。"""
    o_all = pd.read_pickle(MAIN)
    n_all = int(len(o_all))                  # 热线工单全量（2024.1–2026.8）
    o = o_all[o_all["community_name"].notna()].copy()
    o["community_name"] = o["community_name"].astype(str).str.strip()
    o = o[~o["community_name"].isin(["", "无", "nan", "None"])]
    n_raw = int(len(o))                      # 有名可关联的工单数
    o = NM.aggregate_key(o, col="community_name")
    o = o[o["nato_community"].astype(str).str.strip() != ""]
    n_nato = int(len(o))                     # 关联后：纳统小区内的工单数
    y = pd.to_numeric(o["year"], errors="coerce")
    mo = pd.to_numeric(o["month"], errors="coerce")
    n24 = o[y == 2024].groupby("nato_community").size()
    n25 = o[y == 2025].groupby("nato_community").size()
    n26 = o[(y == 2026) & (mo <= 8)].groupby("nato_community").size()
    idx = pd.Index(sorted(set(n24.index) | set(n25.index) | set(n26.index)), name="nato_name")
    d = pd.DataFrame(index=idx)
    d["complaint_2024"] = n24.reindex(idx).fillna(0).astype("int64")
    d["complaint_2025"] = n25.reindex(idx).fillna(0).astype("int64")
    d["complaint_2026"] = n26.reindex(idx).fillna(0).astype("int64")
    d["complaint_total"] = d[["complaint_2024", "complaint_2025", "complaint_2026"]].sum(axis=1)
    d["complaint_yoy_2025"] = np.where(
        d["complaint_2024"] > 0,
        ((d["complaint_2025"] - d["complaint_2024"]) / d["complaint_2024"] * 100).round(1),
        0.0)
    cov = int((d["complaint_total"] > 0).sum())
    q = {"records": n_all, "records_with_community": n_raw, "records_nato": n_nato,
         "matched_by_name": cov, "coverage": round(cov / len(main) * 100, 1)}
    log(f"  热线：全量 {n_all:,} 件（2024.1–2026.8，其中有名可关联 {n_raw:,} 件）→ "
        f"纳统内 {n_nato:,} 件；有投诉记录的小区 {cov} 个（覆盖 {q['coverage']}%）；"
        f"2024={int(d['complaint_2024'].sum()):,} / 2025={int(d['complaint_2025'].sum()):,} / "
        f"2026(1-8月)={int(d['complaint_2026'].sum()):,}")
    return d, q


# ─────────────────────────── 主流程 ───────────────────────────
def build(version: str = "new", dry_run: bool = False) -> pd.DataFrame:
    log(f"重建小区级关联库（主表＝{'2026 更新版' if version=='new' else '旧版'}纳统小区）")
    main = load_main(version)

    ele = link_elevator(main)
    rep = link_repair(main)
    bl = link_bottom_lift(main)
    mig = migrate_from_old()
    hot, hot_q = link_hotline(main)

    df = main.copy().reset_index(drop=True)
    # 主表名 → 纳统小区名（关联键）；所有关联结果按此键 reindex 回主表行，
    # 避免新旧档案的全角/半角命名差异造成错配
    st_of_main = main.set_index("community_name")["street"].to_dict()
    _kmp, kmap = nato_mapper(main["community_name"], st_of_main)
    keys = main["community_name"].map(kmap).tolist()
    n_unkey = sum(1 for k in keys if not isinstance(k, str) or k == "")
    log(f"  键对齐：{len(keys) - n_unkey}/{len(keys)} 行映射到 2026 更新版纳统小区"
        + (f"（{n_unkey} 行无对应）" if n_unkey else ""))
    isin_key = lambda s: pd.Series(keys).isin(s).values  # noqa: E731

    def put(col, series):
        df[col] = series.reindex(keys).values if series is not None else np.nan

    put("elevator_total", ele["elevator_total"])
    put("elevator_done", ele["elevator_done"])
    df["elevator_building"] = 0
    put("repair_project_count", rep["repair_project_count"])
    put("repair_total_invest", rep["repair_total_invest"])
    put("repair_total_area", rep["repair_total_area"])
    put("repair_years", rep["repair_years"])
    put("repair_types", rep["repair_types"])
    for c in ["dishonest_count", "dishonest_total_score", "hotline_2025"]:
        put(c, mig[c])
    _is_bl = isin_key(bl["is_bottom_lift"])
    df["is_bottom_lift"] = _is_bl
    put("bottom_lift_type", bl["bottom_lift_type"])
    for c, s in bl["cats"].items():
        # 与旧库一致：仅底部抬升小区有取值，其余留空
        df[c] = np.where(_is_bl, isin_key(s.index), np.nan)
    for c in ["complaint_total", "complaint_2024", "complaint_2025", "complaint_2026",
              "complaint_yoy_2025"]:
        put(c, hot[c])
    df["parking_total"] = df["parking_ground"] + df["parking_underground"]

    # 数值列空值处理（与旧库一致：计数类填 0，比率类保留 NaN）
    # ⚠️ reindex 对齐后未命中的行会是 NaN，必须显式回填，否则下游 groupby/corr 会丢样本
    for c in ["elevator_total", "elevator_done", "elevator_building", "repair_project_count",
              "dishonest_count", "hotline_2025", "complaint_total", "complaint_2024",
              "complaint_2025", "complaint_2026"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("int64")
    df["dishonest_total_score"] = pd.to_numeric(df["dishonest_total_score"], errors="coerce").fillna(0.0)
    df["complaint_yoy_2025"] = pd.to_numeric(df["complaint_yoy_2025"], errors="coerce").fillna(0.0)
    df["is_bottom_lift"] = df["is_bottom_lift"].astype(bool)

    df = df.reset_index(drop=True)[COLS]

    # ── 对照 ──
    old = pd.read_pickle(PKL)
    log("")
    log(f"  旧库 {len(old)} 行 → 新库 {len(df)} 行")
    log(f"  户数合计：{int(old['total_households'].sum()):,} → {int(df['total_households'].sum()):,}")
    log(f"  有户数行数：{int((old['total_households']>0).sum())} → {int((df['total_households']>0).sum())}")
    log(f"  有投诉记录小区：{int((old['complaint_total']>0).sum())} → {int((df['complaint_total']>0).sum())}")
    log(f"  底部抬升小区：{int(old['is_bottom_lift'].sum())} → {int(df['is_bottom_lift'].sum())}")
    log(f"  有电梯小区：{int((old['elevator_total']>0).sum())} → {int((df['elevator_total']>0).sum())}")
    log(f"  有修缮小区：{int((old['repair_project_count']>0).sum())} → {int((df['repair_project_count']>0).sum())}")

    if dry_run:
        log("\n[dry-run] 未写任何文件")
        return df

    # ── 备份旧库 + 写盘 ──
    bak = os.path.join(DATA, "community_linked_data_20260903_994.pkl")
    if not os.path.exists(bak):
        shutil.copy2(PKL, bak)
        log(f"\n  旧库已备份 → {os.path.relpath(bak, ROOT)}")
    df.to_pickle(PKL)
    df.to_csv(CSV, index=False, encoding="utf-8-sig")

    q = {
        "total_communities": int(len(df)),
        "total_streets": int(df["street"].nunique()),
        "nato_source": "《纳统小区 (2026 更新版).xls》",
        "data_sources": {
            "纳统小区(主表)": {"records": int(len(df)), "match": "100%", "level": "小区级"},
            "电梯基本信息": {**ele["quality"], "level": "小区级"},
            "修缮项目": {**rep["quality"], "level": "小区级"},
            "底部抬升小区": {**bl["quality"], "level": "小区级"},
            "失信计分": {"records": 37, "communities": 18,
                         "matched": int((df["dishonest_count"] > 0).sum()), "match_rate": "100.0%",
                         "note": "原始数据源不在项目目录，沿用旧库迁移值"},
            "热线投诉": {"records": hot_q["records"],
                         "records_with_community": hot_q["records_with_community"],
                         "records_nato": hot_q["records_nato"],
                         "matched_by_name": int((df["complaint_total"] > 0).sum()),
                         "coverage": round((df["complaint_total"] > 0).sum() / len(df) * 100, 1)},
            "征收": {"records": 105, "level": "街道级", "streets": 12},
            "拆房信息": {"records": 51, "level": "街道级", "streets": 11},
            "测绘基本信息": {"records": 115, "level": "街道级", "streets": 12},
        },
        "community_level_fields": int(len(df.columns)),
        "street_level_fields": 24,
        "scope": "统计单元＝纳统小区（《纳统小区 (2026 更新版)》名单，993 个）；"
                 "投诉按热线数据表口径统计，2026 年取 1-8 月",
    }
    import json
    with open(QLTY, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
    log(f"  已写入 {os.path.relpath(PKL, ROOT)} / .csv / data_link_quality.json")
    return df


def main():
    ap = argparse.ArgumentParser(description="以 2026 更新版纳统小区为主表重建关联库")
    ap.add_argument("--version", choices=["new", "old"], default="new")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    build(version=a.version, dry_run=a.dry_run)


if __name__ == "__main__":
    main()
