from typing import Optional, List, Dict, Any, Tuple
import sqlite3
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "xuhui_complaints.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def pct_change_str(curr: Optional[int], prev: Optional[int]) -> str:
    if not prev or prev <= 0:
        return "—"
    v = (curr - prev) / prev * 100
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def period_text(year: int, month: Optional[int]) -> str:
    if month:
        return f"{year}年{month}月"
    return f"{year}年全年"


def make_table(headers: List[str], rows: List[List[Any]]) -> Dict[str, Any]:
    return {"headers": headers, "rows": rows}


# =======================================================
# 1. get_summary — 综合概览 (P0)
# 演示问题Q1: "这个月全区投诉情况怎么样？"
# =======================================================
def get_summary(year: int, month: Optional[int] = None) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()

    if month:
        row = cur.execute(
            "SELECT total_count, complaint_count, help_count, yoy_count, mom_count "
            "FROM monthly_stats WHERE year=? AND month=?",
            (year, month)
        ).fetchone()
        if not row:
            conn.close()
            return {"period": period_text(year, month), "total": 0,
                    "yoy_change": "—", "mom_change": "—",
                    "top3_categories": [], "top3_streets": [],
                    "_table": make_table(["指标", "数值"], [])}
        total, comp, help_cnt, yoy_cnt, mom_cnt = row
        period = period_text(year, month)
    else:
        q = cur.execute(
            "SELECT SUM(total_count),SUM(complaint_count),SUM(help_count) "
            "FROM monthly_stats WHERE year=?", (year,)
        ).fetchone()
        total, comp, help_cnt = (q[0] or 0), (q[1] or 0), (q[2] or 0)
        yoy_q = cur.execute(
            "SELECT SUM(total_count) FROM monthly_stats WHERE year=?", (year - 1,)
        ).fetchone()
        yoy_cnt = yoy_q[0] if yoy_q else 0
        mom_cnt = 0
        period = period_text(year, None)

    cat_sql = (
        "SELECT category, count, yoy_count FROM category_monthly_stats "
        "WHERE year=? " + ("AND month=?" if month else "GROUP BY category") +
        " ORDER BY count DESC LIMIT 3"
    )
    cat_args = (year, month) if month else (year,)
    cat_rows = cur.execute(cat_sql, cat_args).fetchall()

    street_sql = (
        "SELECT street, count, yoy_count FROM street_monthly_stats "
        "WHERE year=? " + ("AND month=?" if month else "GROUP BY street") +
        " ORDER BY count DESC LIMIT 3"
    )
    street_args = (year, month) if month else (year,)
    street_rows = cur.execute(street_sql, street_args).fetchall()
    conn.close()

    top3_categories = [
        {"name": r[0], "count": int(r[1]), "yoy_change": pct_change_str(int(r[1]), int(r[2] or 0))}
        for r in cat_rows
    ]
    top3_streets = [
        {"name": r[0], "count": int(r[1]), "yoy_change": pct_change_str(int(r[1]), int(r[2] or 0))}
        for r in street_rows
    ]

    headers = ["指标", "数值"]
    rows = [
        ["统计周期", period],
        ["12345工单总量", f"{int(total):,} 件"],
        ["同比变化", pct_change_str(int(total), int(yoy_cnt or 0))],
    ]
    if mom_cnt and month:
        rows.append(["环比变化", pct_change_str(int(total), int(mom_cnt))])
    rows.append(["其中：投诉举报类", f"{int(comp or 0):,} 件"])
    rows.append(["　　　求助类", f"{int(help_cnt or 0):,} 件"])
    rows.append(["Top 3 类别", " / ".join(f"{c['name']}({c['count']}件{c['yoy_change']})" for c in top3_categories)])
    rows.append(["Top 3 街道", " / ".join(f"{s['name']}({s['count']}件{s['yoy_change']})" for s in top3_streets)])

    return {
        "period": period,
        "total": int(total or 0),
        "yoy_change": pct_change_str(int(total or 0), int(yoy_cnt or 0)),
        "mom_change": pct_change_str(int(total or 0), int(mom_cnt or 0)) if month else "—",
        "top3_categories": top3_categories,
        "top3_streets": top3_streets,
        "_table": make_table(headers, rows)
    }


# =======================================================
# 2. get_trend — 趋势查询 (P0)
# 演示问题Q2: "今年的投诉量和去年比降了没有？"
# =======================================================
def get_trend(year: int, dimension: str = "total",
              dimension_value: Optional[str] = None,
              compare_year: Optional[int] = None) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    compare_year = compare_year or (year - 1)
    period = f"{year}年1-12月 vs {compare_year}年"

    if dimension == "total":
        curr_rows = cur.execute(
            "SELECT month, total_count FROM monthly_stats WHERE year=? ORDER BY month",
            (year,)
        ).fetchall()
        prev_rows = cur.execute(
            "SELECT month, total_count FROM monthly_stats WHERE year=? ORDER BY month",
            (compare_year,)
        ).fetchall()
    elif dimension == "category":
        curr_rows = cur.execute(
            "SELECT month, count FROM category_monthly_stats WHERE year=? AND category=? ORDER BY month",
            (year, dimension_value or "")
        ).fetchall()
        prev_rows = cur.execute(
            "SELECT month, count FROM category_monthly_stats WHERE year=? AND category=? ORDER BY month",
            (compare_year, dimension_value or "")
        ).fetchall()
    elif dimension == "street":
        curr_rows = cur.execute(
            "SELECT month, count FROM street_monthly_stats WHERE year=? AND street=? ORDER BY month",
            (year, dimension_value or "")
        ).fetchall()
        prev_rows = cur.execute(
            "SELECT month, count FROM street_monthly_stats WHERE year=? AND street=? ORDER BY month",
            (compare_year, dimension_value or "")
        ).fetchall()
    else:
        curr_rows, prev_rows = [], []
    conn.close()

    curr_dict = {int(r[0]): int(r[1]) for r in curr_rows}
    prev_dict = {int(r[0]): int(r[1]) for r in prev_rows}
    months_range = list(range(1, 13))
    current_data = [{"month": m, "count": curr_dict.get(m, 0)} for m in months_range]
    compare_data = [{"month": m, "count": prev_dict.get(m, 0)} for m in months_range]
    total_current = sum(curr_dict.values())
    total_compare = sum(prev_dict.values())

    dim_label = dimension_value or "全区总量"
    headers = ["月份", f"{year}年(件)", f"{compare_year}年(件)", "同比"]
    rows = []
    for m in months_range:
        c = curr_dict.get(m, 0)
        p = prev_dict.get(m, 0)
        rows.append([f"{m}月", c, p, pct_change_str(c, p)])
    rows.append(["合计", total_current, total_compare, pct_change_str(total_current, total_compare)])

    return {
        "period": period,
        "dimension": dimension,
        "dimension_value": dimension_value,
        "compare_year": compare_year,
        "current_data": current_data,
        "compare_data": compare_data,
        "total_current": total_current,
        "total_compare": total_compare,
        "yoy_change": pct_change_str(total_current, total_compare),
        "dim_label": dim_label,
        "_table": make_table(headers, rows)
    }


# =======================================================
# 3. get_ranking — 排行查询 (P0)
# 演示问题Q3: "本月投诉量最多的5个街道是哪些？"
# =======================================================
def get_ranking(year: int, dimension: str, month: Optional[int] = None,
                top_n: int = 10, order: str = "desc") -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    period = period_text(year, month)
    dim_map = {
        "street": ("street_monthly_stats", "street", "街道"),
        "category": ("category_monthly_stats", "category", "类别"),
        "community": ("community_stats", "community_name", "小区"),
        "enterprise": ("enterprise_stats", "property_company", "物业企业"),
    }
    if dimension not in dim_map:
        conn.close()
        return {"period": period, "dimension": dimension, "ranking": [], "_table": make_table([], [])}
    tbl, col, dim_cn = dim_map[dimension]
    order_sql = "DESC" if order.lower() == "desc" else "ASC"

    if dimension in ("street", "category"):
        where = "WHERE year=?"
        args: Tuple[Any, ...] = (year,)
        if month:
            where += " AND month=?"
            args = (year, month)
        sql = (
            f"SELECT {col}, SUM(count) as cnt, SUM(yoy_count) as yoy "
            f"FROM {tbl} {where} GROUP BY {col} ORDER BY cnt {order_sql} LIMIT ?"
        )
        args = args + (top_n,)
        rows_db = cur.execute(sql, args).fetchall()
    else:
        where = "WHERE year=?"
        args = (year,)
        sql = (
            f"SELECT {col}, total_count as cnt, yoy_count as yoy "
            f"FROM {tbl} {where} ORDER BY cnt {order_sql} LIMIT ?"
        )
        args = args + (top_n,)
        rows_db = cur.execute(sql, args).fetchall()

    if dimension == "community" and rows_db:
        extra = cur.execute(
            "SELECT community_name, street, property_company FROM work_orders "
            f"WHERE year=? AND community_name IN ({','.join('?'*len(rows_db))}) GROUP BY community_name",
            (year,) + tuple(r[0] for r in rows_db)
        ).fetchall()
        meta = {r[0]: (r[1], r[2]) for r in extra}
    else:
        meta = {}
    conn.close()

    ranking = []
    headers = ["排名", dim_cn, "投诉量(件)", "同比"]
    if dimension == "community":
        headers = ["排名", "小区", "所属街道", "物业企业", "投诉量(件)", "同比"]
    rows = []
    for i, r in enumerate(rows_db, 1):
        name, cnt, yoy = r[0], int(r[1] or 0), int(r[2] or 0)
        item = {"rank": i, "name": str(name or ""), "count": cnt, "yoy_change": pct_change_str(cnt, yoy)}
        if dimension == "community":
            street, comp = meta.get(name, ("", ""))
            item["street"] = street
            item["property_company"] = comp
            rows.append([i, name, street, comp, cnt, pct_change_str(cnt, yoy)])
        else:
            rows.append([i, name, cnt, pct_change_str(cnt, yoy)])
        ranking.append(item)

    return {
        "period": period,
        "dimension": dim_cn,
        "top_n": top_n,
        "ranking": ranking,
        "_table": make_table(headers, rows)
    }


# =======================================================
# 4. get_category_detail — 类别分析 (P0)
# 演示问题Q4: "停车类投诉主要集中在哪些小区？"
# =======================================================
def get_category_detail(category: str, year: int, month: Optional[int] = None,
                        group_by: str = "community", top_n: int = 10) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    period = period_text(year, month)

    where_sql = "WHERE year=? AND category_14=?"
    args: Tuple[Any, ...] = (year, category)
    if month:
        where_sql += " AND month=?"
        args = (year, category, month)

    total_q = cur.execute(f"SELECT COUNT(*) FROM work_orders {where_sql}", args).fetchone()
    total = int(total_q[0] or 0)
    community_count_q = cur.execute(
        f"SELECT COUNT(DISTINCT community_name) FROM work_orders {where_sql} AND community_name IS NOT NULL AND community_name != ''",
        args
    ).fetchone()
    community_count = int(community_count_q[0] or 0)

    if group_by == "street":
        group_sql = f"SELECT street, COUNT(*) as cnt FROM work_orders {where_sql} GROUP BY street ORDER BY cnt DESC LIMIT ?"
        headers = ["排名", "街道", "投诉量(件)", "占比"]
    elif group_by == "enterprise":
        group_sql = (
            f"SELECT property_company, COUNT(*) as cnt FROM work_orders {where_sql} "
            f"AND property_company IS NOT NULL AND property_company != '' GROUP BY property_company ORDER BY cnt DESC LIMIT ?"
        )
        headers = ["排名", "物业企业", "投诉量(件)", "占比"]
    else:
        group_sql = (
            f"SELECT community_name, MAX(street), MAX(property_company), COUNT(*) as cnt "
            f"FROM work_orders {where_sql} AND community_name IS NOT NULL AND community_name != '' "
            f"GROUP BY community_name ORDER BY cnt DESC LIMIT ?"
        )
        headers = ["排名", "小区", "所属街道", "物业企业", "投诉量(件)", "占比"]

    rows_db = cur.execute(group_sql, args + (top_n,)).fetchall()
    conn.close()

    top_communities = []
    rows = []
    for i, r in enumerate(rows_db, 1):
        pct = f"{int(r[-1] or 0) / total * 100:.1f}%" if total else "0%"
        if group_by == "community":
            name, street, comp, cnt = r[0], r[1] or "", r[2] or "", int(r[3] or 0)
            top_communities.append({"rank": i, "community": name, "street": street,
                                    "company": comp, "count": cnt, "ratio": pct})
            rows.append([i, name, street, comp, cnt, pct])
        elif group_by == "street":
            name, cnt = r[0], int(r[1] or 0)
            top_communities.append({"rank": i, "street": name, "count": cnt, "ratio": pct})
            rows.append([i, name, cnt, pct])
        else:
            name, cnt = r[0], int(r[1] or 0)
            top_communities.append({"rank": i, "company": name, "count": cnt, "ratio": pct})
            rows.append([i, name, cnt, pct])

    # Sub_issues: level4/level5 子问题Top
    # sub_issues from work_orders where category match
    conn2 = get_conn()
    cur2 = conn2.cursor()
    sub_rows = cur2.execute(
        f"SELECT IFNULL(level4, IFNULL(level3, category_14)) sub, COUNT(*) cnt "
        f"FROM work_orders {where_sql} GROUP BY sub ORDER BY cnt DESC LIMIT 5",
        args
    ).fetchall()
    conn2.close()
    sub_issues = [{"name": r[0] or "其他", "count": int(r[1] or 0)} for r in sub_rows]

    return {
        "period": period,
        "category": category,
        "total": total,
        "community_count": community_count,
        "group_by": group_by,
        "top_communities": top_communities,
        "sub_issues": sub_issues,
        "_table": make_table(headers, rows)
    }


# =======================================================
# 5. get_comparison — 对比查询 (P1)
# 演示问题Q5: "徐房集团和城投集团今年表现怎么样？"
# =======================================================
def get_comparison(entity_type: str, entity_names: List[str],
                   year: int, month: Optional[int] = None) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    period = period_text(year, month)

    where_year = " year=?"
    args: Tuple[Any, ...] = (year,)
    if month:
        where_year += " AND month=?"
        args = (year, month)

    if entity_type == "enterprise":
        results = []
        for name in entity_names:
            # 模糊匹配:去掉"集团/物业/公司"等后缀,用核心词匹配
            # 例: "徐房集团" -> 用 "%徐房%" 匹配 "上海徐房物业有限公司"
            core = name
            for suffix in ("集团", "公司", "物业", "管理"):
                if core.endswith(suffix):
                    core = core[:-len(suffix)]
            core = core.strip() or name
            like_core = f"%{core}%"
            like_full = f"%{name}%"
            sql = (
                "SELECT COUNT(*) total, COUNT(DISTINCT community_name) community_count "
                f"FROM work_orders WHERE{where_year} "
                f"AND (REPLACE(property_company,' ','') LIKE ? OR REPLACE(property_company,' ','') LIKE ?)"
            )
            r = cur.execute(sql, args + (like_full, like_core)).fetchone()
            total, cc = int(r[0] or 0), int(r[1] or 0)
            actual_name_rows = cur.execute(
                f"SELECT DISTINCT property_company FROM work_orders WHERE{where_year} "
                f"AND (REPLACE(property_company,' ','') LIKE ? OR REPLACE(property_company,' ','') LIKE ?) LIMIT 5",
                args + (like_full, like_core)
            ).fetchall()
            actual_names = [ar[0] for ar in actual_name_rows if ar[0]]
            avg = round(total / cc, 2) if cc else 0
            # Street distribution
            st_rows = cur.execute(
                f"SELECT street, COUNT(*) c FROM work_orders WHERE{where_year} "
                f"AND (REPLACE(property_company,' ','') LIKE ? OR REPLACE(property_company,' ','') LIKE ?) "
                f"GROUP BY street ORDER BY c DESC LIMIT 3",
                args + (like_full, like_core)
            ).fetchall()
            top_streets = [{"street": s[0], "count": int(s[1])} for s in st_rows]
            # 14类分布
            cat_rows = cur.execute(
                f"SELECT category_14, COUNT(*) c FROM work_orders WHERE{where_year} "
                f"AND (REPLACE(property_company,' ','') LIKE ? OR REPLACE(property_company,' ','') LIKE ?) "
                f"GROUP BY category_14 ORDER BY c DESC LIMIT 3",
                args + (like_full, like_core)
            ).fetchall()
            top_categories = [{"category": c[0], "count": int(c[1])} for c in cat_rows]
            results.append({
                "entity_name": name,
                "matched_names": actual_names,
                "total": total,
                "community_count": cc,
                "avg_per_community": avg,
                "top_streets": top_streets,
                "top_categories": top_categories,
            })
    elif entity_type == "street":
        results = []
        for name in entity_names:
            sql = f"SELECT COUNT(*) total, COUNT(DISTINCT community_name) community_count FROM work_orders WHERE{where_year} AND street=?"
            r = cur.execute(sql, args + (name,)).fetchone()
            total, cc = int(r[0] or 0), int(r[1] or 0)
            avg = round(total / cc, 2) if cc else 0
            st_rows = cur.execute(
                f"SELECT category_14, COUNT(*) c FROM work_orders WHERE{where_year} AND street=? GROUP BY category_14 ORDER BY c DESC LIMIT 3",
                args + (name,)
            ).fetchall()
            top_cats = [{"category": c[0], "count": int(c[1])} for c in st_rows]
            com_rows = cur.execute(
                f"SELECT community_name, COUNT(*) c FROM work_orders WHERE{where_year} AND street=? GROUP BY community_name ORDER BY c DESC LIMIT 3",
                args + (name,)
            ).fetchall()
            top_coms = [{"community": c[0], "count": int(c[1])} for c in com_rows]
            results.append({
                "entity_name": name,
                "total": total,
                "community_count": cc,
                "avg_per_community": avg,
                "top_categories": top_cats,
                "top_communities": top_coms,
            })
    else:
        results = []
    conn.close()

    headers = ["对比维度"] + [r["entity_name"] for r in results]
    rows = [
        ["投诉总量 (件)"] + [r["total"] for r in results],
        ["覆盖小区数 (个)"] + [r["community_count"] for r in results],
        ["小区均投诉 (件/小区)"] + [r["avg_per_community"] for r in results],
    ]
    if entity_type == "enterprise":
        rows.append(["实际匹配名称"] + [" / ".join(r["matched_names"][:2]) or "—" for r in results])
    rows.append(
        ["Top 类别结构"] + [
            " / ".join(f"{x['category']}({x['count']})" for x in (r.get("top_categories") or []))
            for r in results
        ]
    )

    return {
        "period": period,
        "entity_type": entity_type,
        "entities": results,
        "_table": make_table(headers, rows)
    }


# =======================================================
# 6. get_hotspot — 热点查询 (P1)
# 演示问题Q7: "哪些小区今年投诉增长最快？"
# =======================================================
def get_hotspot(year: int, metric: str = "growth", top_n: int = 20) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()

    if metric == "volume":
        sql = (
            "SELECT c.community_name, IFNULL(c.street, w.street) street, "
            "       IFNULL(c.property_company, w.property_company) company, "
            "       c.total_count cnt, c.yoy_count yoy "
            "FROM community_stats c LEFT JOIN (SELECT community_name, MAX(street) street, MAX(property_company) property_company FROM work_orders GROUP BY community_name) w ON c.community_name=w.community_name "
            "WHERE c.year=? AND c.total_count >= 5 ORDER BY cnt DESC LIMIT ?"
        )
        rows_db = cur.execute(sql, (year, top_n)).fetchall()
    elif metric == "density":
        sql = (
            "SELECT c.community_name, IFNULL(c.street, w.street) street, "
            "       IFNULL(c.property_company, w.property_company) company, "
            "       c.total_count cnt, c.yoy_count yoy "
            "FROM community_stats c LEFT JOIN (SELECT community_name, MAX(street) street, MAX(property_company) property_company FROM work_orders GROUP BY community_name) w ON c.community_name=w.community_name "
            "WHERE c.year=? AND c.total_count >= 5 "
            "ORDER BY (CASE WHEN c.yoy_count IS NULL OR c.yoy_count = 0 THEN c.total_count ELSE CAST(c.total_count AS REAL)/c.yoy_count END) DESC LIMIT ?"
        )
        rows_db = cur.execute(sql, (year, top_n)).fetchall()
    else:
        sql = (
            "SELECT c.community_name, IFNULL(c.street, w.street) street, "
            "       IFNULL(c.property_company, w.property_company) company, "
            "       c.total_count cnt, c.yoy_count yoy "
            "FROM community_stats c LEFT JOIN (SELECT community_name, MAX(street) street, MAX(property_company) property_company FROM work_orders GROUP BY community_name) w ON c.community_name=w.community_name "
            "WHERE c.year=? AND c.yoy_count >= 3 AND c.total_count > c.yoy_count ORDER BY (CAST(c.total_count - c.yoy_count AS REAL)/c.yoy_count) DESC LIMIT ?"
        )
        rows_db = cur.execute(sql, (year, top_n)).fetchall()
    conn.close()

    metric_map = {"growth": "同比增长最快", "density": "小区密度最高", "volume": "投诉量最多"}
    hotspots = []
    headers = ["排名", "小区", "所属街道", "物业企业", "今年投诉", "去年同期", "同比"]
    rows = []
    for i, r in enumerate(rows_db, 1):
        name, street, company, cnt, yoy = (r[0] or ""), (r[1] or ""), (r[2] or ""), int(r[3] or 0), int(r[4] or 0)
        yoy_str = pct_change_str(cnt, yoy)
        hotspots.append({
            "rank": i, "community": name, "street": street,
            "company": company, "count": cnt, "prev_year_count": yoy, "yoy_change": yoy_str
        })
        rows.append([i, name, street, company, cnt, yoy or 0, yoy_str])

    return {
        "year": year,
        "metric": metric_map.get(metric, metric),
        "top_n": top_n,
        "hotspots": hotspots,
        "_table": make_table(headers, rows)
    }


# =======================================================
# 7. get_repeat — 重复投诉 (P1)
# 演示问题Q6: "重复投诉率是多少？哪些小区最严重？"
# =======================================================
def get_repeat(year: int, half: int) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    period = f"{year}年1-6月" if half == 1 else f"{year}年7-12月"
    month_start, month_end = (1, 6) if half == 1 else (7, 12)

    total_q = cur.execute(
        "SELECT COUNT(*) FROM work_orders WHERE year=? AND month BETWEEN ? AND ?",
        (year, month_start, month_end)
    ).fetchone()
    total_orders = int(total_q[0] or 0)

    repeat_cnt_sql = (
        "SELECT COUNT(*) FROM ("
        "  SELECT community_name, SUBSTR(REPLACE(content,' ',''),1,20), COUNT(*) c "
        "  FROM work_orders WHERE year=? AND month BETWEEN ? AND ?"
        "   AND community_name IS NOT NULL AND community_name != '' "
        "   AND content IS NOT NULL AND content != ''"
        "  GROUP BY community_name, SUBSTR(REPLACE(content,' ',''),1,20)"
        "  HAVING c >= 2"
        ") t"
    )
    repeat_sub = cur.execute(repeat_cnt_sql, (year, month_start, month_end)).fetchall()
    repeat_sub_orders = int(repeat_sub[0][0] or 0) if repeat_sub else 0
    # 近似: 重复投诉件数 = 重复的（c - 1）累计
    repeat_actual_sql = (
        "SELECT SUM(c - 1) FROM ("
        "  SELECT community_name, SUBSTR(REPLACE(content,' ',''),1,20), COUNT(*) c "
        "  FROM work_orders WHERE year=? AND month BETWEEN ? AND ? "
        "   AND community_name IS NOT NULL AND community_name != '' "
        "  GROUP BY community_name, SUBSTR(REPLACE(content,' ',''),1,20)"
        "  HAVING c >= 2"
        ") t"
    )
    rep_r = cur.execute(repeat_actual_sql, (year, month_start, month_end)).fetchone()
    repeat_orders = int(rep_r[0] or 0)

    # Top 小区（重复次数最多的）
    top_com_sql = (
        "SELECT community_name, MAX(street), SUM(c - 1) as repeat_cnt FROM ("
        "  SELECT community_name, MAX(street) street, SUBSTR(REPLACE(content,' ',''),1,20), COUNT(*) c "
        "  FROM work_orders WHERE year=? AND month BETWEEN ? AND ? "
        "   AND community_name IS NOT NULL AND community_name != '' "
        "  GROUP BY community_name, SUBSTR(REPLACE(content,' ',''),1,20)"
        "  HAVING c >= 2"
        ") t GROUP BY community_name ORDER BY repeat_cnt DESC LIMIT 10"
    )
    top_com_rows = cur.execute(top_com_sql, (year, month_start, month_end)).fetchall()

    top_cat_sql = (
        "SELECT category_14, SUM(c - 1) as repeat_cnt FROM ("
        "  SELECT category_14, community_name, SUBSTR(REPLACE(content,' ',''),1,20), COUNT(*) c "
        "  FROM work_orders WHERE year=? AND month BETWEEN ? AND ? "
        "  GROUP BY category_14, community_name, SUBSTR(REPLACE(content,' ',''),1,20)"
        "  HAVING c >= 2"
        ") t GROUP BY category_14 ORDER BY repeat_cnt DESC LIMIT 5"
    )
    top_cat_rows = cur.execute(top_cat_sql, (year, month_start, month_end)).fetchall()
    conn.close()

    # 文档示例给出 2026年上半年 重复投诉率3.2% (约300重复/9239≈3.2%)
    # 此处：基于小区+content前20字符近似重复匹配
    repeat_rate = f"{repeat_orders / total_orders * 100:.1f}%" if total_orders else "0%"

    top_communities = []
    com_headers = ["排名", "小区", "所属街道", "重复投诉件数"]
    com_rows = []
    for i, r in enumerate(top_com_rows, 1):
        name, street, cnt = r[0] or "", r[1] or "", int(r[2] or 0)
        top_communities.append({"rank": i, "community": name, "street": street, "repeat_count": cnt})
        com_rows.append([i, name, street, cnt])

    top_categories = [
        {"category": r[0], "repeat_count": int(r[1] or 0)} for r in top_cat_rows
    ]

    headers = ["指标", "数值"]
    rows = [
        ["统计周期", period],
        ["工单总量", f"{total_orders:,} 件"],
        ["重复投诉件数", f"{repeat_orders} 件 (近似)"],
        ["重复投诉率", repeat_rate],
        ["Top 3 重复最多类别", " / ".join(f"{x['category']}({x['repeat_count']})" for x in top_categories[:3]) or "—"],
        ["Top 3 重复最多小区", " / ".join(f"{c['community']}({c['repeat_count']}件)" for c in top_communities[:3]) or "—"],
    ]

    return {
        "period": period,
        "total_orders": total_orders,
        "repeat_orders": repeat_orders,
        "repeat_rate": repeat_rate,
        "top_communities": top_communities,
        "top_categories": top_categories,
        "_table_summary": make_table(headers, rows),
        "_table_communities": make_table(com_headers, com_rows),
        "_table": make_table(headers, rows)
    }


# =======================================================
# 8. get_property — 物业企业 (P0)
# =======================================================
def get_property(year: int, month: Optional[int] = None,
                 enterprise: Optional[str] = None,
                 top_n: int = 10) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    period = period_text(year, month)

    if enterprise:
        # 模糊匹配:去掉"集团/物业/公司"等后缀,用核心词匹配
        core = enterprise
        for suffix in ("集团", "公司", "物业", "管理"):
            if core.endswith(suffix):
                core = core[:-len(suffix)]
        core = core.strip() or enterprise
        like_core = f"%{core}%"
        like_full = f"%{enterprise}%"
        where = " year=?"
        args: Tuple[Any, ...] = (year,)
        if month:
            where += " AND month=?"
            args = (year, month)
        sql = (
            f"SELECT COUNT(*) total, COUNT(DISTINCT community_name) community_count, "
            f"       COUNT(DISTINCT street) street_count FROM work_orders"
            f" WHERE{where} "
            f"AND (REPLACE(property_company,' ','') LIKE ? OR REPLACE(property_company,' ','') LIKE ?)"
        )
        r = cur.execute(sql, args + (like_full, like_core)).fetchone()
        total, cc, sc = int(r[0] or 0), int(r[1] or 0), int(r[2] or 0)

        actual_names_row = cur.execute(
            f"SELECT DISTINCT property_company FROM work_orders"
            f" WHERE{where} "
            f"AND (REPLACE(property_company,' ','') LIKE ? OR REPLACE(property_company,' ','') LIKE ?) LIMIT 5",
            args + (like_full, like_core)
        ).fetchall()
        actual_names = [a[0] for a in actual_names_row if a[0]]
        avg = round(total / cc, 2) if cc else 0

        cat_r = cur.execute(
            f"SELECT category_14, COUNT(*) c FROM work_orders"
            f" WHERE{where} "
            f"AND (REPLACE(property_company,' ','') LIKE ? OR REPLACE(property_company,' ','') LIKE ?)"
            " GROUP BY category_14 ORDER BY c DESC LIMIT 5",
            args + (like_full, like_core)
        ).fetchall()
        categories = [{"category": c[0], "count": int(c[1])} for c in cat_r]

        com_r = cur.execute(
            f"SELECT community_name, MAX(street), COUNT(*) c FROM work_orders"
            f" WHERE{where} "
            f"AND (REPLACE(property_company,' ','') LIKE ? OR REPLACE(property_company,' ','') LIKE ?)"
            " GROUP BY community_name ORDER BY c DESC LIMIT 10",
            args + (like_full, like_core)
        ).fetchall()
        communities = [
            {"community": c[0] or "", "street": c[1] or "", "count": int(c[2] or 0)}
            for c in com_r
        ]

        headers = ["指标", "数值"]
        rows = [
            ["企业名称", enterprise],
            ["匹配到的实际名称", " / ".join(actual_names) or "—"],
            ["统计周期", period],
            ["投诉总量", f"{total} 件"],
            ["服务小区数", f"{cc} 个"],
            ["覆盖街道数", f"{sc} 个"],
            ["小区均投诉量", f"{avg} 件/小区"],
            ["Top 5 类别", " / ".join(f"{x['category']}({x['count']})" for x in categories)],
        ]
        ranking = []
        detail_headers = ["排名", "小区", "所属街道", "投诉量"]
        detail_rows = []
        for i, c in enumerate(communities, 1):
            detail_rows.append([i, c["community"], c["street"], c["count"]])

        _table = make_table(headers, rows)
        conn.close()
        return {
            "period": period,
            "enterprise": enterprise,
            "matched_names": actual_names,
            "total": total,
            "community_count": cc,
            "street_count": sc,
            "avg_per_community": avg,
            "top_categories": categories,
            "top_communities": communities,
            "ranking": [],
            "_table": _table,
            "_table_communities": make_table(detail_headers, detail_rows)
        }
    else:
        # 排行: 全年用enterprise_stats，月度从work_orders聚合
        if month is None:
            sql = (
                "SELECT property_company, total_count, community_count, yoy_count "
                "FROM enterprise_stats WHERE year=? ORDER BY total_count DESC LIMIT ?"
            )
            rows_db = cur.execute(sql, (year, top_n)).fetchall()
        else:
            sql = (
                "SELECT property_company, COUNT(*) total_count, "
                "       COUNT(DISTINCT community_name) community_count FROM work_orders"
                " WHERE year=? AND month=? AND property_company IS NOT NULL AND property_company != ''"
                " GROUP BY property_company ORDER BY total_count DESC LIMIT ?"
            )
            rows_db = cur.execute(sql, (year, month, top_n)).fetchall()

        ranking = []
        headers = ["排名", "物业企业", "投诉量", "服务小区数", "小区均投诉", "同比"]
        rows = []
        for i, r in enumerate(rows_db, 1):
            name = r[0] or ""
            total = int(r[1] or 0)
            cc = int(r[2] or 0)
            avg = round(total / cc, 2) if cc else 0
            if len(r) >= 4:
                yoy = int(r[3] or 0)
            else:
                yoy_sql = (
                    "SELECT COUNT(*) FROM work_orders"
                    " WHERE year=? AND month=? AND property_company=?"
                    if month else
                    "SELECT IFNULL(yoy_count, 0) FROM enterprise_stats WHERE year=? AND property_company=?"
                )
                yy = cur.execute(yoy_sql, (year - 1, month, name) if month else (year - 1, name)).fetchone()
                yoy = int(yy[0] or 0) if yy else 0
            ranking.append({
                "rank": i, "enterprise": name, "total": total,
                "community_count": cc, "avg_per_community": avg,
                "yoy_change": pct_change_str(total, yoy)
            })
            rows.append([i, name, total, cc, avg, pct_change_str(total, yoy)])
        conn.close()
        return {
            "period": period,
            "enterprise": None,
            "ranking": ranking,
            "_table": make_table(headers, rows)
        }
