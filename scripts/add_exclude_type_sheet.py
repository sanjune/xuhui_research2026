# -*- coding: utf-8 -*-
"""为「当月复核工单」表加「剔除类型清单」sheet 并在「去重清单」加「剔除类型」列。

需求（用户 2026-09-24）：
  1. 在 9 月复核工单下载.xlsx 中新增一个 sheet，把含下列关键词的工单都筛出来。
  2. 在「去重清单」sheet 的工单编号列后插一列「剔除类型」，把命中的类型标在该列。

关键词（按用户给定顺序）：
  商铺 / 商店 / 商场 / 园区 / 商务楼 / 集体土地 / 开发商 / 台风 / 暴雨 / 积水

扫描范围：
  12345内容描述 + 12345诉求地址 + 小区名称
  （地址字段比正文更可能写"商铺/园区"，正文比地址更可能写"台风/积水/开发商"）

⚠️ 注意：
  本脚本是「增补」操作，不动 sheet1，不动「复核结论」/「重复组明细」。
  若后续重跑 export_dedup_review_list.py，「去重清单」会被重建（不含「剔除类型」列），
  需再跑一次本脚本恢复该列。新 sheet「剔除类型清单」不受影响。

用法：
  PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 \
      scripts/add_exclude_type_sheet.py --xlsx "9月复核工单下载.xlsx"
"""
import argparse
import os

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# 按用户给定顺序，便于新 sheet 排序与去重清单着色对照
EXCLUDE_KEYWORDS = [
    "商铺", "商店", "商场", "园区", "商务楼",
    "集体土地", "开发商", "台风", "暴雨", "积水",
]
# 内容字段名映射（sheet1 列名）
FIELD_OID = "12345工单编号"
FIELD_TIME = "12345受理时间"
FIELD_ADDR = "12345诉求地址"
FIELD_DESC = "12345内容描述"
FIELD_COMMUNITY = "小区名称"
FIELD_PROPERTY = "物业公司"
FIELD_STREET = "街道"
FIELD_CAT = "十四类"
SCAN_FIELDS = [FIELD_DESC, FIELD_ADDR, FIELD_COMMUNITY]

SHEET_NAME_NEW = "剔除类型清单"
SHEET_NAME_LIST = "去重清单"
NEW_COL = "剔除类型"

# 新 sheet 字段
SHEET_COLS = [
    FIELD_OID.replace("12345", ""), FIELD_TIME.replace("12345", ""),
    FIELD_STREET, FIELD_COMMUNITY, FIELD_PROPERTY, FIELD_CAT,
    NEW_COL, "内容描述",
]

HEAD_FILL = PatternFill("solid", fgColor="1D4ED8")
HEAD_FONT = Font(color="FFFFFF", bold=True, size=11)
HIGH_FONT = Font(color="B91C1C", bold=True)
NEW_COL_FONT = Font(color="B91C1C", bold=True)
HIST_FONT = Font(color="92400E", italic=True)
CELL_ALIGN = Alignment(vertical="center", wrap_text=True)


def _join_scan_text(r) -> str:
    return " ".join(str(r.get(c, "") or "") for c in SCAN_FIELDS)


def scan_keywords(text: str):
    """返回命中关键词列表（按 EXCLUDE_KEYWORDS 顺序，去重）。"""
    out = []
    for k in EXCLUDE_KEYWORDS:
        if k in text and k not in out:
            out.append(k)
    return out


def build_exclude_df(df: pd.DataFrame) -> pd.DataFrame:
    """筛出命中工单，并按「首个命中关键词顺序 + 受理时间」排序。"""
    rows = []
    for _, r in df.iterrows():
        ks = scan_keywords(_join_scan_text(r))
        if not ks:
            continue
        rows.append({
            "工单编号": str(r[FIELD_OID]),
            "受理时间": str(r[FIELD_TIME] or ""),
            "街道": str(r[FIELD_STREET] or ""),
            "小区名称": str(r[FIELD_COMMUNITY] or ""),
            "物业公司": str(r[FIELD_PROPERTY] or ""),
            "十四类": str(r[FIELD_CAT] or ""),
            NEW_COL: "；".join(ks),
            "内容描述": str(r[FIELD_DESC] or "")[:120],
        })
    if not rows:
        return pd.DataFrame(columns=SHEET_COLS)
    out = pd.DataFrame(rows)
    order = {k: i for i, k in enumerate(EXCLUDE_KEYWORDS)}
    out["_o"] = out[NEW_COL].map(
        lambda s: order.get(s.split("；")[0], 99))
    out = out.sort_values(["_o", "受理时间"]).drop(columns=["_o"]) \
             .reset_index(drop=True)
    return out


def write_new_sheet(wb, hdf: pd.DataFrame):
    """新建「剔除类型清单」sheet。"""
    if SHEET_NAME_NEW in wb.sheetnames:
        del wb[SHEET_NAME_NEW]
    ws = wb.create_sheet(SHEET_NAME_NEW)
    for j, col in enumerate(SHEET_COLS, 1):
        c = ws.cell(row=1, column=j, value=col)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")
    for i, (_, row) in enumerate(hdf.iterrows(), 2):
        for j, col in enumerate(SHEET_COLS, 1):
            v = row[col]
            cell = ws.cell(row=i, column=j,
                           value=None if pd.isna(v) else v)
            cell.alignment = CELL_ALIGN
            if "编号" in col or "工单" in col:
                cell.number_format = "@"
            if col == NEW_COL:
                cell.font = NEW_COL_FONT
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(SHEET_COLS))}{len(hdf) + 1}"
    widths = {
        "工单编号": 18, "受理时间": 17, "街道": 12, "小区名称": 22,
        "物业公司": 22, "十四类": 15, "剔除类型": 22, "内容描述": 60,
    }
    for j, col in enumerate(SHEET_COLS, 1):
        ws.column_dimensions[get_column_letter(j)].width = widths.get(col, 14)


def insert_list_column(wb, hit_map: dict):
    """在「去重清单」sheet 的「工单编号」列后插入「剔除类型」列。"""
    if SHEET_NAME_LIST not in wb.sheetnames:
        raise RuntimeError(f"找不到 sheet「{SHEET_NAME_LIST}」")
    ws = wb[SHEET_NAME_LIST]
    cols = [c.value for c in ws[1]]
    if NEW_COL in cols:
        # 已有，先删再插（防止重复）
        existing = cols.index(NEW_COL) + 1
        ws.delete_cols(existing, 1)
        cols = [c.value for c in ws[1]]
    oid_idx = cols.index("工单编号") + 1      # 1-based
    insert_idx = oid_idx + 1                   # 工单编号列后
    ws.insert_cols(insert_idx)

    # 表头
    h = ws.cell(row=1, column=insert_idx, value=NEW_COL)
    h.fill, h.font = HEAD_FILL, HEAD_FONT
    h.alignment = Alignment(horizontal="center", vertical="center")
    ws.column_dimensions[get_column_letter(insert_idx)].width = 22

    # 逐行按工单编号回填
    n_marked = 0
    for i in range(2, ws.max_row + 1):
        oid_val = ws.cell(row=i, column=oid_idx).value
        oid_val = str(oid_val).strip() if oid_val else ""
        v = hit_map.get(oid_val, "")
        cell = ws.cell(row=i, column=insert_idx, value=v)
        cell.alignment = CELL_ALIGN
        if v:
            cell.font = NEW_COL_FONT
            n_marked += 1
        # 表外行（工单归属列含「非本月」/「未收录」）若未命中也置斜体提示
        # —— 不会标类型，仅样式区分
    return n_marked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True, help="9 月复核工单下载.xlsx 路径")
    args = ap.parse_args()
    xlsx = args.xlsx
    if not os.path.exists(xlsx):
        raise FileNotFoundError(xlsx)

    # 1) 读 sheet1 → 扫描关键词 → 筛命中
    df = pd.read_excel(xlsx, sheet_name="sheet1", dtype=str)
    hdf = build_exclude_df(df)
    hit_map = {row["工单编号"]: row[NEW_COL] for _, row in hdf.iterrows()}

    # 2) 写回 xlsx
    wb = load_workbook(xlsx)
    write_new_sheet(wb, hdf)
    n_marked = insert_list_column(wb, hit_map)
    wb.save(xlsx)

    # 3) 汇报
    print(f"✔ 新 sheet「{SHEET_NAME_NEW}」: {len(hdf)} 条命中工单")
    print(f"✔ 「{SHEET_NAME_LIST}」sheet 已在「工单编号」列后插入「{NEW_COL}」列，"
          f"清单内匹配 {n_marked} 行")
    print(f"  关键词命中分布（新 sheet 中）:")
    for k in EXCLUDE_KEYWORDS:
        n = int(hdf[NEW_COL].str.contains(k, regex=False).sum()) if len(hdf) else 0
        print(f"    {k}: {n} 条")
    print(f"  sheet 列表: {wb.sheetnames}")


if __name__ == "__main__":
    main()
