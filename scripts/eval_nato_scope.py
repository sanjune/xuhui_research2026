# -*- coding: utf-8 -*-
"""量化「风险评估报告按 2026 更新版纳统小区统计」的影响（dry-run，不写任何产物）。

对照三组口径：
  A 现状     : 按热线小区名分组，不过滤名单，三年合计≥10 件          → 期望 799
  B 记录级过滤: 保留能匹配到新版纳统名单的记录（不聚合）              → ?
  C 按纳统聚合: 别名/曾用名归并到纳统小区后统计，仅名单内              → ?

同时输出：
  · 被剔除的小区清单（热线名 / 工单量 / 原风险等级）
  · 「疑似同一小区但名称不完全一致」候选（供人工确认是否纳入模糊匹配）
"""
import json
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import nato_match as NM  # noqa: E402

DATA_DIR = os.path.join(ROOT, "热线数据")
EXCLUDE = ["剔除三大类", "剔除-商办楼宇", "剔除-非物业管理区域", "剔除-无效工单",
           "无", "房屋交易纠纷", "其他"]
MIN_TOTAL = 10


def load_hotline():
    """按 risk_scoring.py 的原始口径读取热线数据表（市局14类三表）。"""
    files = ["2024年市局14类.xlsx",
             "2025 年全年、2026年 1-6 月市局14类.xlsx",
             "2026 年7月市局14类.xlsx"]
    frames = []
    for f in files:
        p = os.path.join(DATA_DIR, f)
        df = pd.read_excel(p, sheet_name="Sheet1")
        ren = {}
        for c in df.columns:
            if "工单编号" in c: ren[c] = "order_id"
            elif "内容描述" in c: ren[c] = "content"
            elif "小区名称" in c: ren[c] = "community_name"
            elif c == "物业公司": ren[c] = "property_company"
            elif c == "街道": ren[c] = "street"
            elif c == "十四类": ren[c] = "category_14"
            elif c == "年": ren[c] = "year"
            elif c == "月份": ren[c] = "month"
        df = df.rename(columns=ren)
        if "year" not in df.columns:
            df["year"] = 2026
        if "month" not in df.columns:
            for c in df.columns:
                if "受理时间" in c:
                    df["month"] = pd.to_datetime(df[c], errors="coerce").dt.month
                    break
        frames.append(df[["year", "month", "community_name", "street",
                          "property_company", "category_14"]])
        print(f"  读入 {f}: {len(df):,}")
    df = pd.concat(frames, ignore_index=True)
    df["street"] = df["street"].apply(
        lambda x: str(x).replace("街道", "").replace("镇", "").strip() if pd.notna(x) else "未知")
    df["category_14"] = df["category_14"].replace(
        {"群租问题": "群租管理", "业委会": "业主大会/业委会", "服务态度": "物业服务态度"})
    n0 = len(df)
    df = df[~df["category_14"].isin(EXCLUDE)]
    df = df[df["community_name"].notna()
            & (df["community_name"].astype(str).str.strip() != "")
            & (df["community_name"].astype(str).str.strip() != "无")]
    print(f"  剔除非物业类别后 {n0:,} → {len(df):,}")
    return df


def group_by(df, key):
    """按 key 列分组，返回 小区名 → 工单数 的 Series（仅 ≥MIN_TOTAL）。"""
    g = df.groupby(key).size()
    return g[g >= MIN_TOTAL]


def main():
    print("=" * 70)
    print("量化：风险评估报告按《纳统小区（2026 更新版）》统计的影响")
    print("=" * 70)

    df = load_hotline()
    print(f"\n有效记录 {len(df):,}｜热线小区 {df['community_name'].nunique():,} 个")

    st_map = df.groupby("community_name")["street"].agg(
        lambda s: s.mode().iloc[0] if len(s.mode()) else "").to_dict()
    mp = NM.build_map(sorted(st_map), streets=st_map)

    # ── A 现状（按热线名，不过滤）
    A = group_by(df, "community_name")
    # ── B 记录级过滤（保留名单内记录，仍按热线名分组）
    ok_names = set(mp.loc[mp["matched"], "hotline_name"])
    dfB = df[df["community_name"].astype(str).str.strip().isin(ok_names)]
    B = group_by(dfB, "community_name")
    # ── C 按纳统小区聚合（仅名单内）
    dfC = NM.aggregate_key(dfB, col="community_name", mp=mp)
    C = group_by(dfC, "nato_community")

    print("\n" + "=" * 70)
    print("【参评基数（三年合计 ≥10 件）】")
    print("=" * 70)
    print(f"  A 现状（按热线名、不限名单）        : {len(A):>4} 个 ｜ 工单 {int(A.sum()):>7,}")
    print(f"  B 记录级过滤（仅名单内、仍按热线名）: {len(B):>4} 个 ｜ 工单 {int(B.sum()):>7,}")
    print(f"  C 按纳统小区聚合（仅名单内）        : {len(C):>4} 个 ｜ 工单 {int(C.sum()):>7,}")

    dropped = sorted(set(A.index) - set(B.index))
    print(f"\n  被剔除小区 {len(dropped)} 个｜工单 {int(A.reindex(dropped).sum()):,} 件"
          f"（占全部参评工单 {A.reindex(dropped).sum()/A.sum()*100:.1f}%）")

    # 与现有 risk_scores.json 对照
    rs = json.load(open(os.path.join(ROOT, "scripts", "risk_scores.json")))
    cur = set(c["community"] for c in rs["all_communities"])
    print(f"\n  risk_scores.json 现有参评 {len(cur)} 个（模型数据仅到 2026-07，故与 A 略有差异）")
    print(f"    其中不在新版纳统名单: {len(cur - ok_names)} 个")

    print("\n" + "=" * 70)
    print("【方案 C 相对方案 B 的变化（聚合带来的工单归并）】")
    print("=" * 70)
    merged_names = mp[(mp["matched"]) & (mp["hotline_name"] != mp["nato_name"])]
    print(f"  别名/曾用名归并: {len(merged_names)} 个热线名 → {merged_names['nato_name'].nunique()} 个纳统小区")
    up = sorted(set(C.index) - set(B.index))
    print(f"  因归并而新跨过 ≥10 门槛的小区: {len(up)} 个")
    if up:
        for x in up[:15]:
            print(f"     + {x} ({int(C[x])} 件)")

    # ── 疑似同一小区（名称近似但未精确匹配）
    print("\n" + "=" * 70)
    print("【待人工确认：名称近似但未精确匹配（前 30，按工单量）】")
    print("=" * 70)
    nato = NM.load_nato()
    allkeys = set()
    for ks in nato["keys"]:
        allkeys |= ks
    un = mp[~mp["matched"]].copy()
    un["cnt"] = un["hotline_name"].map(lambda x: int(A.get(x, 0)))
    un = un.sort_values("cnt", ascending=False)
    shown = 0
    for _, r in un.iterrows():
        k = NM.norm(r["hotline_name"])
        if len(k) < 3:
            continue
        cands = [x for x in allkeys if x != k and (k in x or x in k)]
        if cands and r["cnt"] > 0:
            print(f"  「{r['hotline_name']}」{r['cnt']:>4} 件 → 疑似: {sorted(cands)[:4]}")
            shown += 1
            if shown >= 30:
                break

    json.dump({
        "A_current": {k: int(v) for k, v in A.items()},
        "B_filtered": {k: int(v) for k, v in B.items()},
        "C_aggregated": {k: int(v) for k, v in C.items()},
        "dropped": {k: int(A[k]) for k in dropped},
    }, open("/tmp/nato_impact.json", "w"), ensure_ascii=False, indent=2)
    print("\n明细已存 /tmp/nato_impact.json")


if __name__ == "__main__":
    main()
