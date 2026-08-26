import sqlite3
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "xuhui_complaints.db")


def pct_change(curr, prev):
    if prev is None or prev == 0:
        return None
    return round((curr - prev) / prev * 100, 2)


def compute_monthly_stats(conn):
    print("[1/5] 计算月度总量统计...")
    df = pd.read_sql("""
        SELECT year, month, order_type, COUNT(*) as cnt
        FROM work_orders
        GROUP BY year, month, order_type
    """, conn)

    pivot = df.pivot_table(index=["year", "month"], columns="order_type",
                           values="cnt", fill_value=0).reset_index()
    total_col = pivot.sum(axis=1) if pivot.empty else 0
    pivot["total_count"] = pivot.get("投诉举报类", 0) + pivot.get("求助类", 0)
    pivot["complaint_count"] = pivot.get("投诉举报类", 0)
    pivot["help_count"] = pivot.get("求助类", 0)

    rows = []
    for _, r in pivot.iterrows():
        y, m = int(r["year"]), int(r["month"])
        prev_y = y - 1
        prev_m_row = pivot[(pivot["year"] == prev_y) & (pivot["month"] == m)]
        mom_row = pivot[
            ((pivot["year"] == y) & (pivot["month"] == m - 1))
            | ((pivot["year"] == y - 1) & (pivot["month"] == 12) & (m == 1))
        ]
        yoy = int(prev_m_row["total_count"].iloc[0]) if len(prev_m_row) else 0
        mom = int(mom_row["total_count"].iloc[0]) if len(mom_row) else 0
        rows.append((y, m, int(r["total_count"]),
                     int(r["complaint_count"]), int(r["help_count"]), yoy, mom))

    cur = conn.cursor()
    cur.executemany(
        "INSERT OR REPLACE INTO monthly_stats VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()


def compute_category_monthly(conn):
    print("[2/5] 计算类别×月度统计...")
    df = pd.read_sql("""
        SELECT year, month, category_14 as category, COUNT(*) as count
        FROM work_orders
        GROUP BY year, month, category_14
    """, conn)

    rows = []
    for _, r in df.iterrows():
        y, m, cat = int(r["year"]), int(r["month"]), r["category"]
        prev = df[(df["year"] == y - 1) & (df["month"] == m) & (df["category"] == cat)]
        yoy = int(prev["count"].iloc[0]) if len(prev) else 0
        rows.append((y, m, cat, int(r["count"]), yoy))

    cur = conn.cursor()
    cur.executemany(
        "INSERT OR REPLACE INTO category_monthly_stats VALUES (?,?,?,?,?)", rows)
    conn.commit()


def compute_street_monthly(conn):
    print("[3/5] 计算街道×月度统计...")
    df = pd.read_sql("""
        SELECT year, month, street, COUNT(*) as count
        FROM work_orders
        WHERE street IS NOT NULL AND street != ''
        GROUP BY year, month, street
    """, conn)

    rows = []
    for _, r in df.iterrows():
        y, m, st = int(r["year"]), int(r["month"]), r["street"]
        prev = df[(df["year"] == y - 1) & (df["month"] == m) & (df["street"] == st)]
        yoy = int(prev["count"].iloc[0]) if len(prev) else 0
        rows.append((y, m, st, int(r["count"]), yoy))

    cur = conn.cursor()
    cur.executemany(
        "INSERT OR REPLACE INTO street_monthly_stats VALUES (?,?,?,?,?)", rows)
    conn.commit()


def compute_enterprise_stats(conn):
    print("[4/5] 计算物业企业统计...")
    df = pd.read_sql("""
        SELECT year, property_company, COUNT(*) as total_count,
               COUNT(DISTINCT community_name) as community_count
        FROM work_orders
        WHERE property_company IS NOT NULL AND property_company != ''
        GROUP BY year, property_company
    """, conn)

    rows = []
    for _, r in df.iterrows():
        y, comp = int(r["year"]), r["property_company"]
        prev = df[(df["year"] == y - 1) & (df["property_company"] == comp)]
        yoy = int(prev["total_count"].iloc[0]) if len(prev) else 0
        cc = int(r["community_count"])
        avg = round(int(r["total_count"]) / cc, 2) if cc > 0 else 0
        rows.append((y, comp, int(r["total_count"]), yoy, cc, avg))

    cur = conn.cursor()
    cur.executemany(
        "INSERT OR REPLACE INTO enterprise_stats VALUES (?,?,?,?,?,?)", rows)
    conn.commit()


def compute_community_stats(conn):
    print("[5/5] 计算小区统计...")
    df = pd.read_sql("""
        SELECT year, community_name,
               MAX(street) as street,
               MAX(property_company) as property_company,
               COUNT(*) as total_count
        FROM work_orders
        WHERE community_name IS NOT NULL AND community_name != ''
        GROUP BY year, community_name
    """, conn)

    rows = []
    for _, r in df.iterrows():
        y, comm = int(r["year"]), r["community_name"]
        prev = df[(df["year"] == y - 1) & (df["community_name"] == comm)]
        yoy = int(prev["total_count"].iloc[0]) if len(prev) else 0
        rows.append((y, comm, r["street"] or "", r["property_company"] or "",
                     int(r["total_count"]), yoy))

    cur = conn.cursor()
    cur.executemany(
        "INSERT OR REPLACE INTO community_stats VALUES (?,?,?,?,?,?)", rows)
    conn.commit()


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ 找不到数据库: {DB_PATH}")
        print("   请先运行: python scripts/build_database.py")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    compute_monthly_stats(conn)
    compute_category_monthly(conn)
    compute_street_monthly(conn)
    compute_enterprise_stats(conn)
    compute_community_stats(conn)

    for t in ["monthly_stats", "category_monthly_stats", "street_monthly_stats",
              "enterprise_stats", "community_stats"]:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"   {t}: {cnt} 条")

    conn.close()
    print("\n✅ 预计算完成!")


if __name__ == "__main__":
    main()
