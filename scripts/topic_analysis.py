import pandas as pd
import numpy as np
import jieba
import json
import os
from collections import Counter, defaultdict

DATA_DIR = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/热线数据"

# ─── 读取数据 ───
print("读取数据...")
df1 = pd.read_excel(os.path.join(DATA_DIR, "2024年市局14类.xlsx"), sheet_name="Sheet1")
df2 = pd.read_excel(os.path.join(DATA_DIR, "2025 年全年、2026年 1-6 月市局14类.xlsx"), sheet_name="Sheet1")
df3 = pd.read_excel(os.path.join(DATA_DIR, "2026 年7月市局14类.xlsx"), sheet_name="Sheet1")

# 标准化函数
def clean_df(df, year_col='年'):
    rename_map = {}
    for c in df.columns:
        if '工单编号' in c: rename_map[c] = 'order_id'
        elif '内容描述' in c: rename_map[c] = 'content'
        elif '小区名称' in c: rename_map[c] = 'community_name'
        elif c == '物业公司': rename_map[c] = 'property_company'
        elif c == '街道': rename_map[c] = 'street'
        elif c == '十四类': rename_map[c] = 'category_14'
        elif c == year_col: rename_map[c] = 'year'
        elif c == '月份': rename_map[c] = 'month'
        elif '受理时间' in c: rename_map[c] = 'accept_time'
    df = df.rename(columns=rename_map)

    # 日期处理
    if 'accept_time' in df.columns:
        if df['accept_time'].dtype == 'float64':
            df['accept_time'] = pd.to_datetime(df['accept_time'], errors='coerce', unit='D', origin='1899-12-30')
        else:
            df['accept_time'] = pd.to_datetime(df['accept_time'], errors='coerce')

    # 街道清洗
    df['street'] = df['street'].apply(
        lambda x: str(x).replace('街道','').replace('镇','').strip() if pd.notna(x) else '未知'
    )

    # 类别统一
    df['category_14'] = df['category_14'].replace({
        '群租问题': '群租管理', '业委会': '业主大会/业委会', '服务态度': '物业服务态度'
    })

    # 过滤非标准类别
    exclude = ['剔除三大类','剔除-商办楼宇','剔除-非物业管理区域','剔除-无效工单','无','房屋交易纠纷','其他']
    df = df[~df['category_14'].isin(exclude)]

    # 年份处理
    if 'year' not in df.columns:
        df['year'] = df['accept_time'].dt.year
    df['year'] = pd.to_numeric(df['year'], errors='coerce')

    # 月份处理
    if 'month' in df.columns:
        df['month'] = pd.to_numeric(df['month'], errors='coerce')

    return df

df1 = clean_df(df1)
df2 = clean_df(df2)
df3 = clean_df(df3)

cols = ['year','month','category_14','street','property_company','community_name','content','order_id']
df_all = pd.concat([df1[cols], df2[cols], df3[cols]], ignore_index=True)
print(f"总记录数: {len(df_all)}")

# ─── 5个专题 ───
topics = ['停车管理', '房屋维修', '邻里纠纷', '房屋违规使用', '业主大会/业委会']

# 停用词
stop_words = set(['的','了','在','是','我','有','和','就','不','人','都','一','上','也','很',
    '到','说','要','去','会','着','没','看','好','自己','这','那','与','为','对','把','被',
    '让','从','向','给','但','而','或','及','以','于','之','其','此','该','等','可','能',
    '需','应','将','已','正','还','又','再','们','个','中','里','下','后','前','时','地','得',
    '吧','呢','啊','吗','么','只','才','便','即','则','虽','因','由','所','使','现在','至今',
    '市民','反映','来电','求助','投诉','上述','相关','进行','已经','关于','由于','并且','另外',
    '一直没有','一直没有','目前','至今未','有关','通过','对于','根据','表示','认为','要求'])

def get_keywords(texts, top_n=15):
    all_words = []
    for text in texts:
        if pd.isna(text):
            continue
        words = jieba.lcut(str(text))
        words = [w for w in words if len(w) >= 2 and w not in stop_words]
        all_words.extend(words)
    return Counter(all_words).most_common(top_n)

results = {}

for topic in topics:
    print(f"\n{'='*60}")
    print(f"分析专题: {topic}")
    print(f"{'='*60}")

    df_topic = df_all[df_all['category_14'] == topic].copy()
    print(f"总记录数: {len(df_topic)}")

    # 年度统计
    yearly = df_topic.groupby('year').size()
    print(f"年度: {dict(yearly)}")

    # 同比
    y2024 = int(yearly.get(2024, 0))
    y2025 = int(yearly.get(2025, 0))
    y2026 = int(yearly.get(2026, 0))
    yoy_25 = round((y2025 - y2024) / y2024 * 100, 1) if y2024 > 0 else 0

    # 2026年1-7月 vs 2025年1-7月
    y2026_h1 = int(df_topic[df_topic['year'] == 2026].shape[0])
    y2025_h1 = int(df_topic[(df_topic['year'] == 2025) & (df_topic['month'] <= 7)].shape[0])
    yoy_26 = round((y2026_h1 - y2025_h1) / y2025_h1 * 100, 1) if y2025_h1 > 0 else 0

    # 月度趋势
    monthly = {}
    for y in [2024, 2025, 2026]:
        for m in range(1, 13):
            cnt = int(df_topic[(df_topic['year'] == y) & (df_topic['month'] == m)].shape[0])
            if cnt > 0:
                monthly[f"{y}-{m:02d}"] = cnt

    # 街道分布
    street_dist = df_topic.groupby('street').size().sort_values(ascending=False).head(13)
    street_2025 = df_topic[df_topic['year'] == 2025].groupby('street').size().sort_values(ascending=False)

    # 热点小区
    community_dist = df_topic.groupby('community_name').size().sort_values(ascending=False)
    community_dist = community_dist[community_dist.index != '无'].head(15)

    # 物业企业
    company_dist = df_topic.groupby('property_company').size().sort_values(ascending=False)
    company_dist = company_dist[company_dist.index != '无'].head(10)

    # 关键词
    keywords = get_keywords(df_topic['content'].tolist(), 15)

    # 月度趋势（按年对比）
    monthly_compare = {}
    for m in range(1, 13):
        monthly_compare[m] = {
            '2024': int(df_topic[(df_topic['year'] == 2024) & (df_topic['month'] == m)].shape[0]),
            '2025': int(df_topic[(df_topic['year'] == 2025) & (df_topic['month'] == m)].shape[0]),
            '2026': int(df_topic[(df_topic['year'] == 2026) & (df_topic['month'] == m)].shape[0]),
        }

    # 街道2025年对比
    street_yearly = {}
    for s in street_dist.index:
        street_yearly[s] = {
            '2024': int(df_topic[(df_topic['street'] == s) & (df_topic['year'] == 2024)].shape[0]),
            '2025': int(df_topic[(df_topic['street'] == s) & (df_topic['year'] == 2025)].shape[0]),
            '2026': int(df_topic[(df_topic['street'] == s) & (df_topic['year'] == 2026)].shape[0]),
        }

    # 热点小区详情
    community_yearly = {}
    for c in community_dist.index[:10]:
        community_yearly[c] = {
            'total': int(community_dist[c]),
            '2024': int(df_topic[(df_topic['community_name'] == c) & (df_topic['year'] == 2024)].shape[0]),
            '2025': int(df_topic[(df_topic['community_name'] == c) & (df_topic['year'] == 2025)].shape[0]),
            '2026': int(df_topic[(df_topic['community_name'] == c) & (df_topic['year'] == 2026)].shape[0]),
            'street': df_topic[df_topic['community_name'] == c]['street'].iloc[0] if len(df_topic[df_topic['community_name'] == c]) > 0 else '未知',
            'company': str(df_topic[df_topic['community_name'] == c]['property_company'].iloc[0])[:20] if len(df_topic[df_topic['community_name'] == c]) > 0 and pd.notna(df_topic[df_topic['community_name'] == c]['property_company'].iloc[0]) else '未知',
        }

    results[topic] = {
        'total': len(df_topic),
        'y2024': y2024, 'y2025': y2025, 'y2026_h1': y2026_h1, 'y2025_h1': y2025_h1,
        'yoy_2025': yoy_25, 'yoy_2026': yoy_26,
        'monthly_compare': monthly_compare,
        'street_dist': {s: int(street_dist[s]) for s in street_dist.index},
        'street_yearly': street_yearly,
        'community_top10': community_yearly,
        'company_top10': {c: int(company_dist[c]) for c in company_dist.index},
        'keywords': [{'word': w, 'count': c} for w, c in keywords],
    }

    print(f"  2024: {y2024}, 2025: {y2025} (同比{yoy_25:+.1f}%)")
    print(f"  2026年1-7月: {y2026_h1}, 2025年1-7月: {y2025_h1} (同比{yoy_26:+.1f}%)")
    print(f"  热点小区Top3: {list(community_dist.index[:3])}")
    print(f"  关键词Top5: {[w for w,c in keywords[:5]]}")

# ─── 输出JSON ───
output_path = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/scripts/topic_analysis.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n结果已保存: {output_path}")
