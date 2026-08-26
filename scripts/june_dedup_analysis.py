import pandas as pd
import numpy as np
import jieba
import json
import re
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict

DATA_DIR = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/热线数据"

# ─── 1. 读取数据 ───
print("=" * 60)
print("读取2025-2026年数据，筛选2026年6月")
print("=" * 60)

df = pd.read_excel(
    os.path.join(DATA_DIR, "2025 年全年、2026年 1-6 月市局14类.xlsx"),
    sheet_name="Sheet1"
)

# 标准化
df = df.rename(columns={
    '12345工单编号': 'order_id',
    '12345受理时间': 'accept_time',
    '12345内容描述': 'content',
    '小区名称': 'community_name',
    '物业公司': 'property_company',
    '街道': 'street',
    '十四类': 'category_14',
    '年': 'year',
    '月份': 'month',
})

# 筛选2026年6月
df_jun = df[(df['year'] == 2026) & (df['month'] == 6)].copy()
print(f"2026年6月工单总数: {len(df_jun)}")
print(f"涉及小区数: {df_jun['community_name'].nunique()}")
print(f"涉及类别数: {df_jun['category_14'].nunique()}")
print(f"涉及街道数: {df_jun['street'].nunique()}")

# 清洗街道名称
df_jun['street'] = df_jun['street'].apply(
    lambda x: str(x).replace('街道', '').replace('镇', '').strip() if pd.notna(x) else '未知'
)

# 统一类别名称
category_rename = {
    '群租问题': '群租管理',
    '业委会': '业主大会/业委会',
    '服务态度': '物业服务态度',
}
df_jun['category_14'] = df_jun['category_14'].replace(category_rename)

# ─── 2. 策略一：完全重复识别 ───
print("\n" + "=" * 60)
print("策略一：完全重复识别")
print("=" * 60)

exact_dup_groups = []
for community, group in df_jun.groupby('community_name'):
    if pd.isna(community) or community == '':
        continue
    # 同小区内内容完全相同
    dup = group[group['content'].duplicated(keep=False)]
    if len(dup) > 0:
        for content, sub in dup.groupby('content'):
            if len(sub) >= 2:
                exact_dup_groups.append({
                    'community': community,
                    'content': content[:100],
                    'order_ids': sub['order_id'].tolist(),
                    'count': len(sub),
                    'street': sub['street'].iloc[0],
                    'category': sub['category_14'].iloc[0],
                })

exact_dup_orders = set()
for g in exact_dup_groups:
    exact_dup_orders.update(g['order_ids'])
print(f"完全重复组数: {len(exact_dup_groups)}")
print(f"涉及工单数: {len(exact_dup_orders)}")

# ─── 3. 策略二：催办/重新交办识别 ───
print("\n" + "=" * 60)
print("策略二：催办/重新交办识别")
print("=" * 60)

keywords = ['催单', '重新交办', '反复', '相同事项']
urge_mask = df_jun['content'].apply(
    lambda x: any(kw in str(x) for kw in keywords) if pd.notna(x) else False
)
urge_orders = df_jun[urge_mask]
print(f"催办/重发工单数: {len(urge_orders)}")
urge_order_ids = set(urge_orders['order_id'].tolist())

# ─── 4. 策略三：同小区同类高频识别 ───
print("\n" + "=" * 60)
print("策略三：同小区同类高频识别（≥3次）")
print("=" * 60)

high_freq_groups = []
for (community, category), group in df_jun.groupby(['community_name', 'category_14']):
    if pd.isna(community) or community == '' or pd.isna(category):
        continue
    if len(group) >= 3:
        high_freq_groups.append({
            'community': community,
            'category': category,
            'count': len(group),
            'street': group['street'].iloc[0],
            'order_ids': group['order_id'].tolist(),
            'company': group['property_company'].iloc[0] if pd.notna(group['property_company'].iloc[0]) else '未知',
        })

high_freq_orders = set()
for g in high_freq_groups:
    high_freq_orders.update(g['order_ids'])

# 按次数降序
high_freq_groups.sort(key=lambda x: x['count'], reverse=True)
print(f"高频组数: {len(high_freq_groups)}")
print(f"涉及工单数: {len(high_freq_orders)}")
print(f"Top5高频组:")
for g in high_freq_groups[:5]:
    print(f"  {g['community']} - {g['category']}: {g['count']}次 ({g['street']})")

# ─── 5. 策略四：TF-IDF文本相似度识别 ───
print("\n" + "=" * 60)
print("策略四：TF-IDF文本相似度识别（≥0.6）")
print("=" * 60)

# 停用词
stop_words = set(['的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '上', '也', '很',
                  '到', '说', '要', '去', '会', '着', '没', '看', '好', '自己', '这', '那', '与', '为',
                  '对', '把', '被', '让', '从', '向', '给', '但', '而', '或', '及', '以', '于', '之',
                  '其', '此', '该', '等', '可', '能', '需', '应', '将', '已', '正', '还', '又', '再',
                  '们', '个', '中', '里', '下', '后', '前', '时', '地', '得', '着', '吧', '呢', '啊',
                  '吗', '么', '只', '才', '便', '即', '则', '虽', '因', '由', '所', '使'])

def tokenize(text):
    if pd.isna(text):
        return ''
    words = jieba.lcut(str(text))
    words = [w for w in words if len(w) >= 2 and w not in stop_words]
    return ' '.join(words)

similar_pairs = []
for community, group in df_jun.groupby('community_name'):
    if pd.isna(community) or community == '' or len(group) < 2:
        continue

    # 分词
    texts = group['content'].apply(tokenize).tolist()
    # 过滤空文本
    valid_indices = [i for i, t in enumerate(texts) if t.strip()]
    if len(valid_indices) < 2:
        continue

    valid_texts = [texts[i] for i in valid_indices]
    valid_orders = group['order_id'].tolist()
    valid_contents = group['content'].tolist()
    valid_categories = group['category_14'].tolist()

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
                        'content_1': str(valid_contents[valid_indices[i]])[:80],
                        'content_2': str(valid_contents[valid_indices[j]])[:80],
                        'similarity': round(sim_matrix[i][j], 3),
                        'category': valid_categories[valid_indices[i]],
                    })
    except Exception as e:
        pass

similar_order_ids = set()
for p in similar_pairs:
    similar_order_ids.add(p['order_id_1'])
    similar_order_ids.add(p['order_id_2'])

print(f"高度相似工单对数: {len(similar_pairs)}")
print(f"涉及工单数: {len(similar_order_ids)}")
print(f"涉及小区数: {len(set(p['community'] for p in similar_pairs))}")

# ─── 6. 合并去重 ───
print("\n" + "=" * 60)
print("合并去重")
print("=" * 60)

all_repeat_orders = exact_dup_orders | urge_order_ids | high_freq_orders | similar_order_ids
print(f"四策略合并后重复工单数: {len(all_repeat_orders)}")
print(f"重复投诉占比: {len(all_repeat_orders) / len(df_jun) * 100:.1f}%")

# ─── 7. 生成去重建议清单 ───
print("\n" + "=" * 60)
print("生成去重建议清单")
print("=" * 60)

# 为每条重复工单标注识别策略和处置建议
repeat_records = []
for _, row in df_jun.iterrows():
    oid = row['order_id']
    if oid not in all_repeat_orders:
        continue

    strategies = []
    if oid in exact_dup_orders:
        strategies.append('完全重复')
    if oid in urge_order_ids:
        strategies.append('催办/重发')
    if oid in high_freq_orders:
        strategies.append('同小区高频')
    if oid in similar_order_ids:
        strategies.append('文本相似')

    # 确定高频组信息
    freq_count = 1
    freq_group = None
    for g in high_freq_groups:
        if oid in g['order_ids']:
            freq_count = g['count']
            freq_group = g
            break

    # 确定相似度
    max_sim = 0
    for p in similar_pairs:
        if p['order_id_1'] == oid or p['order_id_2'] == oid:
            max_sim = max(max_sim, p['similarity'])

    # 处置建议
    if '催办/重发' in strategies:
        recommendation = '提升首次答复质量'
        priority = '高'
    elif freq_count >= 5:
        recommendation = '专项治理（一小区一方案）'
        priority = '高'
    elif freq_count >= 3:
        recommendation = '督办整改+跟踪闭环'
        priority = '中'
    elif '完全重复' in strategies:
        recommendation = '合并关闭重复工单'
        priority = '低'
    elif '文本相似' in strategies:
        recommendation = '核实是否同一问题，合并处理'
        priority = '中'
    else:
        recommendation = '关注跟踪'
        priority = '低'

    repeat_records.append({
        'order_id': str(oid),
        'community': str(row['community_name']) if pd.notna(row['community_name']) else '未知',
        'street': str(row['street']) if pd.notna(row['street']) else '未知',
        'category': str(row['category_14']) if pd.notna(row['category_14']) else '未知',
        'property_company': str(row['property_company'])[:20] if pd.notna(row['property_company']) else '未知',
        'content': str(row['content'])[:80] if pd.notna(row['content']) else '',
        'strategies': ' + '.join(strategies),
        'freq_count': freq_count,
        'max_similarity': round(max_sim, 2) if max_sim > 0 else None,
        'recommendation': recommendation,
        'priority': priority,
    })

# 按优先级和频次排序
priority_order = {'高': 0, '中': 1, '低': 2}
repeat_records.sort(key=lambda x: (priority_order[x['priority']], -x['freq_count']))

print(f"去重建议清单条目数: {len(repeat_records)}")

# 统计
priority_counts = defaultdict(int)
for r in repeat_records:
    priority_counts[r['priority']] += 1
print(f"优先级分布: 高={priority_counts['高']}, 中={priority_counts['中']}, 低={priority_counts['低']}")

strategy_counts = defaultdict(int)
for r in repeat_records:
    for s in r['strategies'].split(' + '):
        strategy_counts[s] += 1
print(f"策略分布: {dict(strategy_counts)}")

# ─── 8. 输出JSON ───
result = {
    'period': '2026年6月',
    'total_orders': len(df_jun),
    'repeat_orders': len(all_repeat_orders),
    'repeat_rate': round(len(all_repeat_orders) / len(df_jun) * 100, 1),
    'strategy_results': {
        'exact_duplicate': {'groups': len(exact_dup_groups), 'orders': len(exact_dup_orders)},
        'urge_redelivery': {'orders': len(urge_orders)},
        'high_frequency': {'groups': len(high_freq_groups), 'orders': len(high_freq_orders)},
        'text_similarity': {'pairs': len(similar_pairs), 'orders': len(similar_order_ids), 'communities': len(set(p['community'] for p in similar_pairs))},
    },
    'priority_distribution': dict(priority_counts),
    'top_high_freq_groups': [{
        'community': g['community'],
        'category': g['category'],
        'count': g['count'],
        'street': g['street'],
        'company': g['company'],
    } for g in high_freq_groups[:20]],
    'top_similar_pairs': [{
        'community': p['community'],
        'content_1': p['content_1'],
        'content_2': p['content_2'],
        'similarity': p['similarity'],
    } for p in sorted(similar_pairs, key=lambda x: -x['similarity'])[:10]],
    'category_distribution': {},
    'street_distribution': {},
    'recommendation_records': repeat_records,
}

# 类别分布
cat_dist = defaultdict(int)
for r in repeat_records:
    cat_dist[r['category']] += 1
result['category_distribution'] = dict(sorted(cat_dist.items(), key=lambda x: -x[1]))

# 街道分布
street_dist = defaultdict(int)
for r in repeat_records:
    street_dist[r['street']] += 1
result['street_distribution'] = dict(sorted(street_dist.items(), key=lambda x: -x[1]))

output_path = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/scripts/june_dedup_result.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\n结果已保存到: {output_path}")
print(f"\n=== 2026年6月去重分析汇总 ===")
print(f"工单总数: {len(df_jun)}")
print(f"重复工单: {len(all_repeat_orders)} ({len(all_repeat_orders)/len(df_jun)*100:.1f}%)")
print(f"完全重复: {len(exact_dup_orders)}条 ({len(exact_dup_groups)}组)")
print(f"催办/重发: {len(urge_orders)}条")
print(f"同小区高频: {len(high_freq_orders)}条 ({len(high_freq_groups)}组)")
print(f"文本相似: {len(similar_order_ids)}条 ({len(similar_pairs)}对)")
