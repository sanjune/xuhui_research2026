# -*- coding: utf-8 -*-
"""
当月复核工单 · 重复工单复核（外部下载表）
==========================================

对「12345 当月复核工单下载」这类外部 xlsx 套用项目既有的四重去重策略
（规则实现复用 scripts/dedup_monthly.py，保证口径与历史月度一致），
输出重复工单判定与清单。

字段映射（外部表 → 项目口径）：
    12345工单编号 → order_id      12345受理时间 → accept_time
    12345内容描述 → content        小区名称     → community_name
    十四类        → category_14    街道         → street
    物业公司      → property_company

用法：
    PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 \
        scripts/dedup_review_external.py --xlsx "/path/to/表.xlsx" [--strip-quote]
"""
import argparse
import json
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dedup_monthly as D  # noqa: E402  四重策略的规则实现（唯一口径来源）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COLMAP = {
    "12345工单编号": "order_id",
    "12345受理时间": "accept_time",
    "12345内容描述": "content",
    "小区名称": "community_name",
    "十四类": "category_14",
    "街道": "street",
    "物业公司": "property_company",
}

# 系统追加的引用块：「【最近派发的工单编号：X，工单内容：<原文全文>】」
# 写法有十余种变体（最近派发/最近办结/最近办结地/最近发的/最近派发工单编号/
# 最近办结工单号/最近办结工单：…），正则在 dedup_monthly.py 统一定义后此处引用，
# 避免两处各写一份导致漂移（S2 的系统标记匹配也依赖同一正则）。
QUOTED_BLOCK_RE = D.QUOTED_BLOCK_RE

# 正文里引用的工单编号（统一按「工单(编)(号) + 14 位数字」抓取）
# 2026-09-28：定义已迁到唯一判定口径源 `dedup_monthly.ORDER_REF_RE`，此处仅引用。
# 修正要点（2026-09-24）：
#   1) 「编」「号」都改为可选 —— 「关联工单2026…」「最近办结工单：2026…」原写法抓不到；
#   2) 两侧加数字边界，避免把 18 位身份证号（如 3101081965******36）的前 14 位误判为工单编号。
ORDER_REF_RE = D.ORDER_REF_RE


def load_external(path: str, sheet: str = "sheet1") -> pd.DataFrame:
    d = pd.read_excel(path, sheet_name=sheet)
    d = d.rename(columns=COLMAP)
    missing = [c for c in COLMAP.values() if c not in d.columns]
    if missing:
        raise SystemExit(f"缺少必要字段: {missing}")
    d["content"] = d["content"].fillna("").astype(str).str.strip()
    d["community_name"] = d["community_name"].fillna("").astype(str).str.strip()
    d["category_14"] = d["category_14"].fillna("").astype(str).str.strip()
    # 受理时间：可能是 datetime，也可能是 Excel 序列值
    t = pd.to_datetime(d["accept_time"], errors="coerce")
    if t.isna().all():
        t = pd.to_datetime(
            pd.to_numeric(d["accept_time"], errors="coerce"),
            unit="D", origin="1899-12-30", errors="coerce")
    d["t"] = t
    return d


def strip_quoted(text: str) -> str:
    """剥离系统追加的引用块（注意函数名勿与 analyze_external 的形参同名）。"""
    return QUOTED_BLOCK_RE.sub("", text or "").strip()


def analyze_external(path: str, sheet: str = "sheet1", strip_quote: bool = False) -> dict:
    d = load_external(path, sheet)
    if strip_quote:
        d["content"] = d["content"].map(strip_quoted)

    total = len(d)
    s1, s1g = D.strategy1_exact(d)
    s2 = D.strategy2_keyword(d)
    s3, s3_groups, freq, s3_f4 = D.strategy3_frequency(d)
    s4, s4_pairs, s4_comms, order_sim = D.strategy4_similarity(d)

    union = s1 | s2 | s3 | s4
    high = s1 | s2 | s3_f4
    mid = union - high

    return {
        "file": os.path.basename(path),
        "strip_quote": strip_quote,
        "total": total,
        "total_dup": len(union),
        "dup_rate": round(len(union) / total * 100, 1) if total else 0.0,
        "high": len(high), "mid": len(mid),
        "s1": len(s1), "s1_groups": s1g,
        "s2": len(s2),
        "s3": len(s3), "s3_groups": len(s3_groups),
        "s4_orders": len(s4), "s4_pairs": len(s4_pairs), "s4_comms": len(s4_comms),
        "_d": d, "_sets": {"s1": s1, "s2": s2, "s3": s3, "s4": s4,
                            "union": union, "high": high, "mid": mid},
        "_order_sim": order_sim, "_freq": freq, "_s3_groups": s3_groups,
        "_s4_pairs": s4_pairs,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--sheet", default="sheet1")
    ap.add_argument("--out", default=None, help="清单输出 xlsx（追加工作表）")
    args = ap.parse_args()

    base = analyze_external(args.xlsx, args.sheet, strip_quote=False)
    stripped = analyze_external(args.xlsx, args.sheet, strip_quote=True)

    print("=" * 78)
    print(f"文件 {base['file']}  共 {base['total']} 条")
    print("-" * 78)
    print(f"{'口径':<22}{'重复数':>8}{'重复率':>9}{'高':>7}{'中':>6}"
          f"{'S1':>6}{'S2':>6}{'S3':>6}{'S4条':>7}{'S4对':>7}")
    for r, label in [(base, "原样（历史规则）"), (stripped, "剥离引用块后")]:
        print(f"{label:<22}{r['total_dup']:>8}{r['dup_rate']:>8}%{r['high']:>7}{r['mid']:>6}"
              f"{r['s1']:>6}{r['s2']:>6}{r['s3']:>6}{r['s4_orders']:>7}{r['s4_pairs']:>7}")
    print("-" * 78)
    print(f"原样  S1 {base['s1_groups']} 组 / S3 {base['s3_groups']} 组 / "
          f"S4 涉及 {base['s4_comms']} 小区")
    print(f"剥离  S1 {stripped['s1_groups']} 组 / S3 {stripped['s3_groups']} 组 / "
          f"S4 涉及 {stripped['s4_comms']} 小区")

    # 引用块占比（复用 base 已加载的数据，避免重复读盘）
    d0 = base["_d"]
    nq = int(d0["content"].str.contains(QUOTED_BLOCK_RE, na=False).sum())
    print(f"\n含「最近派发/办结的工单编号」引用块: {nq}/{len(d0)} "
          f"({nq/len(d0)*100:.1f}%)")

    # 导出 JSON（供后续清单生成）
    out_json = os.path.join(ROOT, "scripts", "dedup_review_external.json")
    payload = {k: v for k, v in base.items() if not k.startswith("_")}
    payload["with_strip"] = {k: v for k, v in stripped.items() if not k.startswith("_")}
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n✔ 指标已写入 {out_json}")


if __name__ == "__main__":
    main()
