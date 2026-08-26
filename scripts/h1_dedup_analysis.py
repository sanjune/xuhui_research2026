import pandas as pd
import numpy as np
import jieba
import json
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict

DATA_DIR = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/热线数据"
OUTPUT_DIR = "/Users/macbookpro/Desktop/8-24 徐汇课题一期"

# 停用词
stop_words = set(['的','了','在','是','我','有','和','就','不','人','都','一','上','也','很',
    '到','说','要','去','会','着','没','看','好','自己','这','那','与','为',
    '对','把','被','让','从','向','给','但','而','或','及','以','于','之',
    '其','此','该','等','可','能','需','应','将','已','正','还','又','再',
    '们','个','中','里','下','后','前','时','地','得','吧','呢','啊',
    '吗','么','只','才','便','即','则','虽','因','由','所','使'])

def tokenize(text):
    if pd.isna(text):
        return ''
    words = jieba.lcut(str(text))
    words = [w for w in words if len(w) >= 2 and w not in stop_words]
    return ' '.join(words)

def analyze_month(df_month, month_label):
    """对单月数据应用四重识别策略"""
    total = len(df_month)
    if total == 0:
        return None

    # 策略一：完全重复
    exact_dup_orders = set()
    exact_dup_groups = []
    for community, group in df_month.groupby('community_name'):
        if pd.isna(community) or community == '':
            continue
        dup = group[group['content'].duplicated(keep=False)]
        if len(dup) > 0:
            for content, sub in dup.groupby('content'):
                if len(sub) >= 2:
                    exact_dup_groups.append({'community': community, 'count': len(sub)})
                    exact_dup_orders.update(sub['order_id'].tolist())

    # 策略二：催办/重发
    keywords = ['催单', '重新交办', '反复', '相同事项']
    urge_mask = df_month['content'].apply(
        lambda x: any(kw in str(x) for kw in keywords) if pd.notna(x) else False
    )
    urge_orders = set(df_month[urge_mask]['order_id'].tolist())

    # 策略三：同小区同类高频（≥3次）
    high_freq_orders = set()
    high_freq_groups = []
    for (community, category), group in df_month.groupby(['community_name', 'category_14']):
        if pd.isna(community) or community == '' or pd.isna(category):
            continue
        if len(group) >= 3:
            high_freq_groups.append({
                'community': community,
                'category': category,
                'count': len(group),
                'street': group['street'].iloc[0],
                'company': str(group['property_company'].iloc[0])[:20] if pd.notna(group['property_company'].iloc[0]) else '未知',
                'order_ids': group['order_id'].tolist(),
            })
            high_freq_orders.update(group['order_id'].tolist())

    high_freq_groups.sort(key=lambda x: x['count'], reverse=True)

    # 策略四：TF-IDF文本相似度
    similar_pairs = []
    similar_order_ids = set()
    for community, group in df_month.groupby('community_name'):
        if pd.isna(community) or community == '' or len(group) < 2:
            continue
        texts = group['content'].apply(tokenize).tolist()
        valid_indices = [i for i, t in enumerate(texts) if t.strip()]
        if len(valid_indices) < 2:
            continue
        valid_texts = [texts[i] for i in valid_indices]
        valid_orders = group['order_id'].tolist()
        try:
            tfidf = TfidfVectorizer()
            tfidf_matrix = tfidf.fit_transform(valid_texts)
            sim_matrix = cosine_similarity(tfidf_matrix)
            for i in range(len(valid_indices)):
                for j in range(i + 1, len(valid_indices)):
                    if sim_matrix[i][j] >= 0.6:
                        similar_pairs.append({
                            'community': community,
                            'order_id_1': valid_orders[valid_indices[i]],
                            'order_id_2': valid_orders[valid_indices[j]],
                            'similarity': round(sim_matrix[i][j], 3),
                        })
                        similar_order_ids.add(valid_orders[valid_indices[i]])
                        similar_order_ids.add(valid_orders[valid_indices[j]])
        except:
            pass

    # 合并去重
    all_repeat = exact_dup_orders | urge_orders | high_freq_orders | similar_order_ids

    # 生成逐条建议
    records = []
    for _, row in df_month.iterrows():
        oid = row['order_id']
        if oid not in all_repeat:
            continue

        strategies = []
        if oid in exact_dup_orders: strategies.append('完全重复')
        if oid in urge_orders: strategies.append('催办/重发')
        if oid in high_freq_orders: strategies.append('同小区高频')
        if oid in similar_order_ids: strategies.append('文本相似')

        freq_count = 1
        for g in high_freq_groups:
            if oid in g['order_ids']:
                freq_count = g['count']
                break

        max_sim = 0
        for p in similar_pairs:
            if p['order_id_1'] == oid or p['order_id_2'] == oid:
                max_sim = max(max_sim, p['similarity'])

        if '催办/重发' in strategies:
            rec = '提升首次答复质量'
            pri = '高'
        elif freq_count >= 5:
            rec = '专项治理（一小区一方案）'
            pri = '高'
        elif freq_count >= 3:
            rec = '督办整改+跟踪闭环'
            pri = '中'
        elif '完全重复' in strategies:
            rec = '合并关闭重复工单'
            pri = '低'
        elif '文本相似' in strategies:
            rec = '核实是否同一问题，合并处理'
            pri = '中'
        else:
            rec = '关注跟踪'
            pri = '低'

        records.append({
            'month': month_label,
            'order_id': str(oid),
            'community': str(row['community_name']) if pd.notna(row['community_name']) else '未知',
            'street': str(row['street']) if pd.notna(row['street']) else '未知',
            'category': str(row['category_14']) if pd.notna(row['category_14']) else '未知',
            'property_company': str(row['property_company'])[:20] if pd.notna(row['property_company']) else '未知',
            'content': str(row['content'])[:60] if pd.notna(row['content']) else '',
            'strategies': ' + '.join(strategies),
            'freq_count': freq_count,
            'max_similarity': round(max_sim, 2) if max_sim > 0 else None,
            'recommendation': rec,
            'priority': pri,
        })

    priority_order = {'高': 0, '中': 1, '低': 2}
    records.sort(key=lambda x: (priority_order[x['priority']], -x['freq_count']))

    return {
        'month': month_label,
        'total_orders': total,
        'repeat_orders': len(all_repeat),
        'repeat_rate': round(len(all_repeat) / total * 100, 1) if total > 0 else 0,
        'strategy_results': {
            'exact': {'groups': len(exact_dup_groups), 'orders': len(exact_dup_orders)},
            'urge': len(urge_orders),
            'high_freq': {'groups': len(high_freq_groups), 'orders': len(high_freq_orders)},
            'similar': {'pairs': len(similar_pairs), 'orders': len(similar_order_ids)},
        },
        'priority_dist': {'高': sum(1 for r in records if r['priority'] == '高'),
                          '中': sum(1 for r in records if r['priority'] == '中'),
                          '低': sum(1 for r in records if r['priority'] == '低')},
        'top_groups': [{'community': g['community'], 'category': g['category'],
                         'count': g['count'], 'street': g['street'], 'company': g['company']}
                        for g in high_freq_groups[:10]],
        'records': records,
    }

# ─── 主流程 ───
print("=" * 60)
print("2026年1-6月投诉去重分析")
print("=" * 60)

df = pd.read_excel(os.path.join(DATA_DIR, "2025 年全年、2026年 1-6 月市局14类.xlsx"), sheet_name="Sheet1")
df = df.rename(columns={
    '12345工单编号': 'order_id', '12345内容描述': 'content',
    '小区名称': 'community_name', '物业公司': 'property_company',
    '街道': 'street', '十四类': 'category_14', '年': 'year', '月份': 'month',
})
df = df.rename(columns={'年': 'year'})

# 标准化
df['street'] = df['street'].apply(
    lambda x: str(x).replace('街道','').replace('镇','').strip() if pd.notna(x) else '未知'
)
df['category_14'] = df['category_14'].replace({
    '群租问题': '群租管理', '业委会': '业主大会/业委会', '服务态度': '物业服务态度'
})

# 筛选2026年1-6月
df_2026 = df[(df['year'] == 2026) & (df['month'].between(1, 6))].copy()
print(f"2026年1-6月总工单数: {len(df_2026)}")

all_results = []
all_records = []

for m in range(1, 7):
    month_label = f"2026年{m}月"
    df_m = df_2026[df_2026['month'] == m].copy()
    print(f"\n--- 分析{month_label} ({len(df_m)}条) ---")
    result = analyze_month(df_m, month_label)
    if result:
        all_results.append(result)
        all_records.extend(result['records'])
        print(f"  重复: {result['repeat_orders']}条 ({result['repeat_rate']}%)")
        print(f"  策略: 完全重复{result['strategy_results']['exact']['orders']}, "
              f"催办{result['strategy_results']['urge']}, "
              f"高频{result['strategy_results']['high_freq']['orders']}, "
              f"相似{result['strategy_results']['similar']['orders']}")
        print(f"  优先级: 高{result['priority_dist']['高']}, 中{result['priority_dist']['中']}, 低{result['priority_dist']['低']}")

# ─── 汇总统计 ───
total_orders = sum(r['total_orders'] for r in all_results)
total_repeats = sum(r['repeat_orders'] for r in all_results)
overall_rate = round(total_repeats / total_orders * 100, 1)

print(f"\n{'='*60}")
print(f"2026年1-6月汇总:")
print(f"  总工单: {total_orders}")
print(f"  重复工单: {total_repeats} ({overall_rate}%)")
print(f"  去重建议清单总条目: {len(all_records)}")

# ─── 导出Excel ───
print(f"\n导出Excel...")
df_export = pd.DataFrame(all_records)
df_export = df_export[['month','order_id','community','street','category','property_company',
                        'content','strategies','freq_count','max_similarity','recommendation','priority']]
df_export.columns = ['月份','工单编号','小区名称','街道','投诉类别','物业公司',
                      '内容描述(截选)','识别策略','重复频次','最大相似度','处置建议','优先级']
excel_path = os.path.join(OUTPUT_DIR, "2026年1-6月投诉去重建议清单.xlsx")
df_export.to_excel(excel_path, index=False, sheet_name="去重建议清单")
print(f"Excel已保存: {excel_path}")

# ─── 导出JSON汇总 ───
summary = {
    'total_orders': total_orders,
    'total_repeats': total_repeats,
    'overall_rate': overall_rate,
    'monthly': [{
        'month': r['month'],
        'total': r['total_orders'],
        'repeat': r['repeat_orders'],
        'rate': r['repeat_rate'],
        'exact': r['strategy_results']['exact']['orders'],
        'urge': r['strategy_results']['urge'],
        'high_freq': r['strategy_results']['high_freq']['orders'],
        'similar': r['strategy_results']['similar']['orders'],
        'high_freq_groups': r['strategy_results']['high_freq']['groups'],
        'similar_pairs': r['strategy_results']['similar']['pairs'],
        'priority_high': r['priority_dist']['高'],
        'priority_medium': r['priority_dist']['中'],
        'priority_low': r['priority_dist']['低'],
        'top_groups': r['top_groups'],
    } for r in all_results],
    'total_records': len(all_records),
}

json_path = os.path.join(OUTPUT_DIR, "scripts/h1_dedup_summary.json")
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f"JSON已保存: {json_path}")

# ─── 全期热点小区Top20 ───
community_freq = defaultdict(lambda: {'total_freq': 0, 'months': set(), 'category': '', 'street': '', 'company': ''})
for r in all_results:
    for g in r['top_groups']:
        key = (g['community'], g['category'])
        community_freq[key]['total_freq'] += g['count']
        community_freq[key]['months'].add(r['month'])
        community_freq[key]['category'] = g['category']
        community_freq[key]['street'] = g['street']
        community_freq[key]['company'] = g['company']

top_communities = sorted(community_freq.items(), key=lambda x: -x[1]['total_freq'])[:20]
print(f"\n全期热点小区Top5:")
for (comm, cat), info in top_communities[:5]:
    print(f"  {comm} - {cat}: 累计{info['total_freq']}次, 出现在{len(info['months'])}个月 ({info['street']})")
