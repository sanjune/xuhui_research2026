import pandas as pd
import numpy as np
import json
import os

DATA_DIR = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/热线数据"

print("=" * 60)
print("治理效果追踪分析")
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
    if 'year' not in df.columns: df['year'] = 2026
    df['year'] = pd.to_numeric(df['year'], errors='coerce')
    if 'month' not in df.columns:
        for c in df.columns:
            if '受理时间' in c: df['month'] = pd.to_datetime(df[c], errors='coerce').dt.month; break
    if 'month' in df.columns: df['month'] = pd.to_numeric(df['month'], errors='coerce')
    return df

df1, df2, df3 = clean_df(df1), clean_df(df2), clean_df(df3)
cols = ['year','month','category_14','street','property_company','community_name','content']
df_all = pd.concat([df1[cols], df2[cols], df3[cols]], ignore_index=True)
df_all = df_all[df_all['community_name'].notna() & (df_all['community_name'] != '无') & (df_all['community_name'] != '')]

print(f"有效记录: {len(df_all)}")

# ─── 1. 治理效果追踪：小区层面 ───
print("\n" + "=" * 60)
print("1. 小区治理效果追踪")
print("=" * 60)

# 对每个小区，按类别追踪2024→2025→2026的变化
tracking = []

for community, group in df_all.groupby('community_name'):
    if community in ['无', '', 'nan']: continue
    n_total = len(group)
    if n_total < 15: continue  # 只看投诉量≥15的小区

    g2024 = group[group['year'] == 2024]
    g2025 = group[group['year'] == 2025]
    g2026 = group[group['year'] == 2026]

    n2024 = len(g2024)
    n2025 = len(g2025)
    n2026_h1 = len(g2026)

    # 2026年1-7月 vs 2025年1-7月
    g2025_h1 = g2025[g2025['month'] <= 7] if 'month' in g2025.columns else g2025
    n2025_h1 = len(g2025_h1)

    if n2024 < 5: continue  # 2024年至少5条才有分析价值

    # 治理效果：2025年vs2024年的变化率
    if n2024 > 0:
        improvement_2025 = (n2024 - n2025) / n2024 * 100
    else:
        improvement_2025 = 0

    # 2026年趋势
    if n2025_h1 > 0:
        improvement_2026 = (n2025_h1 - n2026_h1) / n2025_h1 * 100
    else:
        improvement_2026 = 0

    street = group['street'].iloc[0]
    company = str(group['property_company'].iloc[0])[:20] if pd.notna(group['property_company'].iloc[0]) else '未知'

    # 主要问题
    top_cat = group['category_14'].value_counts().index[0]
    top_cat_2024 = g2024['category_14'].value_counts().index[0] if len(g2024) > 0 else top_cat

    # 分类治理效果
    cat_tracking = {}
    for cat in group['category_14'].unique():
        c2024 = len(g2024[g2024['category_14'] == cat])
        c2025 = len(g2025[g2025['category_14'] == cat])
        c2026 = len(g2026[g2026['category_14'] == cat])
        if c2024 >= 3:
            cat_tracking[cat] = {'2024': c2024, '2025': c2025, '2026': c2026}

    tracking.append({
        'community': community,
        'street': street,
        'company': company,
        'total': n_total,
        'n2024': n2024,
        'n2025': n2025,
        'n2025_h1': n2025_h1,
        'n2026_h1': n2026_h1,
        'improvement_2025': round(improvement_2025, 1),  # 正数=改善
        'improvement_2026': round(improvement_2026, 1),  # 正数=继续改善
        'top_category': top_cat,
        'cat_tracking': cat_tracking,
    })

# ─── 2. 成功案例：改善幅度最大的Top20 ───
print("\n" + "=" * 60)
print("2. 治理成功案例Top20")
print("=" * 60)

success_cases = sorted([t for t in tracking if t['n2024'] >= 10 and t['improvement_2025'] > 0],
                       key=lambda x: -x['improvement_2025'])

print(f"改善案例数: {len(success_cases)}")
print(f"\nTop20成功案例:")
for i, t in enumerate(success_cases[:20]):
    status = "持续改善" if t['improvement_2026'] > 0 else "出现反弹"
    print(f"  {i+1:2d}. {t['community'][:15]:15s} | {t['street']:6s} | {t['n2024']:3d}→{t['n2025']:3d}→{t['n2026_h1']:3d} | 改善{t['improvement_2025']:+.1f}% | {t['top_category']} | {status}")

# ─── 3. 反弹案例：2025年改善但2026年反弹 ───
print("\n" + "=" * 60)
print("3. 治理反弹案例（2025改善但2026恶化）")
print("=" * 60)

rebound_cases = [t for t in tracking if t['improvement_2025'] > 20 and t['improvement_2026'] < -10 and t['n2025_h1'] >= 5]
rebound_cases.sort(key=lambda x: x['improvement_2026'])

print(f"反弹案例数: {len(rebound_cases)}")
print(f"\nTop10反弹案例:")
for i, t in enumerate(rebound_cases[:10]):
    print(f"  {i+1:2d}. {t['community'][:15]:15s} | {t['street']:6s} | 2025改善{t['improvement_2025']:+.1f}% → 2026反弹{t['improvement_2026']:+.1f}% | {t['top_category']}")

# ─── 4. 恶化案例：投诉持续增长 ───
print("\n" + "=" * 60)
print("4. 治理失效/未治理案例Top10")
print("=" * 60)

worsening = [t for t in tracking if t['improvement_2025'] < -20 and t['n2024'] >= 5]
worsening.sort(key=lambda x: x['improvement_2025'])

print(f"恶化案例数: {len(worsening)}")
for i, t in enumerate(worsening[:10]):
    print(f"  {i+1:2d}. {t['community'][:15]:15s} | {t['street']:6s} | {t['n2024']:3d}→{t['n2025']:3d}→{t['n2026_h1']:3d} | {t['improvement_2025']:+.1f}% | {t['top_category']}")

# ─── 5. 按类别统计治理效果 ───
print("\n" + "=" * 60)
print("5. 十四类治理效果统计")
print("=" * 60)

category_effects = {}
for cat in df_all['category_14'].unique():
    g = df_all[df_all['category_14'] == cat]
    c2024 = len(g[g['year'] == 2024])
    c2025 = len(g[g['year'] == 2025])
    g2025_h1 = g[(g['year'] == 2025) & (g['month'] <= 7)]
    g2026 = g[g['year'] == 2026]
    c2025_h1 = len(g2025_h1)
    c2026_h1 = len(g2026)

    effect_2025 = (c2024 - c2025) / c2024 * 100 if c2024 > 0 else 0
    effect_2026 = (c2025_h1 - c2026_h1) / c2025_h1 * 100 if c2025_h1 > 0 else 0

    category_effects[cat] = {
        '2024': c2024, '2025': c2025, '2025_h1': c2025_h1, '2026_h1': c2026_h1,
        'effect_2025': round(effect_2025, 1),
        'effect_2026': round(effect_2026, 1),
    }
    print(f"  {cat:12s}: 2024={c2024:5d} → 2025={c2025:5d}(改善{effect_2025:+.1f}%) → 2026H1={c2026_h1:4d}({'持续改善' if effect_2026 > 0 else '需关注'})")

# ─── 6. 按街道统计治理效果 ───
print("\n" + "=" * 60)
print("6. 街道治理效果统计")
print("=" * 60)

street_effects = {}
for street in df_all['street'].unique():
    if street in ['未知', '无']: continue
    g = df_all[df_all['street'] == street]
    c2024 = len(g[g['year'] == 2024])
    c2025 = len(g[g['year'] == 2025])
    g2025_h1 = g[(g['year'] == 2025) & (g['month'] <= 7)]
    g2026 = g[g['year'] == 2026]
    c2025_h1 = len(g2025_h1)
    c2026_h1 = len(g2026)

    effect_2025 = (c2024 - c2025) / c2024 * 100 if c2024 > 0 else 0
    effect_2026 = (c2025_h1 - c2026_h1) / c2025_h1 * 100 if c2025_h1 > 0 else 0

    street_effects[street] = {
        '2024': c2024, '2025': c2025, '2025_h1': c2025_h1, '2026_h1': c2026_h1,
        'effect_2025': round(effect_2025, 1),
        'effect_2026': round(effect_2026, 1),
    }

for s in sorted(street_effects.keys(), key=lambda x: -street_effects[x]['effect_2025']):
    e = street_effects[s]
    print(f"  {s:6s}: 2024={e['2024']:4d} → 2025={e['2025']:4d}({e['effect_2025']:+.1f}%) → 2026H1={e['2026_h1']:4d}({e['effect_2026']:+.1f}%)")

# ─── 7. 治理闭环模型 ───
print("\n" + "=" * 60)
print("7. 治理闭环统计")
print("=" * 60)

total_success = len([t for t in tracking if t['improvement_2025'] > 30])
total_rebound = len(rebound_cases)
total_worsening = len(worsening)
total_stable = len([t for t in tracking if abs(t['improvement_2025']) <= 10])
total_tracking = len(tracking)

print(f"追踪小区总数: {total_tracking}")
print(f"显著改善(>30%): {total_success}个 ({total_success/total_tracking*100:.1f}%)")
print(f"反弹(改善→恶化): {total_rebound}个 ({total_rebound/total_tracking*100:.1f}%)")
print(f"持续恶化(<-20%): {total_worsening}个 ({total_worsening/total_tracking*100:.1f}%)")
print(f"基本稳定(±10%): {total_stable}个 ({total_stable/total_tracking*100:.1f}%)")

# ─── 8. 输出JSON ───
result = {
    'total_tracking': total_tracking,
    'success_count': total_success,
    'rebound_count': total_rebound,
    'worsening_count': total_worsening,
    'stable_count': total_stable,
    'success_top20': [{
        'community': t['community'],
        'street': t['street'],
        'company': t['company'],
        'n2024': t['n2024'],
        'n2025': t['n2025'],
        'n2026_h1': t['n2026_h1'],
        'improvement_2025': t['improvement_2025'],
        'improvement_2026': t['improvement_2026'],
        'top_category': t['top_category'],
        'status': '持续改善' if t['improvement_2026'] > 0 else ('出现反弹' if t['improvement_2026'] < -10 else '基本稳定'),
    } for t in success_cases[:20]],
    'rebound_top10': [{
        'community': t['community'],
        'street': t['street'],
        'n2024': t['n2024'],
        'n2025': t['n2025'],
        'n2026_h1': t['n2026_h1'],
        'improvement_2025': t['improvement_2025'],
        'improvement_2026': t['improvement_2026'],
        'top_category': t['top_category'],
    } for t in rebound_cases[:10]],
    'worsening_top10': [{
        'community': t['community'],
        'street': t['street'],
        'n2024': t['n2024'],
        'n2025': t['n2025'],
        'n2026_h1': t['n2026_h1'],
        'improvement_2025': t['improvement_2025'],
        'top_category': t['top_category'],
    } for t in worsening[:10]],
    'category_effects': category_effects,
    'street_effects': street_effects,
}

output_path = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/scripts/governance_tracking.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\n结果已保存: {output_path}")
