#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recalc_rootcause.py — 复算《物业投诉根因分析报告》的分组统计

背景：关联库重建为《纳统小区 (2026 更新版)》993 口径后，报告中直接依赖
「关联字段」（total_households / elevator_total / parking_total / repair_project_count /
is_bottom_lift）的分组统计需要同步复算。

样本口径（与报告一致）：**纳统小区中有投诉记录的**（complaint_total > 0）。
列口径：
  · 平均投诉量   = mean(complaint_total)            （三年合计的均值）
  · 每千户投诉量 = sum(complaint_total) / sum(total_households) × 1000
  · 2025同比     = (sum(complaint_2025) − sum(complaint_2024)) / sum(complaint_2024)

用法：
    python3 scripts/recalc_rootcause.py --lib old     # 用旧库复现，校验口径
    python3 scripts/recalc_rootcause.py               # 用新库（993）出正式值
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEW = os.path.join(ROOT, "data", "community_linked_data.pkl")
OLD = os.path.join(ROOT, "data", "community_linked_data_20260903_994.pkl")


def p1k(g):
    hh = g["total_households"].sum()
    return g["complaint_total"].sum() / hh * 1000 if hh else float("nan")


def yoy(g):
    a, b = g["complaint_2024"].sum(), g["complaint_2025"].sum()
    return (b - a) / a * 100 if a else float("nan")


def report(df, title):
    print(f"\n{'='*72}\n{title}   样本 n={len(df)}\n{'='*72}")

    print("\n【2.1 小区规模】")
    bins = [0, 200, 500, 1000, 10 ** 9]
    lab = ["小型（<200户）", "中型（200-500户）", "大型（500-1000户）", "超大型（>1000户）"]
    for k, v in df.groupby(pd.cut(df["total_households"], bins=bins, labels=lab, right=False),
                           observed=True):
        print(f"  {k:<18} 小区数={len(v):>4}  平均投诉={v['complaint_total'].mean():>7.1f}件  "
              f"每千户={p1k(v):>7.1f}件")

    print("\n【4.1 电梯状况】")
    for name, m in [("无电梯", df["elevator_total"] == 0), ("有电梯", df["elevator_total"] > 0)]:
        v = df[m]
        print(f"  {name:<8} 小区数={len(v):>4}  平均投诉={v['complaint_total'].mean():>7.1f}件  "
              f"每千户={p1k(v):>7.1f}件  2025同比={yoy(v):>+7.1f}%")

    print("\n【4.1 电梯台数分段】")
    eb = [(-1, 0, "无电梯"), (0, 5, "1-5台"), (5, 10, "6-10台"), (10, 20, "11-20台"), (20, 10 ** 9, "20台以上")]
    for lo, hi, name in eb:
        v = df[(df["elevator_total"] > lo) & (df["elevator_total"] <= hi)]
        if not len(v):
            continue
        print(f"  {name:<10} 小区数={len(v):>4}  平均投诉={v['complaint_total'].mean():>7.1f}件  "
              f"每千户={p1k(v):>7.1f}件  2025同比={yoy(v):>+7.1f}%")

    print("\n【4.2 车位配比】")
    r = df[df["total_households"] > 0].copy()
    r["ratio"] = r["parking_total"] / r["total_households"]
    pr = [(-1, 0.3, "严重不足（<0.3）"), (0.3, 0.5, "不足（0.3-0.5）"),
          (0.5, 0.8, "基本平衡（0.5-0.8）"), (0.8, 10 ** 9, "充足（>0.8）")]
    for lo, hi, name in pr:
        v = r[(r["ratio"] > lo) & (r["ratio"] <= hi)]
        if not len(v):
            continue
        print(f"  {name:<18} 小区数={len(v):>4}  平均投诉={v['complaint_total'].mean():>7.1f}件  "
              f"每千户={p1k(v):>7.1f}件  2025同比={yoy(v):>+7.1f}%")

    print("\n【4.3 修缮状况】")
    for name, m in [("无修缮项目", df["repair_project_count"] == 0),
                    ("有修缮项目", df["repair_project_count"] > 0)]:
        v = df[m]
        print(f"  {name:<10} 小区数={len(v):>4}  平均投诉={v['complaint_total'].mean():>7.1f}件  "
              f"每千户={p1k(v):>7.1f}件  2024平均={v['complaint_2024'].mean():>6.1f}件  "
              f"2025平均={v['complaint_2025'].mean():>6.1f}件  2025同比={yoy(v):>+7.1f}%")

    print("\n【5.2 底部抬升】")
    for name, m in [("普通小区", ~df["is_bottom_lift"]), ("底部抬升小区", df["is_bottom_lift"])]:
        v = df[m]
        print(f"  {name:<12} 小区数={len(v):>4}  平均投诉={v['complaint_total'].mean():>7.1f}件  "
              f"每千户={p1k(v):>7.1f}件  2025同比={yoy(v):>+7.1f}%  "
              f"平均户数={v['total_households'].mean():>6.0f}户")

    print("\n【相关系数（户数 vs 投诉总量）】")
    c = df[["total_households", "complaint_total"]].dropna()
    print(f"  r = {c['total_households'].corr(c['complaint_total']):.3f}   (n={len(c)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", choices=["new", "old"], default="new")
    ap.add_argument("--all", action="store_true", help="不筛选「有投诉记录」，用全部纳统小区")
    a = ap.parse_args()
    df = pd.read_pickle(NEW if a.lib == "new" else OLD)
    if not a.all:
        df = df[df["complaint_total"] > 0]
    tag = "旧库 994（复现校验）" if a.lib == "old" else "新库 993（2026 更新版，含 2026年1-8月）"
    report(df, tag)


if __name__ == "__main__":
    main()
