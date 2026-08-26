import sqlite3
conn = sqlite3.connect('data/xuhui_complaints.db')
cur = conn.cursor()
print('=== 物业企业中含 徐房 / 城投 / 汇成 / 集团 ===')
for kw in ['徐房', '城投', '汇成', '集团']:
    rows = cur.execute(
        "SELECT property_company, COUNT(*) c FROM work_orders WHERE REPLACE(property_company,' ','') LIKE ? GROUP BY property_company ORDER BY c DESC LIMIT 10",
        (f'%{kw}%',)
    ).fetchall()
    print(f'--- 含 {kw} ({len(rows)}家) ---')
    for n, c in rows[:5]:
        print(f'  {repr(n)}: {c}件')
print()
print('=== 2026年物业企业Top20 ===')
rows = cur.execute("""SELECT property_company, COUNT(*) c, COUNT(DISTINCT community_name) cc
FROM work_orders WHERE year=2026 AND property_company!='' GROUP BY property_company ORDER BY c DESC LIMIT 20""").fetchall()
for n, c, cc in rows:
    print(f'  {n}: {c}件 / {cc}小区')
conn.close()
print('done')
