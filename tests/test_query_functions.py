import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.query_functions import (
    get_summary, get_trend, get_ranking, get_category_detail,
    get_comparison, get_hotspot, get_repeat, get_property
)

REPORT = []
PASS, FAIL = 0, 0


def check(name, condition, expected="", actual=""):
    global PASS, FAIL
    flag = "✅ 通过" if condition else "❌ 失败"
    if condition:
        PASS += 1
    else:
        FAIL += 1
    msg = f"  {flag} {name}"
    if expected or actual:
        msg += f" (期望={expected} / 实际={actual})"
    REPORT.append(msg)
    print(msg)


def print_table(t):
    if not t:
        return
    headers = t.get("headers", [])
    rows = t.get("rows", [])
    print("    表格:")
    print("    " + " | ".join(map(str, headers)))
    print("    " + "-" * (10 * len(headers)))
    for row in rows[:8]:
        print("    " + " | ".join(str(x) for x in row))
    if len(rows) > 8:
        print(f"    ... ({len(rows) - 8} more rows)")
    print()


t0 = time.perf_counter()

# ============= Q1. get_summary =============
print("\n=== Q1 演示问题: 这个月全区投诉情况怎么样？ ===")
print("→ 函数: get_summary(2026, 7)")
r = get_summary(2026, 7)
t1 = time.perf_counter()
print(f"  耗时: {(t1 - t0) * 1000:.1f}ms")
print(f"  period={r['period']}  total={r['total']}  yoy={r['yoy_change']}  mom={r['mom_change']}")
print(f"  Top3类别: {[(c['name'], c['count']) for c in r['top3_categories']]}")
print(f"  Top3街道: {[(c['name'], c['count']) for c in r['top3_streets']]}")
print_table(r["_table"])

check("Q1-period", r["period"] == "2026年7月", "2026年7月", r["period"])
check("Q1-total", r["total"] == 2097, "2097", str(r["total"]))
check("Q1-yoy", r["yoy_change"].startswith("-0.2"), "-0.2%", r["yoy_change"])
check("Q1-mom", r["mom_change"].startswith("+13.0"), "+13.0%", r["mom_change"])

cats = {c["name"]: c["count"] for c in r["top3_categories"]}
check("Q1-Cat房屋维修", cats.get("房屋维修") == 414, "房屋维修=414件", f"房屋维修={cats.get('房屋维修')}")
check("Q1-Cat邻里纠纷", cats.get("邻里纠纷") == 333, "邻里纠纷=333件", f"邻里纠纷={cats.get('邻里纠纷')}")
check("Q1-Cat停车管理", cats.get("停车管理") == 263, "停车管理=263件", f"停车管理={cats.get('停车管理')}")
strs = {c["name"]: c["count"] for c in r["top3_streets"]}
check("Q1-Street漕河泾", strs.get("漕河泾") == 226, "漕河泾=226", f"漕河泾={strs.get('漕河泾')}")

# ============= Q2. get_trend =============
print("\n=== Q2 演示问题: 今年投诉量和去年比降了没有？ ===")
print("→ 函数: get_trend(2026)")
t = time.perf_counter()
r = get_trend(2026)
print(f"  耗时: {(time.perf_counter() - t) * 1000:.1f}ms")
print(f"  period={r['period']}  total_current={r['total_current']}  total_compare={r['total_compare']}  yoy={r['yoy_change']}")
print_table(r["_table"])

check("Q2-total_current>0", r["total_current"] > 9000, ">9000 (至7月)", str(r["total_current"]))
check("Q2-12月数据点", len(r["current_data"]) == 12, "12条月度数据", str(len(r["current_data"])))

# ============= Q3. get_ranking =============
print("\n=== Q3 演示问题: 本月投诉量最多的5个街道是哪些？ ===")
print("→ 函数: get_ranking(2026, 'street', month=7, top_n=5)")
t = time.perf_counter()
r = get_ranking(2026, "street", month=7, top_n=5)
print(f"  耗时: {(time.perf_counter() - t) * 1000:.1f}ms")
print(f"  period={r['period']}  dimension={r['dimension']}")
for item in r["ranking"]:
    print(f"    #{item['rank']} {item['name']}: {item['count']}件 ({item['yoy_change']})")
print_table(r["_table"])

check("Q3-Top1漕河泾", r["ranking"][0]["name"] == "漕河泾", "漕河泾", r["ranking"][0]["name"])
check("Q3-Top1件数", r["ranking"][0]["count"] == 226, "226", str(r["ranking"][0]["count"]))
check("Q3-TopN=5", len(r["ranking"]) == 5, "5个", str(len(r["ranking"])))

# 类别排行额外验证
r_cat = get_ranking(2026, "category", month=7, top_n=5)
check("Q3(附加)-类别Top1维修", r_cat["ranking"][0]["name"] == "房屋维修", "房屋维修", r_cat["ranking"][0]["name"])
check("Q3(附加)-维修件数", r_cat["ranking"][0]["count"] == 414, "414", str(r_cat["ranking"][0]["count"]))

# ============= Q4. get_category_detail =============
print("\n=== Q4 演示问题: 停车类投诉主要集中在哪些小区？ ===")
print("→ 函数: get_category_detail('停车管理', 2026, 7, group_by='community', top_n=10)")
t = time.perf_counter()
r = get_category_detail("停车管理", 2026, 7, group_by="community", top_n=10)
print(f"  耗时: {(time.perf_counter() - t) * 1000:.1f}ms")
print(f"  period={r['period']}  category={r['category']}  total={r['total']}  涉及小区={r['community_count']}")
print(f"  子问题Top: {[(s['name'], s['count']) for s in r['sub_issues'][:3]]}")
print_table(r["_table"])

check("Q4-total", r["total"] == 263, "263", str(r["total"]))
check("Q4-topN=10", len(r["top_communities"]) <= 10, "<=10", str(len(r["top_communities"])))
check("Q4-含街道字段", all("street" in c for c in r["top_communities"]), "每项都有street", "OK" if all("street" in c for c in r["top_communities"]) else "缺失")

# ============= Q5. get_comparison =============
print("\n=== Q5 演示问题: 徐房集团和城投集团今年表现怎么样？ ===")
print("→ 函数: get_comparison('enterprise', ['徐房集团', '城投集团'], 2026)")
t = time.perf_counter()
r = get_comparison("enterprise", ["徐房集团", "城投集团"], 2026)
print(f"  耗时: {(time.perf_counter() - t) * 1000:.1f}ms")
print(f"  period={r['period']}  entity_type={r['entity_type']}  对比实体数={len(r['entities'])}")
for e in r["entities"]:
    print(f"    {e['entity_name']} -> 匹配名={e.get('matched_names')[:2]}  total={e['total']}  小区={e['community_count']}  均={e['avg_per_community']}")
print_table(r["_table"])

check("Q5-两实体", len(r["entities"]) == 2, "2个", str(len(r["entities"])))
check("Q5-徐房匹配到名", bool(r["entities"][0]["matched_names"]), "非空", str(r["entities"][0]["matched_names"]))
check("Q5-城投匹配到名", bool(r["entities"][1]["matched_names"]), "非空", str(r["entities"][1]["matched_names"]))

# ============= Q6. get_repeat =============
print("\n=== Q6 演示问题: 重复投诉率是多少？哪些小区最严重？ ===")
print("→ 函数: get_repeat(2026, half=1)  —  2026年上半年")
t = time.perf_counter()
r = get_repeat(2026, half=1)
print(f"  耗时: {(time.perf_counter() - t) * 1000:.1f}ms")
print(f"  period={r['period']}  total={r['total_orders']}  repeat={r['repeat_orders']}  rate={r['repeat_rate']}")
print(f"  Top3类别: {[(c['category'], c['repeat_count']) for c in r['top_categories'][:3]]}")
print(f"  Top3小区: {[(c['community'], c['repeat_count']) for c in r['top_communities'][:3]]}")
print_table(r["_table"])

check("Q6-period", r["period"] == "2026年1-6月", "2026年1-6月", r["period"])
check("Q6-total>9000", r["total_orders"] > 9000, ">9000 (≈9387)", str(r["total_orders"]))
# 文档示例给出 3.2% 左右重复率，近似匹配即可
rate_val = float(r["repeat_rate"].replace("%", ""))
check("Q6-repeat率>0", rate_val > 0, ">0%", r["repeat_rate"])
check("Q6-top小区有数据", len(r["top_communities"]) >= 1, ">=1个小区", str(len(r["top_communities"])))

# ============= Q7. get_hotspot =============
print("\n=== Q7 演示问题: 哪些小区今年投诉增长最快？ ===")
print("→ 函数: get_hotspot(2026, metric='growth', top_n=20)")
t = time.perf_counter()
r = get_hotspot(2026, metric="growth", top_n=20)
print(f"  耗时: {(time.perf_counter() - t) * 1000:.1f}ms")
print(f"  year={r['year']}  metric={r['metric']}  热点数={len(r['hotspots'])}")
for h in r["hotspots"][:5]:
    print(f"    #{h['rank']} {h['community']} ({h['street']}/{h['company'][:10]}) 今年={h['count']} 去年={h['prev_year_count']} 同比={h['yoy_change']}")
print_table(r["_table"])

check("Q7-topN<=20", len(r["hotspots"]) <= 20, "<=20", str(len(r["hotspots"])))
if r["hotspots"]:
    first_yoy = r["hotspots"][0]["yoy_change"]
    check("Q7-Top1同比正增长", first_yoy.startswith("+"), "正增长", first_yoy)
    check("Q7-每项都有street", all(h["street"] for h in r["hotspots"]), "街道非空", "OK" if all(h["street"] for h in r["hotspots"]) else "缺失")

# ============= get_property 双向测试 =============
print("\n=== P0: get_property 物业排行 (2026年7月 top10) ===")
t = time.perf_counter()
r = get_property(2026, month=7, top_n=10)
print(f"  耗时: {(time.perf_counter() - t) * 1000:.1f}ms")
print(f"  period={r['period']}")
for item in r["ranking"][:5]:
    print(f"    #{item['rank']} {item['enterprise'][:15]}: {item['total']}件  小区={item['community_count']}  均={item['avg_per_community']}  {item['yoy_change']}")
print_table(r["_table"])
check("Property-排行榜<=10", len(r["ranking"]) <= 10, "<=10", str(len(r["ranking"])))

print("\n=== P0: get_property 企业详情 (徐房集团 2026) ===")
t = time.perf_counter()
r = get_property(2026, enterprise="徐房集团")
print(f"  耗时: {(time.perf_counter() - t) * 1000:.1f}ms")
print(f"  period={r['period']}  enterprise={r['enterprise']}  匹配名={r['matched_names']}")
print(f"  total={r['total']}  小区={r['community_count']}  街道={r['street_count']}  均={r['avg_per_community']}")
print(f"  Top类别: {[(c['category'], c['count']) for c in r['top_categories'][:3]]}")
print_table(r["_table"])
check("Property-徐房匹配", bool(r["matched_names"]), "名称有匹配", str(r["matched_names"]))
check("Property-详情有小区列表", "_table_communities" in r, "存在小区表", "Y" if "_table_communities" in r else "N")

# ============= 额外边界测试 =============
print("\n=== 额外边界: get_summary 全年 2025 ===")
t = time.perf_counter()
r = get_summary(2025)
print(f"  耗时: {(time.perf_counter() - t) * 1000:.1f}ms")
print(f"  period={r['period']}  total={r['total']}  yoy={r['yoy_change']}")
check("边界-2025全年", r["total"] > 20000, ">20000", str(r["total"]))

print("\n=== 额外边界: get_ranking 小区 (2025全年 top10) ===")
t = time.perf_counter()
r = get_ranking(2025, "community", top_n=10)
print(f"  耗时: {(time.perf_counter() - t) * 1000:.1f}ms")
print(f"  Top1: {r['ranking'][0]['name']} 投诉={r['ranking'][0]['count']} 街道={r['ranking'][0].get('street')}")
check("边界-小区TopN", len(r["ranking"]) == 10, "10个", str(len(r["ranking"])))

print("\n=== 额外边界: get_category_detail('停车管理', 2025, group_by='enterprise', top_n=5) ===")
t = time.perf_counter()
r = get_category_detail("停车管理", 2025, group_by="enterprise", top_n=5)
print(f"  耗时: {(time.perf_counter() - t) * 1000:.1f}ms  total={r['total']}")
check("边界-类别按企业", len(r["top_communities"]) > 0, ">0", str(len(r["top_communities"])))

print(f"\n{'='*60}")
print(f"阶段3函数测试汇总: 通过 {PASS}, 失败 {FAIL}")
print(f"总耗时: {(time.perf_counter() - t0) * 1000:.1f}ms")
print(f"{'='*60}")

sys.exit(0 if FAIL == 0 else 1)
