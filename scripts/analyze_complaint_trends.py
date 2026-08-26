import pandas as pd
import json
import os

DATA_DIR = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/热线数据"

# ─── 1. 读取三个Excel文件 ───

print("=" * 60)
print("步骤1: 读取Excel文件")
print("=" * 60)

# 2024年数据（27列）
df_2024 = pd.read_excel(os.path.join(DATA_DIR, "2024年市局14类.xlsx"), sheet_name="Sheet1")
print(f"2024年原始记录数: {len(df_2024)}")
print(f"2024年列数: {len(df_2024.columns)}")

# 2025年全年+2026年1-6月数据（23列）
df_2025_2026 = pd.read_excel(os.path.join(DATA_DIR, "2025 年全年、2026年 1-6 月市局14类.xlsx"), sheet_name="Sheet1")
print(f"2025-2026H1原始记录数: {len(df_2025_2026)}")

# 2026年7月数据（21列）
df_2026_07 = pd.read_excel(os.path.join(DATA_DIR, "2026 年7月市局14类.xlsx"), sheet_name="Sheet1")
print(f"2026年7月原始记录数: {len(df_2026_07)}")

# ─── 2. 统一字段名和清洗 ───

print("\n" + "=" * 60)
print("步骤2: 数据清洗和统一")
print("=" * 60)

# 标准化列名映射
def normalize_2024(df):
    df = df.rename(columns={
        '12345工单编号': 'order_id',
        '12345受理时间': 'accept_time',
        '12345工单来源': 'source',
        '12345诉求区域': 'district',
        '12345诉求地址': 'address',
        '12345工单类型': 'order_type',
        '12345内容描述': 'content',
        '主办单位': 'handler',
        '答复市民要点': 'reply',
        '年': 'year',
        '月份': 'month',
        '小区编号': 'community_id',
        '小区名称': 'community_name',
        '小区地址': 'community_addr',
        '物业公司': 'property_company',
        '街道': 'street',
        '行政区': 'district2',
        '十四类': 'category_14',
    })
    df['accept_time'] = pd.to_datetime(df['accept_time'], errors='coerce')
    df['year'] = df['year'].astype(int)
    df['month'] = df['month'].astype(int)
    return df

def normalize_2025(df):
    df = df.rename(columns={
        '12345工单编号': 'order_id',
        '12345受理时间': 'accept_time',
        '12345工单来源': 'source',
        '12345诉求区域': 'district',
        '12345诉求地址': 'address',
        '12345工单类型': 'order_type',
        '12345内容描述': 'content',
        '主办单位': 'handler',
        '答复市民要点': 'reply',
        '月份': 'month',
        '小区编号': 'community_id',
        '小区名称': 'community_name',
        '小区地址': 'community_addr',
        '物业公司': 'property_company',
        '街道': 'street',
        '行政区': 'district2',
        '十四类': 'category_14',
        '年': 'year',
    })
    # Excel序列号转日期
    df['accept_time'] = pd.to_datetime(df['accept_time'], errors='coerce', unit='D', origin='1899-12-30')
    df['year'] = df['year'].astype(int)
    df['month'] = df['month'].astype(int)
    return df

def normalize_2026_07(df):
    df = df.rename(columns={
        '工单编号': 'order_id',
        '受理时间': 'accept_time',
        '工单来源': 'source',
        '诉求区域': 'district',
        '诉求地址': 'address',
        '工单类型': 'order_type',
        '内容描述': 'content',
        '主办单位': 'handler',
        '答复市民要点': 'reply',
        '月份': 'month_str',
        '小区名称': 'community_name',
        '小区地址': 'community_addr',
        '物业公司': 'property_company',
        '街道': 'street',
        '行政区': 'district2',
        '十四类': 'category_14',
    })
    df['accept_time'] = pd.to_datetime(df['accept_time'], errors='coerce')
    df['year'] = 2026
    df['month'] = 7
    df['community_id'] = None
    return df

df_2024 = normalize_2024(df_2024)
df_2025_2026 = normalize_2025(df_2025_2026)
df_2026_07 = normalize_2026_07(df_2026_07)

# 统一街道名称（去掉"街道"后缀）
def clean_street(s):
    if pd.isna(s) or s == '无':
        return '未知'
    return str(s).replace('街道', '').replace('镇', '').strip()

for df in [df_2024, df_2025_2026, df_2026_07]:
    df['street'] = df['street'].apply(clean_street)

# 统一十四类名称
category_rename = {
    '群租问题': '群租管理',
    '业委会': '业主大会/业委会',
    '物业服务态度': '物业服务态度',
    '服务态度': '物业服务态度',
}
for df in [df_2024, df_2025_2026, df_2026_07]:
    df['category_14'] = df['category_14'].replace(category_rename)

# 过滤掉剔除类记录（2024年数据有）
exclude_categories = ['剔除三大类', '剔除-商办楼宇', '剔除-非物业管理区域', '剔除-无效工单', '无', '房屋交易纠纷']
df_2024 = df_2024[~df_2024['category_14'].isin(exclude_categories)]
print(f"2024年过滤剔除类后记录数: {len(df_2024)}")

# 合并所有数据
cols = ['year', 'month', 'category_14', 'street', 'property_company', 'community_name', 'order_type']
df_all = pd.concat([df_2024[cols], df_2025_2026[cols], df_2026_07[cols]], ignore_index=True)
print(f"合并后总记录数: {len(df_all)}")

# ─── 3. 计算月度趋势 ───

print("\n" + "=" * 60)
print("步骤3: 月度趋势计算")
print("=" * 60)

# 月度总量
monthly = df_all.groupby(['year', 'month']).size().reset_index(name='count')
monthly_pivot = monthly.pivot(index='month', columns='year', values='count')

print("\n月度工单量（14类）：")
print(monthly_pivot.to_string())

# 年度总量
yearly = df_all.groupby('year').size().reset_index(name='count')
print(f"\n年度总量：")
print(yearly.to_string())

# 同比计算
yoy_data = {}
for _, row in yearly.iterrows():
    year = int(row['year'])
    count = int(row['count'])
    prev = yearly[yearly['year'] == year - 1]
    if len(prev) > 0:
        prev_count = int(prev.iloc[0]['count'])
        yoy_pct = (count - prev_count) / prev_count * 100
        yoy_data[year] = {
            'count': count,
            'prev_count': prev_count,
            'yoy_pct': round(yoy_pct, 2)
        }
    else:
        yoy_data[year] = {'count': count, 'prev_count': None, 'yoy_pct': None}

print(f"\n同比数据：")
for y, d in yoy_data.items():
    if d['prev_count']:
        print(f"  {y}年: {d['count']}件 (去年{d['prev_count']}件, 同比{d['yoy_pct']:+.2f}%)")
    else:
        print(f"  {y}年: {d['count']}件 (无去年数据)")

# ─── 4. 月度同比对比 ───

print("\n" + "=" * 60)
print("步骤4: 月度同比对比")
print("=" * 60)

monthly_compare = []
for m in range(1, 13):
    row = {'month': m}
    for y in [2024, 2025, 2026]:
        val = monthly_pivot.loc[m, y] if y in monthly_pivot.columns and m in monthly_pivot.index else None
        if pd.notna(val):
            row[f'y{y}'] = int(val)
        else:
            row[f'y{y}'] = None
    
    # 同比计算
    if row.get('y2025') and row.get('y2024'):
        row['yoy_2025_vs_2024'] = round((row['y2025'] - row['y2024']) / row['y2024'] * 100, 2)
    else:
        row['yoy_2025_vs_2024'] = None
    
    if row.get('y2026') and row.get('y2025'):
        row['yoy_2026_vs_2025'] = round((row['y2026'] - row['y2025']) / row['y2025'] * 100, 2)
    else:
        row['yoy_2026_vs_2025'] = None
    
    monthly_compare.append(row)

print("月度同比对比：")
for r in monthly_compare:
    parts = [f"{r['month']:2d}月"]
    for y in [2024, 2025, 2026]:
        v = r.get(f'y{y}')
        parts.append(f"{y}:{v:>6}" if v else f"{y}:  N/A")
    if r.get('yoy_2025_vs_2024') is not None:
        parts.append(f"25vs24:{r['yoy_2025_vs_2024']:+.1f}%")
    if r.get('yoy_2026_vs_2025') is not None:
        parts.append(f"26vs25:{r['yoy_2026_vs_2025']:+.1f}%")
    print("  " + " | ".join(parts))

# ─── 5. 类别分析 ───

print("\n" + "=" * 60)
print("步骤5: 十四类投诉分析")
print("=" * 60)

# 年度类别统计
category_yearly = df_all.groupby(['year', 'category_14']).size().reset_index(name='count')
category_pivot = category_yearly.pivot(index='category_14', columns='year', values='count').fillna(0).astype(int)

# 按2025年量降序排列
category_pivot = category_pivot.sort_values(2025, ascending=False)

print("十四类投诉年度对比：")
print(category_pivot.to_string())

# 类别同比
category_yoy = []
for cat in category_pivot.index:
    row = {'category': cat}
    for y in [2024, 2025, 2026]:
        row[f'y{y}'] = int(category_pivot.loc[cat, y]) if y in category_pivot.columns else 0
    
    if row['y2024'] > 0 and row['y2025'] > 0:
        row['yoy_2025'] = round((row['y2025'] - row['y2024']) / row['y2024'] * 100, 2)
    else:
        row['yoy_2025'] = None
    
    # 2026年1-7月 vs 2025年1-7月
    cat_2026_h1 = df_all[(df_all['year'] == 2026) & (df_all['category_14'] == cat)].shape[0]
    cat_2025_h1 = df_all[(df_all['year'] == 2025) & (df_all['month'] <= 7) & (df_all['category_14'] == cat)].shape[0]
    row['y2026_h1'] = cat_2026_h1
    row['y2025_h1'] = cat_2025_h1
    if cat_2025_h1 > 0:
        row['yoy_2026_h1'] = round((cat_2026_h1 - cat_2025_h1) / cat_2025_h1 * 100, 2)
    else:
        row['yoy_2026_h1'] = None
    
    category_yoy.append(row)

print("\n类别同比：")
for r in category_yoy:
    yoy25 = f"{r['yoy_2025']:+.1f}%" if r['yoy_2025'] is not None else "N/A"
    yoy26 = f"{r['yoy_2026_h1']:+.1f}%" if r['yoy_2026_h1'] is not None else "N/A"
    print(f"  {r['category']:12s} 24:{r['y2024']:>5} 25:{r['y2025']:>5} 26H1:{r['y2026_h1']:>5} | 25vs24:{yoy25} 26H1vs25H1:{yoy26}")

# ─── 6. 街道分析 ───

print("\n" + "=" * 60)
print("步骤6: 街道分析")
print("=" * 60)

street_yearly = df_all.groupby(['year', 'street']).size().reset_index(name='count')
street_pivot = street_yearly.pivot(index='street', columns='year', values='count').fillna(0).astype(int)
street_pivot = street_pivot.sort_values(2025, ascending=False)

print("街道年度对比（按2025年降序）：")
print(street_pivot.to_string())

# ─── 7. 物业企业分析（Top10）───

print("\n" + "=" * 60)
print("步骤7: 物业企业Top10分析")
print("=" * 60)

company_yearly = df_all.groupby(['year', 'property_company']).size().reset_index(name='count')
company_pivot = company_yearly.pivot(index='property_company', columns='year', values='count').fillna(0).astype(int)
company_pivot = company_pivot.sort_values(2025, ascending=False).head(15)

print("物业企业Top15（按2025年降序）：")
print(company_pivot.to_string())

# ─── 8. 环比分析 ───

print("\n" + "=" * 60)
print("步骤8: 环比分析")
print("=" * 60)

mom_data = []
for y in [2024, 2025, 2026]:
    for m in range(1, 13):
        curr = df_all[(df_all['year'] == y) & (df_all['month'] == m)].shape[0]
        if curr == 0:
            continue
        # 上月
        if m == 1:
            prev = df_all[(df_all['year'] == y - 1) & (df_all['month'] == 12)].shape[0]
        else:
            prev = df_all[(df_all['year'] == y) & (df_all['month'] == m - 1)].shape[0]
        
        if prev > 0:
            mom_pct = round((curr - prev) / prev * 100, 2)
        else:
            mom_pct = None
        
        mom_data.append({
            'year': y, 'month': m, 'count': curr,
            'prev_count': prev if prev > 0 else None,
            'mom_pct': mom_pct
        })

print("环比数据：")
for r in mom_data:
    mom_str = f"{r['mom_pct']:+.1f}%" if r['mom_pct'] is not None else "N/A"
    print(f"  {r['year']}.{r['month']:2d}月: {r['count']:>5}件 (上月{r['prev_count']}, 环比{mom_str})")

# ─── 9. 汇总输出JSON ───

print("\n" + "=" * 60)
print("步骤9: 输出JSON结果")
print("=" * 60)

result = {
    'overview': {
        'total_2024': int(yearly[yearly['year'] == 2024]['count'].values[0]) if len(yearly[yearly['year'] == 2024]) > 0 else 0,
        'total_2025': int(yearly[yearly['year'] == 2025]['count'].values[0]) if len(yearly[yearly['year'] == 2025]) > 0 else 0,
        'total_2026_h1': int(df_all[df_all['year'] == 2026].shape[0]),
        'total_2025_h1': int(df_all[(df_all['year'] == 2025) & (df_all['month'] <= 7)].shape[0]),
        'yoy_2025_vs_2024': yoy_data.get(2025, {}).get('yoy_pct'),
        'yoy_2026_h1_vs_2025_h1': None,
    },
    'monthly': monthly_compare,
    'category': category_yoy,
    'street': street_pivot.reset_index().to_dict('records'),
    'company_top15': company_pivot.reset_index().to_dict('records'),
    'mom': mom_data,
}

# 计算2026 H1 vs 2025 H1同比
if result['overview']['total_2025_h1'] > 0:
    result['overview']['yoy_2026_h1_vs_2025_h1'] = round(
        (result['overview']['total_2026_h1'] - result['overview']['total_2025_h1']) / result['overview']['total_2025_h1'] * 100, 2
    )

output_path = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/scripts/complaint_trends.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\n结果已保存到: {output_path}")
print(f"\n=== 关键数据汇总 ===")
print(f"2024年总量(14类): {result['overview']['total_2024']}")
print(f"2025年总量(14类): {result['overview']['total_2025']}")
print(f"2025年同比: {result['overview']['yoy_2025_vs_2024']:+.2f}%")
print(f"2026年1-7月: {result['overview']['total_2026_h1']}")
print(f"2025年1-7月: {result['overview']['total_2025_h1']}")
print(f"2026年1-7月同比: {result['overview']['yoy_2026_h1_vs_2025_h1']:+.2f}%")
