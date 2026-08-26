import pandas as pd
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DATA_DIR = os.path.join(BASE_DIR, "热线数据")

CATEGORY_MAPPING = {
    "业委会": "业主大会/业委会",
    "群租问题": "群租管理",
    "物业服务态度/服务态度": "物业服务态度",
    "物业服务态度": "物业服务态度",
    "服务态度": "物业服务态度",
}

CATEGORY_DROP_PREFIX = ["剔除", "无"]

STANDARD_CATEGORIES = [
    "停车管理", "房屋维修", "邻里纠纷", "房屋违规使用",
    "业主大会/业委会", "消防管理", "群租管理", "物业安保",
    "旧住房改造", "清洁卫生", "物业收费", "物业服务态度",
    "房屋交易纠纷", "其他"
]

VALID_ORDER_TYPES = ["投诉举报类", "求助类"]

FIELD_MAPPING = {
    "2024": {
        "12345工单编号": "order_id",
        "12345受理时间": "accept_time",
        "12345工单来源": "source",
        "12345诉求地址": "address",
        "12345工单类型": "order_type",
        "12345内容描述": "content",
        "主办单位": "handler",
        "答复市民要点": "reply",
        "年": "year",
        "月份": "month",
        "小区编号": "community_id",
        "小区名称": "community_name",
        "小区地址": "community_addr",
        "物业公司": "property_company",
        "街道": "street",
        "十四类": "category_14",
        "一级业务分类": "level1",
        "二级业务分类": "level2",
        "三级业务分类": "level3",
        "四级业务分类": "level4",
        "五级业务分类": "level5",
    },
    "2025_2026H1": {
        "12345工单编号": "order_id",
        "12345受理时间": "accept_time",
        "12345工单来源": "source",
        "12345诉求地址": "address",
        "12345工单类型": "order_type",
        "12345内容描述": "content",
        "主办单位": "handler",
        "答复市民要点": "reply",
        "年": "year",
        "月份": "month",
        "小区编号": "community_id",
        "小区名称": "community_name",
        "小区地址": "community_addr",
        "物业公司": "property_company",
        "街道": "street",
        "十四类": "category_14",
        "一级业务分类": "level1",
        "二级业务分类": "level2",
        "三级业务分类": "level3",
        "四级业务分类": "level4",
        "五级业务分类": "level5",
    },
    "2026_07": {
        "工单编号": "order_id",
        "受理时间": "accept_time",
        "工单来源": "source",
        "诉求地址": "address",
        "工单类型": "order_type",
        "内容描述": "content",
        "主办单位": "handler",
        "答复市民要点": "reply",
        "月份": "month",
        "小区名称": "community_name",
        "小区地址": "community_addr",
        "物业公司": "property_company",
        "街道": "street",
        "十四类": "category_14",
        "一级分类": "level1",
        "二级分类": "level2",
        "三级分类": "level3",
        "四级分类": "level4",
        "五级分类": "level5",
    }
}

COMMON_COLS = [
    "order_id", "accept_time", "source", "address", "order_type",
    "content", "handler", "reply", "year", "month", "community_id",
    "community_name", "community_addr", "property_company",
    "street", "category_14", "level1", "level2", "level3", "level4", "level5"
]


def clean_street(val) -> str:
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    s = s.replace("街道办事处", "").replace("街道", "")
    if s.endswith("镇") and len(s) > 1:
        pass
    else:
        s = s.replace("镇人民政府", "")
    return s.strip()


def clean_category(val):
    if pd.isna(val) or val is None:
        return None
    s = str(val).strip()
    if s == "":
        return None
    if any(s.startswith(p) for p in CATEGORY_DROP_PREFIX):
        return None
    if s in CATEGORY_MAPPING:
        return CATEGORY_MAPPING[s]
    if s in STANDARD_CATEGORIES:
        return s
    return "其他"


def clean_company(val) -> str:
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip().replace(" ", "")


def clean_order_id(val) -> str:
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.isdigit() and len(s) <= 6:
        return s
    for prefix in ["12345", "SH"]:
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s.strip()


def clean_month(val):
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val) if 1 <= int(val) <= 12 else None
    s = str(val).strip()
    m = re.match(r"(\d{1,2})月?", s)
    if m:
        return int(m.group(1))
    return None


def load_2024() -> pd.DataFrame:
    path = os.path.join(RAW_DATA_DIR, "2024年市局14类.xlsx")
    df = pd.read_excel(path, sheet_name="Sheet1")
    df = df.rename(columns=FIELD_MAPPING["2024"])
    for col in COMMON_COLS:
        if col not in df.columns:
            df[col] = None
    df["accept_time"] = pd.to_datetime(df["accept_time"], errors="coerce")
    return df[COMMON_COLS].copy()


def load_2025_2026H1() -> pd.DataFrame:
    path = os.path.join(RAW_DATA_DIR, "2025 年全年、2026年 1-6 月市局14类.xlsx")
    df = pd.read_excel(path, sheet_name="Sheet1")
    df = df.rename(columns=FIELD_MAPPING["2025_2026H1"])
    for col in COMMON_COLS:
        if col not in df.columns:
            df[col] = None
    raw_series = df["accept_time"].copy()
    if pd.api.types.is_numeric_dtype(raw_series):
        df["accept_time"] = pd.to_datetime(
            raw_series, unit="D", origin="1899-12-30", errors="coerce"
        )
    else:
        numeric_vals = pd.to_numeric(raw_series, errors="coerce")
        mask_numeric = numeric_vals.notna()
        converted = pd.to_datetime(raw_series.astype(str), errors="coerce")
        if mask_numeric.any():
            from_excel = pd.to_datetime(
                numeric_vals[mask_numeric], unit="D", origin="1899-12-30", errors="coerce"
            )
            converted.loc[mask_numeric] = from_excel
        df["accept_time"] = converted
    return df[COMMON_COLS].copy()


def load_2026_07() -> pd.DataFrame:
    path = os.path.join(RAW_DATA_DIR, "2026 年7月市局14类.xlsx")
    df = pd.read_excel(path, sheet_name="Sheet1")
    df = df.rename(columns=FIELD_MAPPING["2026_07"])
    for col in COMMON_COLS:
        if col not in df.columns:
            df[col] = None
    df["accept_time"] = pd.to_datetime(df["accept_time"], errors="coerce")
    df["year"] = 2026
    df["community_id"] = None
    return df[COMMON_COLS].copy()


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["order_id"] = df["order_id"].apply(clean_order_id)
    df["street"] = df["street"].apply(clean_street)
    df["category_14"] = df["category_14"].apply(clean_category)
    df["property_company"] = df["property_company"].apply(clean_company)
    df["month"] = df["month"].apply(clean_month)

    for col in ["source", "address", "order_type", "content", "handler", "reply",
                "community_name", "community_addr", "level1", "level2", "level3", "level4", "level5"]:
        df[col] = df[col].where(df[col].notna(), None)
        df[col] = df[col].apply(lambda v: None if (pd.isna(v) or str(v).strip() in ["无", ""]) else (str(v).strip() if v is not None else None))

    df = df[df["category_14"].notna() & (df["category_14"] != "")]
    df = df[df["order_type"].isin(VALID_ORDER_TYPES)]

    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["month"] = pd.to_numeric(df["month"], errors="coerce").astype("Int64")

    df = df[df["year"].notna()]
    df = df[(df["year"] >= 2024) & (df["year"] <= 2026)]

    return df.reset_index(drop=True)


def merge_all() -> pd.DataFrame:
    print("[1/4] 加载2024年数据 (Sheet1)...")
    df1 = load_2024()
    print(f"   2024年: {len(df1)} 条, 时间样本: {df1['accept_time'].dropna().iloc[:2].tolist()}")

    print("[2/4] 加载2025-2026H1数据 (Sheet1)...")
    df2 = load_2025_2026H1()
    print(f"   2025-2026H1: {len(df2)} 条, 时间样本: {df2['accept_time'].dropna().iloc[:2].tolist()}")

    print("[3/4] 加载2026年7月数据...")
    df3 = load_2026_07()
    print(f"   2026.7: {len(df3)} 条, 月份样本: {df3['month'].dropna().unique()[:5]}")

    merged = pd.concat([df1, df2, df3], ignore_index=True)
    print(f"[4/4] 合并后总计: {len(merged)} 条，开始清洗...")

    cleaned = clean_dataframe(merged)
    print(f"   清洗完成: {len(cleaned)} 条 (剔除{(len(merged) - len(cleaned))}条)")

    return cleaned


def main():
    output_pkl = os.path.join(BASE_DIR, "data", "merged_cleaned.pkl")
    output_csv = os.path.join(BASE_DIR, "data", "merged_cleaned_sample.csv")
    report_path = os.path.join(BASE_DIR, "data", "_cleaning_report.txt")
    os.makedirs(os.path.dirname(output_pkl), exist_ok=True)

    df = merge_all()
    df.to_pickle(output_pkl)

    with open(report_path, "w", encoding="utf-8") as r:
        r.write("=== 数据清洗校验报告 ===\n")
        r.write(f"总记录数: {len(df)}\n")
        tmin = df["accept_time"].min()
        tmax = df["accept_time"].max()
        r.write(f"时间范围: {tmin} ~ {tmax}\n\n")

        r.write("--- 按年分布 ---\n")
        yg = df.groupby("year").size()
        r.write(yg.to_string() + "\n\n")

        r.write("--- 按年×月 交叉表 ---\n")
        ct = pd.crosstab(df["year"], df["month"])
        r.write(ct.to_string() + "\n\n")

        r.write("--- 工单类型分布 ---\n")
        r.write(df["order_type"].value_counts().to_string() + "\n\n")

        r.write("--- 14类分类分布 ---\n")
        r.write(df["category_14"].value_counts().to_string() + "\n\n")

        r.write("--- 街道分布(Top15) ---\n")
        r.write(df["street"].value_counts().head(15).to_string() + "\n\n")

        r.write("--- 物业公司数量 ---\n")
        r.write(f"物业企业总数(非空): {df['property_company'].replace('', pd.NA).nunique()}\n")
        r.write(f"小区总数(非空): {df['community_name'].replace('', pd.NA).nunique()}\n\n")

        r.write("--- 14类标准覆盖检查 ---\n")
        actual_cats = set(df["category_14"].dropna().unique())
        std_cats = set(STANDARD_CATEGORIES)
        r.write(f"不在标准14类的值: {actual_cats - std_cats}\n")
        r.write(f"标准14类中缺失的: {std_cats - actual_cats}\n")

    df.head(100).to_csv(output_csv, index=False, encoding="utf-8-sig")

    with open(report_path, "r", encoding="utf-8") as r:
        print("\n" + "=" * 50)
        print("清洗校验报告:")
        print("=" * 50)
        print(r.read())

    print(f"\n✅ 数据已保存:")
    print(f"   - 完整: {output_pkl}")
    print(f"   - 样本(100行): {output_csv}")
    print(f"   - 报告: {report_path}")


if __name__ == "__main__":
    main()
