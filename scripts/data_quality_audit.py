import pandas as pd
import numpy as np
import json
import os
from collections import Counter

DATA_DIR = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/热线数据"

print("=" * 70)
print("12345热线数据质量专项排查")
print("=" * 70)

# ─── 1. 读取三个文件 ───
df1 = pd.read_excel(os.path.join(DATA_DIR, "2024年市局14类.xlsx"), sheet_name="Sheet1")
df2 = pd.read_excel(os.path.join(DATA_DIR, "2025 年全年、2026年 1-6 月市局14类.xlsx"), sheet_name="Sheet1")
df3 = pd.read_excel(os.path.join(DATA_DIR, "2026 年7月市局14类.xlsx"), sheet_name="Sheet1")

files = {
    "2024年": (df1, 27),
    "2025-2026H1": (df2, 23),
    "2026年7月": (df3, 21),
}

print(f"\n文件1 (2024年): {len(df1)}行 × {len(df1.columns)}列")
print(f"文件2 (2025-2026H1): {len(df2)}行 × {len(df2.columns)}列")
print(f"文件3 (2026年7月): {len(df3)}行 × {len(df3.columns)}列")

# ─── 2. 字段结构对比 ───
print("\n" + "=" * 70)
print("2. 字段结构对比")
print("=" * 70)

all_cols = {}
for name, (df, expected_cols) in files.items():
    all_cols[name] = set(df.columns.tolist())
    print(f"\n{name}字段({len(df.columns)}个):")
    for i, c in enumerate(df.columns):
        print(f"  {i+1:2d}. {c}")

# 共有字段
common = all_cols["2024年"] & all_cols["2025-2026H1"] & all_cols["2026年7月"]
only_2024 = all_cols["2024年"] - all_cols["2025-2026H1"]
only_2025 = all_cols["2025-2026H1"] - all_cols["2024年"]
only_jul = all_cols["2026年7月"] - all_cols["2025-2026H1"]

print(f"\n三文件共有字段({len(common)}个): {sorted(common)}")
print(f"\n仅2024年有({len(only_2024)}个): {sorted(only_2024)}")
print(f"\n2025-2026H1新增({len(only_2025)}个): {sorted(only_2025)}")
print(f"\n2026年7月新增({len(only_jul)}个): {sorted(only_jul)}")

# ─── 3. 字段命名差异映射 ───
print("\n" + "=" * 70)
print("3. 同义字段命名差异")
print("=" * 70)

# 手动建立映射
name_mapping = {
    "12345工单编号": ["12345工单编号", "工单编号"],
    "12345受理时间": ["12345受理时间", "受理时间"],
    "12345工单来源": ["12345工单来源", "工单来源"],
    "12345诉求区域": ["12345诉求区域", "诉求区域"],
    "12345诉求地址": ["12345诉求地址", "诉求地址"],
    "12345工单类型": ["12345工单类型", "工单类型"],
    "12345内容描述": ["12345内容描述", "内容描述"],
    "年": ["年"],
    "月份": ["月份", "月份"],
    "小区编号": ["小区编号"],
    "小区名称": ["小区名称"],
    "小区地址": ["小区地址"],
    "物业公司": ["物业公司"],
    "街道": ["街道"],
    "行政区": ["行政区"],
    "十四类": ["十四类"],
    "主办单位": ["主办单位"],
    "答复市民要点": ["答复市民要点"],
}

print("\n同义字段命名差异表：")
for standard, variants in name_mapping.items():
    found_in = {}
    for fname, (df, _) in files.items():
        for v in variants:
            if v in df.columns:
                found_in[fname] = v
                break
    if len(set(found_in.values())) > 1:
        print(f"  标准名: {standard}")
        for f, v in found_in.items():
            print(f"    {f}: '{v}'")

# ─── 4. 数据类型和格式差异 ───
print("\n" + "=" * 70)
print("4. 数据类型和格式差异")
print("=" * 70)

# 受理时间字段
print("\n受理时间字段格式：")
for fname, (df, _) in files.items():
    time_col = None
    for c in df.columns:
        if '受理时间' in c:
            time_col = c
            break
    if time_col:
        sample = df[time_col].dropna().head(3).tolist()
        dtype = df[time_col].dtype
        print(f"  {fname}: dtype={dtype}, 样本={sample}")

# 年字段
print("\n年字段格式：")
for fname, (df, _) in files.items():
    if '年' in df.columns:
        print(f"  {fname}: dtype={df['年'].dtype}, 唯一值={sorted(df['年'].dropna().unique().tolist())}")

# ─── 5. 分类字段值域差异 ───
print("\n" + "=" * 70)
print("5. 十四类分类值域差异")
print("=" * 70)

for fname, (df, _) in files.items():
    cat_col = None
    for c in df.columns:
        if '十四类' in c:
            cat_col = c
            break
    if cat_col:
        vals = df[cat_col].value_counts()
        print(f"\n{fname} 十四类值域({len(vals)}个):")
        for v, c in vals.items():
            print(f"  {v}: {c}")

# ─── 6. 缺失值排查 ───
print("\n" + "=" * 70)
print("6. 缺失值排查")
print("=" * 70)

for fname, (df, _) in files.items():
    print(f"\n{fname} 缺失值统计:")
    for col in df.columns:
        missing = df[col].isna().sum()
        if missing > 0:
            pct = missing / len(df) * 100
            print(f"  {col}: {missing}条缺失 ({pct:.1f}%)")

# ─── 7. 异常值排查 ───
print("\n" + "=" * 70)
print("7. 异常值排查")
print("=" * 70)

for fname, (df, _) in files.items():
    print(f"\n{fname} 异常值排查:")

    # 小区名称为"无"或空
    community_col = None
    for c in df.columns:
        if '小区名称' in c:
            community_col = c
            break
    if community_col:
        invalid_comm = df[df[community_col].isin(['无', '', 'nan', 'None', np.nan]) | df[community_col].isna()].shape[0]
        print(f"  小区名称为'无'或空: {invalid_comm}条 ({invalid_comm/len(df)*100:.1f}%)")

    # 街道为空
    street_col = None
    for c in df.columns:
        if c == '街道':
            street_col = c
            break
    if street_col:
        invalid_street = df[street_col].isna().sum() + df[df[street_col].isin(['无', ''])].shape[0]
        print(f"  街道为空或'无': {invalid_street}条")

    # 物业公司为空
    company_col = None
    for c in df.columns:
        if '物业公司' in c:
            company_col = c
            break
    if company_col:
        invalid_company = df[company_col].isna().sum() + df[df[company_col].isin(['无', '', 'nan'])].shape[0]
        print(f"  物业公司为空或'无': {invalid_company}条 ({invalid_company/len(df)*100:.1f}%)")

    # 内容描述为空
    content_col = None
    for c in df.columns:
        if '内容描述' in c:
            content_col = c
            break
    if content_col:
        empty_content = df[content_col].isna().sum() + df[df[content_col] == ''].shape[0]
        print(f"  内容描述为空: {empty_content}条")

# ─── 8. 街道名称一致性 ───
print("\n" + "=" * 70)
print("8. 街道名称一致性检查")
print("=" * 70)

for fname, (df, _) in files.items():
    street_col = None
    for c in df.columns:
        if c == '街道':
            street_col = c
            break
    if street_col:
        streets = sorted(df[street_col].dropna().unique().tolist())
        print(f"\n{fname} 街道值域({len(streets)}个): {streets}")

# ─── 9. 物业公司名称一致性 ───
print("\n" + "=" * 70)
print("9. 物业公司名称一致性检查（Top20）")
print("=" * 70)

for fname, (df, _) in files.items():
    company_col = None
    for c in df.columns:
        if '物业公司' in c:
            company_col = c
            break
    if company_col:
        companies = df[company_col].value_counts().head(20)
        print(f"\n{fname} 物业公司Top20:")
        for name, count in companies.items():
            print(f"  {name}: {count}")

# ─── 10. 重复工单编号检查 ───
print("\n" + "=" * 70)
print("10. 工单编号重复检查")
print("=" * 70)

for fname, (df, _) in files.items():
    id_col = None
    for c in df.columns:
        if '工单编号' in c:
            id_col = c
            break
    if id_col:
        dup_ids = df[df[id_col].duplicated(keep=False)]
        print(f"\n{fname}: 重复工单编号 {len(dup_ids)}条")
        if len(dup_ids) > 0:
            print(f"  重复编号样本: {dup_ids[id_col].head(5).tolist()}")

# ─── 11. 生成质量评分 ───
print("\n" + "=" * 70)
print("11. 数据质量评分")
print("=" * 70)

quality_scores = {}
for fname, (df, _) in files.items():
    total_cells = len(df) * len(df.columns)
    missing_cells = df.isna().sum().sum()
    completeness = (1 - missing_cells / total_cells) * 100

    # 字段一致性（与标准27列对齐度）
    if fname == "2024年":
        consistency = 100
    elif fname == "2025-2026H1":
        consistency = len(all_cols["2024年"] & all_cols["2025-2026H1"]) / len(all_cols["2024年"]) * 100
    else:
        consistency = len(all_cols["2024年"] & all_cols["2026年7月"]) / len(all_cols["2024年"]) * 100

    # 唯一性（工单编号去重率）
    id_col = None
    for c in df.columns:
        if '工单编号' in c:
            id_col = c
            break
    if id_col:
        uniqueness = (1 - df[id_col].duplicated().sum() / len(df)) * 100
    else:
        uniqueness = 0

    # 总分
    score = (completeness * 0.4 + consistency * 0.3 + uniqueness * 0.3)

    quality_scores[fname] = {
        'completeness': round(completeness, 1),
        'consistency': round(consistency, 1),
        'uniqueness': round(uniqueness, 1),
        'overall': round(score, 1),
    }
    print(f"\n{fname}:")
    print(f"  完整性: {completeness:.1f}%")
    print(f"  一致性: {consistency:.1f}%")
    print(f"  唯一性: {uniqueness:.1f}%")
    print(f"  综合评分: {score:.1f}")

print("\n完成！")
