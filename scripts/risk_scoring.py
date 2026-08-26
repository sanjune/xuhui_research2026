import pandas as pd
import numpy as np
import json
import os
from collections import defaultdict
from datetime import datetime

DATA_DIR = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/热线数据"

print("=" * 60)
print("高风险小区预警评分模型")
print("=" * 60)

# ─── 读取数据 ───
df1 = pd.read_excel(os.path.join(DATA_DIR, "2024年市局14类.xlsx"), sheet_name="Sheet1")
df2 = pd.read_excel(os.path.join(DATA_DIR, "2025 年全年、2026年 1-6 月市局14类.xlsx"), sheet_name="Sheet1")
df3 = pd.read_excel(os.path.join(DATA_DIR, "2026 年7月市局14类.xlsx"), sheet_name="Sheet1")

def clean_df(df):
    rename_map = {}
    for c in df.columns:
        if '工单编号' in c: rename_map[c] = 'order_id'
        elif '内容描述' in c: rename_map[c] = 'content'
        elif '小区名称' in c: rename_map[c] = 'community_name'
        elif c == '物业公司': rename_map[c] = 'property_company'
        elif c == '街道': rename_map[c] = 'street'
        elif c == '十四类': rename_map[c] = 'category_14'
        elif c == '年': rename_map[c] = 'year'
        elif c == '月份': rename_map[c] = 'month'
    df = df.rename(columns=rename_map)
    df['street'] = df['street'].apply(lambda x: str(x).replace('街道','').replace('镇','').strip() if pd.notna(x) else '未知')
    df['category_14'] = df['category_14'].replace({'群租问题':'群租管理','业委会':'业主大会/业委会','服务态度':'物业服务态度'})
    exclude = ['剔除三大类','剔除-商办楼宇','剔除-非物业管理区域','剔除-无效工单','无','房屋交易纠纷','其他']
    df = df[~df['category_14'].isin(exclude)]

    # 处理year字段
    if 'year' not in df.columns:
        df['year'] = 2026
    df['year'] = pd.to_numeric(df['year'], errors='coerce')

    # 处理month字段
    if 'month' not in df.columns:
        for c in df.columns:
            if '受理时间' in c or c == 'accept_time':
                df['month'] = pd.to_datetime(df[c], errors='coerce').dt.month
                break
    if 'month' in df.columns:
        df['month'] = pd.to_numeric(df['month'], errors='coerce')

    return df

df1 = clean_df(df1)
df2 = clean_df(df2)
df3 = clean_df(df3)

cols = ['year','month','category_14','street','property_company','community_name','content','order_id']
df_all = pd.concat([df1[cols], df2[cols], df3[cols]], ignore_index=True)
df_all = df_all[df_all['community_name'].notna() & (df_all['community_name'] != '无') & (df_all['community_name'] != '')]
print(f"有效记录数: {len(df_all)}")
print(f"涉及小区数: {df_all['community_name'].nunique()}")

# ─── 构建风险评分模型 ───
print("\n构建风险评分模型...")

community_stats = []

for community, group in df_all.groupby('community_name'):
    if community in ['无', '', 'nan', None]:
        continue

    total = len(group)
    if total < 10:  # 过滤投诉量极少的小区
        continue

    g2024 = group[group['year'] == 2024]
    g2025 = group[group['year'] == 2025]
    g2026 = group[group['year'] == 2026]

    n2024 = len(g2024)
    n2025 = len(g2025)
    n2026 = len(g2026)

    # 2026年1-7月 vs 2025年1-7月
    g2025_h1 = g2025[g2025['month'] <= 7]
    g2026_h1 = g2026  # 2026年只有1-7月

    n2025_h1 = len(g2025_h1)
    n2026_h1 = len(g2026_h1)

    # 增长率（仅当基数≥5时计算，避免小样本失真）
    if n2025_h1 >= 5:
        growth_rate = (n2026_h1 - n2025_h1) / n2025_h1 * 100
    elif n2025_h1 > 0:
        growth_rate = 0  # 基数太小，不计算增长率
    else:
        growth_rate = 0

    # 重复投诉率（同小区同类≥3次的比例）
    repeat_count = 0
    for (cat), cat_group in group.groupby('category_14'):
        if len(cat_group) >= 3:
            repeat_count += len(cat_group) - 2  # 超过3次的部分算重复
    repeat_rate = repeat_count / total * 100 if total > 0 else 0

    # 类别多样性
    n_categories = group['category_14'].nunique()

    # 月度波动度（标准差/均值）
    monthly_counts = group.groupby(['year', 'month']).size()
    if len(monthly_counts) >= 3 and monthly_counts.mean() > 0:
        volatility = monthly_counts.std() / monthly_counts.mean() * 100
    else:
        volatility = 0

    # 主要问题
    top_category = group['category_14'].value_counts().index[0]
    top_category_count = group['category_14'].value_counts().iloc[0]
    top_category_pct = top_category_count / total * 100

    # 街道和物业
    street = group['street'].iloc[0] if len(group) > 0 else '未知'
    company = group['property_company'].iloc[0] if len(group) > 0 else '未知'
    if pd.isna(company) or company == '无':
        company = '未知'

    # ─── 风险评分（0-100分） ───
    # 维度1: 投诉总量（25分）- 对数缩放
    score_volume = min(25, np.log1p(total) / np.log1p(50) * 25)

    # 维度2: 增长率（25分）- 正增长=高风险
    if growth_rate > 50:
        score_growth = 25
    elif growth_rate > 20:
        score_growth = 20
    elif growth_rate > 0:
        score_growth = 15 + growth_rate / 20 * 5
    elif growth_rate > -20:
        score_growth = 10
    elif growth_rate > -50:
        score_growth = 5
    else:
        score_growth = 0

    # 维度3: 重复投诉率（20分）
    score_repeat = min(20, repeat_rate / 50 * 20)

    # 维度4: 类别集中度（15分）- 单一类别占比越高，风险越高
    score_concentration = min(15, top_category_pct / 100 * 15)

    # 维度5: 月度波动度（15分）- 波动越大越不稳定
    score_volatility = min(15, volatility / 100 * 15)

    # 总分
    total_score = score_volume + score_growth + score_repeat + score_concentration + score_volatility
    total_score = round(total_score, 1)

    # 风险等级
    if total_score >= 70:
        risk_level = '红色'
    elif total_score >= 55:
        risk_level = '橙色'
    elif total_score >= 40:
        risk_level = '黄色'
    elif total_score >= 25:
        risk_level = '蓝色'
    else:
        risk_level = '绿色'

    community_stats.append({
        'community': community,
        'street': street,
        'company': str(company)[:20],
        'total': total,
        'n2024': n2024,
        'n2025': n2025,
        'n2026_h1': n2026_h1,
        'n2025_h1': n2025_h1,
        'growth_rate': round(growth_rate, 1),
        'repeat_rate': round(repeat_rate, 1),
        'n_categories': n_categories,
        'top_category': top_category,
        'top_category_pct': round(top_category_pct, 1),
        'volatility': round(volatility, 1),
        'score_volume': round(score_volume, 1),
        'score_growth': round(score_growth, 1),
        'score_repeat': round(score_repeat, 1),
        'score_concentration': round(score_concentration, 1),
        'score_volatility': round(score_volatility, 1),
        'total_score': total_score,
        'risk_level': risk_level,
    })

# 按总分降序
community_stats.sort(key=lambda x: -x['total_score'])

print(f"\n评分完成，共 {len(community_stats)} 个小区参评")

# 统计风险等级分布
level_dist = defaultdict(int)
for c in community_stats:
    level_dist[c['risk_level']] += 1
print(f"风险等级分布:")
for level in ['红色', '橙色', '黄色', '蓝色', '绿色']:
    print(f"  {level}: {level_dist[level]}个")

# 街道分布
street_risk = defaultdict(lambda: {'红色': 0, '橙色': 0, '黄色': 0, '蓝色': 0, '绿色': 0, 'total': 0})
for c in community_stats:
    street_risk[c['street']][c['risk_level']] += 1
    street_risk[c['street']]['total'] += 1

# 输出JSON
result = {
    'total_communities': len(community_stats),
    'level_distribution': dict(level_dist),
    'street_distribution': {k: v for k, v in sorted(street_risk.items(), key=lambda x: -x[1]['total'])},
    'top50_risk': community_stats[:50],
    'all_communities': community_stats,
    'model_description': {
        'dimensions': [
            {'name': '投诉总量', 'weight': '25分', 'desc': '对数缩放，总量越大得分越高'},
            {'name': '同比增长率', 'weight': '25分', 'desc': '2026年1-7月 vs 2025年同期，正增长=高风险'},
            {'name': '重复投诉率', 'weight': '20分', 'desc': '同小区同类≥3次的占比'},
            {'name': '类别集中度', 'weight': '15分', 'desc': '主要问题类别占比越高风险越高'},
            {'name': '月度波动度', 'weight': '15分', 'desc': '月度投诉量标准差/均值，波动大=不稳定'},
        ],
        'risk_levels': [
            {'level': '红色', 'score': '≥60', 'action': '紧急处置'},
            {'level': '橙色', 'score': '45-59', 'action': '重点关注'},
            {'level': '黄色', 'score': '30-44', 'action': '常规关注'},
            {'level': '蓝色', 'score': '15-29', 'action': '一般跟踪'},
            {'level': '绿色', 'score': '<15', 'action': '正常'},
        ]
    }
}

output_path = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/scripts/risk_scores.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# 同时导出Excel
df_export = pd.DataFrame(community_stats)
df_export.columns = ['小区名称','街道','物业公司','投诉总量','2024年','2025年','2026年1-7月','2025年1-7月',
                      '同比增长率%','重复投诉率%','类别数','主要问题','主要问题占比%','月度波动度%',
                      '总量得分','增长得分','重复得分','集中度得分','波动度得分','总分','风险等级']
excel_path = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/高风险小区预警清单.xlsx"
df_export.to_excel(excel_path, index=False, sheet_name="风险评分清单")
print(f"\nExcel已保存: {excel_path}")

print(f"\nTop20高风险小区:")
for i, c in enumerate(community_stats[:20]):
    print(f"  {i+1:2d}. {c['community'][:15]:15s} | {c['street']:6s} | 总分{c['total_score']:5.1f} | {c['risk_level']} | 总量{c['total']:4d} | 增长{c['growth_rate']:+6.1f}% | 主要问题:{c['top_category']}")

print(f"\n完成!")
