import sqlite3
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "xuhui_complaints.db")
PKL_PATH = os.path.join(BASE_DIR, "data", "merged_cleaned.pkl")

CREATE_MAIN_TABLE = """
CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE,
    accept_time DATETIME,
    source TEXT,
    district TEXT DEFAULT '徐汇区',
    address TEXT,
    order_type TEXT,
    content TEXT,
    handler TEXT,
    reply TEXT,
    year INTEGER,
    month INTEGER,
    community_id TEXT,
    community_name TEXT,
    community_addr TEXT,
    property_company TEXT,
    street TEXT,
    category_14 TEXT,
    level1 TEXT,
    level2 TEXT,
    level3 TEXT,
    level4 TEXT,
    level5 TEXT
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_year_month ON work_orders(year, month);",
    "CREATE INDEX IF NOT EXISTS idx_street ON work_orders(street);",
    "CREATE INDEX IF NOT EXISTS idx_category ON work_orders(category_14);",
    "CREATE INDEX IF NOT EXISTS idx_company ON work_orders(property_company);",
    "CREATE INDEX IF NOT EXISTS idx_community ON work_orders(community_name);",
]

CREATE_AGG_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS monthly_stats (
        year INTEGER,
        month INTEGER,
        total_count INTEGER,
        complaint_count INTEGER,
        help_count INTEGER,
        yoy_count INTEGER,
        mom_count INTEGER,
        PRIMARY KEY (year, month)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS category_monthly_stats (
        year INTEGER,
        month INTEGER,
        category TEXT,
        count INTEGER,
        yoy_count INTEGER,
        PRIMARY KEY (year, month, category)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS street_monthly_stats (
        year INTEGER,
        month INTEGER,
        street TEXT,
        count INTEGER,
        yoy_count INTEGER,
        PRIMARY KEY (year, month, street)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS enterprise_stats (
        year INTEGER,
        property_company TEXT,
        total_count INTEGER,
        yoy_count INTEGER,
        community_count INTEGER,
        avg_per_community REAL,
        PRIMARY KEY (year, property_company)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS community_stats (
        year INTEGER,
        community_name TEXT,
        street TEXT,
        property_company TEXT,
        total_count INTEGER,
        yoy_count INTEGER,
        PRIMARY KEY (year, community_name)
    );
    """,
]

DATA_DICTIONARY = {
    "tables": {
        "work_orders": {
            "description": "12345热线物业投诉工单明细表",
            "row_count": 70000,
            "columns": {
                "year": {"type": "int", "values": "2024, 2025, 2026"},
                "month": {"type": "int", "values": "1-12"},
                "street": {"type": "text", "values": "漕河泾, 长桥, 徐家汇, 田林, 枫林路, 斜土路, 龙华, 康健新村, 天平路, 湖南路, 虹梅路, 凌云路, 华泾镇"},
                "category_14": {"type": "text", "values": "停车管理, 房屋维修, 邻里纠纷, 房屋违规使用, 业主大会/业委会, 消防管理, 群租管理, 物业安保, 旧住房改造, 清洁卫生, 物业收费, 物业服务态度, 房屋交易纠纷, 其他"},
                "property_company": {"type": "text", "values": "200+家物业企业"},
                "community_name": {"type": "text", "values": "800+个小区"},
                "order_type": {"type": "text", "values": "投诉举报类, 求助类"}
            }
        }
    }
}


def main():
    import pandas as pd

    if not os.path.exists(PKL_PATH):
        print(f"❌ 找不到清洗后的数据: {PKL_PATH}")
        print("   请先运行: python scripts/clean_data.py")
        sys.exit(1)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    df = pd.read_pickle(PKL_PATH)
    print(f"加载数据: {len(df)} 条")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("[1/3] 创建主表和索引...")
    cur.execute(CREATE_MAIN_TABLE)
    for idx_sql in CREATE_INDEXES:
        cur.execute(idx_sql)

    print("[2/3] 导入工单数据...")
    insert_cols = [
        "order_id", "accept_time", "source", "order_type", "content",
        "handler", "reply", "year", "month", "community_id",
        "community_name", "community_addr", "property_company",
        "street", "category_14"
    ]
    rows = []
    for _, r in df.iterrows():
        row = []
        for c in insert_cols:
            v = r.get(c)
            if pd.isna(v):
                row.append(None)
            elif c == "accept_time":
                row.append(str(v) if v else None)
            else:
                row.append(v)
        rows.append(tuple(row))

    placeholders = ",".join(["?"] * len(insert_cols))
    col_sql = ",".join(insert_cols)
    cur.executemany(
        f"INSERT OR IGNORE INTO work_orders ({col_sql}) VALUES ({placeholders})",
        rows
    )
    conn.commit()
    cnt = cur.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0]
    print(f"   已导入 {cnt} 条")

    print("[3/3] 创建聚合表...")
    for agg_sql in CREATE_AGG_TABLES:
        cur.execute(agg_sql)
    conn.commit()

    dict_path = os.path.join(BASE_DIR, "data", "data_dictionary.json")
    with open(dict_path, "w", encoding="utf-8") as f:
        json.dump(DATA_DICTIONARY, f, ensure_ascii=False, indent=2)

    conn.close()
    print(f"\n✅ 数据库已创建: {DB_PATH}")
    print(f"✅ 数据字典: {dict_path}")
    print("   下一步: 运行 python scripts/precompute.py 填充聚合表")


if __name__ == "__main__":
    main()
