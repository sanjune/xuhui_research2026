# -*- coding: utf-8 -*-
"""导出「名称近似但未精确匹配」的纳统候选清单（供项目组人工确认）
=================================================================

背景：项目组 2026-09-28 决策 —— 风险评估报告按《纳统小区 (2026 更新版)》统计，
不在名单中的小区不做统计。匹配口径沿用「主名/别名 精确匹配」。

但热线工单里有一批小区名与纳统档案**名称近似而不完全相等**（如
「丁香园」vs「丁香园小区」、「长桥三村西区」vs「长桥三村西块」），
严格匹配认不出，被当作「名单外」剔除。本脚本把这批候选单独导出，
**不自动纳入统计**，由项目组逐条确认后再决定是否追加映射。

产出：项目根目录《待确认纳统匹配候选清单.xlsx》（3 张表）
  · 候选清单   —— 需要人工判断的（名称近似）
  · 其余未匹配 —— 名称差异较大，默认不纳入
  · 统计口径    —— 本次评估的口径说明
"""
import os
import sys
from difflib import SequenceMatcher

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import nato_match as NM  # noqa: E402

OUT_XLSX = os.path.join(ROOT, "待确认纳统匹配候选清单.xlsx")

# 明显与物业小区无关、无需确认的关键词（商业体/公寓/在建等）
NOISE = ("建设中", "在建", "服务公寓", "公寓式", "酒店", "商场", "广场", "大厦", "工地",
         "地块", "征收", "拆", "待建", "规划")


def candidates(name: str, keys: list, topn: int = 3):
    """返回 [(候选纳统名, 相似度, 关系, 置信档), ...]

    分档规则（宁可漏、不可错 —— 误判会把不同小区的工单并到一起）：
      · 高：子串关系且长度差 ≤4 字（如「丁香园」⊂「丁香园小区」、「永嘉大楼」⊂「永嘉大楼小区」）
      · 中：用字高度相近（相似度 ≥0.80）且首字相同
      · 其余不列
    """
    k = NM.norm(name)
    if len(k) < 3:
        return []
    out = []
    for key, disp in keys:
        if key == k:
            continue
        ratio = SequenceMatcher(None, k, key).ratio()
        grade, rel = "", ""
        if ((k in key or key in k) and abs(len(k) - len(key)) <= 4
                and min(len(k), len(key)) >= 3):      # 长度下限：避免「三村」这类通用短别名误配
            grade = "高"
            rel = (f"热线名是档案名的子串（档案多「{key[key.find(k)+len(k):]}」）" if k in key
                   else f"档案名是热线名的子串（热线多「{k[k.find(key)+len(key):]}」）")
        elif ratio >= 0.80 and k[:1] == key[:1]:
            grade = "中"
            rel = f"用字高度相近（相似度 {ratio:.2f}）"
        if grade:
            out.append((disp, round(ratio, 3), rel, grade))
    out.sort(key=lambda x: (x[3] != "高", -x[1]))
    return out[:topn]


def main():
    print("=" * 70)
    print("导出待确认纳统匹配候选清单")
    print("=" * 70)

    nato = NM.load_nato()
    # 规范化键 → 展示名（取档案主名）
    key_disp = {}
    for _, r in nato.iterrows():
        for k in r["keys"]:
            key_disp.setdefault(k, r["nato_name"])
    keys = list(key_disp.items())

    p = pd.read_pickle(os.path.join(ROOT, "data", "merged_cleaned.pkl"))
    p["cm"] = p["community_name"].fillna("").astype(str).str.strip()
    p = p[~p["cm"].isin(["", "无", "nan", "None"])].copy()
    p["at"] = pd.to_datetime(p["accept_time"], errors="coerce")

    mp = NM.build_map(sorted(p["cm"].unique()))
    outside = mp.loc[~mp["matched"], "hotline_name"].tolist()
    print(f"热线小区 {len(mp)} 个｜未匹配 {len(outside)} 个")

    rows = []
    for nm in outside:
        g = p[p["cm"] == nm]
        cands = candidates(nm, keys)
        rows.append({
            "热线小区名称": nm,
            "工单数": len(g),
            "2024": int((g["year"] == 2024).sum()),
            "2025": int((g["year"] == 2025).sum()),
            "2026(1-8月)": int(((g["year"] == 2026) & (g["month"] <= 8)).sum()),
            "是否疑似同一小区": (cands[0][3] + "置信" if cands else ""),
            "候选纳统小区1": cands[0][0] if len(cands) > 0 else "",
            "相似度1": cands[0][1] if len(cands) > 0 else "",
            "关系1": cands[0][2] if len(cands) > 0 else "",
            "候选纳统小区2": cands[1][0] if len(cands) > 1 else "",
            "候选纳统小区3": cands[2][0] if len(cands) > 2 else "",
            "人工结论": "",
            "确认人": "",
            "确认日期": "",
        })
    df = pd.DataFrame(rows).sort_values("工单数", ascending=False)

    cand = df[df["是否疑似同一小区"] != ""].copy()
    rest = df[df["是否疑似同一小区"] == ""].copy()
    print(f"  疑似同一小区（需人工确认）: {len(cand)} 个｜工单 {int(cand['工单数'].sum()):,}"
          f"（高置信 {int((cand['是否疑似同一小区']=='高置信').sum())} 个）")
    print(f"  其余未匹配（差异大）      : {len(rest)} 个｜工单 {int(rest['工单数'].sum()):,}")

    note = pd.DataFrame([
        ["统计范围", "仅《纳统小区 (2026 更新版).xls》名单内小区"],
        ["匹配口径", "主名 / 别名 精确匹配（规范化：去空白、全角转半角）"],
        ["本次是否纳入", "否 —— 全部候选保持「名单外」，不参与风险评估统计"],
        ["确认方式", "在「人工结论」列填「纳入/不纳入/改名映射为」后交回，脚本按结论补挂匹配键"],
        ["生成脚本", "scripts/export_nato_candidates.py"],
        ["生成时间", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")],
    ], columns=["项目", "说明"])

    from openpyxl.styles import Font

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as w:
        cand.to_excel(w, sheet_name="候选清单", index=False)
        rest.to_excel(w, sheet_name="其余未匹配", index=False)
        note.to_excel(w, sheet_name="统计口径", index=False)
        for sn in ("候选清单", "其余未匹配"):
            ws = w.sheets[sn]
            for cell in ws[1]:
                cell.font = Font(bold=True)
            ws.freeze_panes = "A2"
            ws.column_dimensions["A"].width = 30
            ws.column_dimensions["B"].width = 9
            ws.column_dimensions["F"].width = 14
            for letter in ("G", "H", "I", "J", "K"):
                ws.column_dimensions[letter].width = 22
            ws.column_dimensions["L"].width = 18
            for col in ("M", "N"):
                ws.column_dimensions[col].width = 12
    print(f"\n已导出: {OUT_XLSX}")
    print("\n需人工确认的重点（Top12，按工单量）:")
    for _, r in cand.head(12).iterrows():
        print(f"  {r['热线小区名称']:<22}{r['工单数']:>5} 件 → 疑似「{r['候选纳统小区1']}」"
              f"（{r['关系1']}）")


if __name__ == "__main__":
    main()
