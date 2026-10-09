# -*- coding: utf-8 -*-
"""高风险小区预警评分模型

口径（2026-09-28 项目组决策后）
--------------------------------
· **参评范围**：仅《纳统小区 (2026 更新版).xls》名单内的小区；不在名单中的小区不参评。
  由 `nato_match` 统一做「热线小区名 → 纳统小区」映射（主名/别名/2026版曾用名精确匹配）。
· **统计单元**：按**纳统小区**聚合（别名、曾用名归并到同一小区），
  故 `--scope aggregate` 为默认；`--scope filter` 保留热线名粒度、只做名单过滤；
  `--scope all` 为改造前的旧口径（不限名单）。
· **投诉数据**：一律取**热线数据表**（市局 14 类原始表），不使用纳统档案里的派生投诉字段。
· **计分方式**：**100 分起扣**（反扣分制）——满分 100 分，五维按风险程度扣分，
  展示分 = 100 − 扣分合计，**得分越低风险越高**（红色 ≤30 / 橙色 31-45 / 黄色 46-60 /
  蓝色 61-75 / 绿色 >75）。分档与改造前的正向分阈值 ≥70/≥55/≥40/≥25 一一对应，
  故各级小区数（红 254 / 橙 386 / 黄 108 / 蓝 24）完全不变。

用法
----
    python3 scripts/risk_scoring.py                     # 纳统聚合 + 数据到 2026-07（原时间口径）
    python3 scripts/risk_scoring.py --with-aug          # 额外纳入 2026 年 8 月表
    python3 scripts/risk_scoring.py --scope filter      # 仅过滤名单、不聚合
    python3 scripts/risk_scoring.py --dry-run           # 只打印，不覆盖 json/xlsx
"""
import argparse
import os
import sys

import pandas as pd
import numpy as np
import json
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nato_match as NM  # noqa: E402
from company_alias import canon_series  # noqa: E402

DATA_DIR = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/热线数据"

_ap = argparse.ArgumentParser(add_help=True)
_ap.add_argument("--scope", choices=["aggregate", "filter", "all"], default="aggregate",
                 help="aggregate=按纳统小区聚合（默认）；filter=仅过滤名单；all=旧口径")
_ap.add_argument("--with-aug", action="store_true", help="额外纳入 2026 年 8 月市局14类表")
_ap.add_argument("--dry-run", action="store_true", help="只打印结果，不写 json/xlsx")
ARGS = _ap.parse_args()

print("=" * 60)
print("高风险小区预警评分模型")
print(f"  参评范围: {ARGS.scope}｜时间: 2026年1-{'8' if ARGS.with_aug else '7'}月")
print("=" * 60)

# ─── 读取数据 ───
df1 = pd.read_excel(os.path.join(DATA_DIR, "2024年市局14类.xlsx"), sheet_name="Sheet1")
df2 = pd.read_excel(os.path.join(DATA_DIR, "2025 年全年、2026年 1-6 月市局14类.xlsx"), sheet_name="Sheet1")
df3 = pd.read_excel(os.path.join(DATA_DIR, "2026 年7月市局14类.xlsx"), sheet_name="Sheet1")
_extra = []
if ARGS.with_aug:
    # 注意：2026 年 8 月表面为 .xlsx 实为 xls 换名，openpyxl 会报 BadZipFile，须用 xlrd 读
    _p8 = os.path.join(DATA_DIR, "2026 年8月市局14类.xlsx")
    try:
        df8 = pd.read_excel(_p8, sheet_name="Sheet1")
    except Exception:
        import xlrd
        _wb = xlrd.open_workbook(_p8)
        _sh = _wb.sheet_by_index(0)
        _hdr = [str(_sh.cell_value(0, c)).strip() for c in range(_sh.ncols)]
        _rows = [[_sh.cell_value(r, c) for c in range(_sh.ncols)] for r in range(1, _sh.nrows)]
        df8 = pd.DataFrame(_rows, columns=_hdr)
        # 编号列须归一化为字符串，避免 float 科学计数法
        for c in df8.columns:
            if "工单编号" in str(c):
                df8[c] = df8[c].map(lambda v: str(int(v)) if isinstance(v, float) and v == int(v) else str(v))
    df8["year"] = 2026
    _extra.append(df8)
    print(f"  已加载 2026 年 8 月表: {len(df8):,} 条")


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
    # 企业名归并（全站唯一口径源）：更名前后的两个名称合并为同一主体
    if 'property_company' in df.columns:
        df['property_company'] = canon_series(df['property_company'].astype(str))
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
_extra = [clean_df(e) for e in _extra]

cols = ['year','month','category_14','street','property_company','community_name','content','order_id']
df_all = pd.concat([df1[cols], df2[cols], df3[cols]] + [e[cols] for e in _extra], ignore_index=True)
df_all = df_all[df_all['community_name'].notna() & (df_all['community_name'] != '无') & (df_all['community_name'] != '')]
df_all['community_name'] = df_all['community_name'].astype(str).str.strip()
print(f"有效记录数: {len(df_all)}")
print(f"涉及小区数(热线名): {df_all['community_name'].nunique()}")

# ─── 参评范围：按《纳统小区 (2026 更新版)》收窄 ───
_st_map = df_all.groupby('community_name')['street'].agg(
    lambda s: s.mode().iloc[0] if len(s.mode()) else "").to_dict()
NATO_MAP = NM.build_map(sorted(_st_map), streets=_st_map)
NATO_STREET = dict(zip(NATO_MAP['nato_name'], NATO_MAP['nato_street']))

if ARGS.scope == "all":
    df_all['_unit'] = df_all['community_name']
    print("⚠️ scope=all：未按纳统名单收窄（旧口径）")
else:
    _ok = set(NATO_MAP.loc[NATO_MAP['matched'], 'hotline_name'])
    _n0 = len(df_all)
    _kept = df_all[df_all['community_name'].isin(_ok)].copy()
    if ARGS.scope == "aggregate":
        _kept = NM.aggregate_key(_kept, col='community_name', mp=NATO_MAP)
        _kept['_unit'] = _kept['nato_community']
    else:
        _kept['_unit'] = _kept['community_name']
    df_all = _kept
    print(f"参评范围收窄（{ARGS.scope}）：{_n0:,} → {len(df_all):,} 条"
          f"（剔除 {_n0-len(df_all):,} 条，{( _n0-len(df_all))/_n0*100:.1f}%）"
          f"｜统计单元 {df_all['_unit'].nunique()} 个")
    if df_all['_unit'].eq('').any():
        print("⚠️ 存在未归入纳统小区的记录，已丢弃")
        df_all = df_all[df_all['_unit'] != '']

# ─── 构建风险评分模型 ───
print("\n构建风险评分模型...")

community_stats = []

MONTH_MAX = 8 if ARGS.with_aug else 7

for community, group in df_all.groupby('_unit'):
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

    # 2026年1-MONTH_MAX月 vs 2025年同期
    g2025_h1 = g2025[g2025['month'] <= MONTH_MAX]
    g2026_h1 = g2026

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

    # 街道和物业（街道优先取纳统档案，避免别名造成同一小区街道不一）
    street = NATO_STREET.get(community) or (group['street'].iloc[0] if len(group) > 0 else '未知')
    street = str(street).replace('街道', '').replace('镇', '').strip() or '未知'
    company = group['property_company'].iloc[0] if len(group) > 0 else '未知'
    if pd.isna(company) or company == '无':
        company = '未知'

    # ─── 风险扣分（100 分起扣，扣得越多风险越高） ───
    # 各维度「扣分额」＝该维度的风险程度×权重；维度权重＝该维度最大扣分额。
    # 展示分 = 100 − 各维度扣分合计，故**得分越低风险越高**（避免「80 分是红色」的反直觉）。

    # 维度1: 投诉总量（最多扣 25 分）- 对数缩放
    ded_volume = min(25, np.log1p(total) / np.log1p(50) * 25)

    # 维度2: 增长率（最多扣 25 分）- 正增长扣分越多
    if growth_rate > 50:
        ded_growth = 25
    elif growth_rate > 20:
        ded_growth = 20
    elif growth_rate > 0:
        ded_growth = 15 + growth_rate / 20 * 5
    elif growth_rate > -20:
        ded_growth = 10
    elif growth_rate > -50:
        ded_growth = 5
    else:
        ded_growth = 0

    # 维度3: 重复投诉率（最多扣 20 分）
    ded_repeat = min(20, repeat_rate / 50 * 20)

    # 维度4: 类别集中度（最多扣 15 分）- 单一类别占比越高，风险越高
    ded_concentration = min(15, top_category_pct / 100 * 15)

    # 维度5: 月度波动度（最多扣 15 分）- 波动越大越不稳定
    ded_volatility = min(15, volatility / 100 * 15)

    # 扣分合计 与 展示分
    deduction = round(ded_volume + ded_growth + ded_repeat + ded_concentration + ded_volatility, 1)
    total_score = round(100 - deduction, 1)

    # 风险等级（按 100 分起扣后的剩余分判定：**分越低风险越高**）；
    # 分档与改造前的正向分阈值 ≥70/≥55/≥40/≥25 一一对应，故各级小区数完全不变。
    if total_score <= 30:
        risk_level = '红色'
    elif total_score <= 45:
        risk_level = '橙色'
    elif total_score <= 60:
        risk_level = '黄色'
    elif total_score <= 75:
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
        'ded_volume': round(ded_volume, 1),
        'ded_growth': round(ded_growth, 1),
        'ded_repeat': round(ded_repeat, 1),
        'ded_concentration': round(ded_concentration, 1),
        'ded_volatility': round(ded_volatility, 1),
        'deduction': deduction,
        'total_score': total_score,      # 100 − 扣分合计；越低越危险
        'risk_level': risk_level,
    })

# 按风险从高到低（＝展示分升序，分越低越危险）
community_stats.sort(key=lambda x: x['total_score'])

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
    'scope': {
        'unit': '纳统小区（《纳统小区 (2026 更新版).xls》）' if ARGS.scope != 'all' else '热线小区名（旧口径，未收窄）',
        'mode': ARGS.scope,
        'exclude_outside_nato': ARGS.scope != 'all',
        'data_source': '热线数据表（市局14类）',
        'period_2026': f"2026年1-{MONTH_MAX}月",
    },
    'model_description': {
        'principle': '100 分起扣：满分 100 分，各维度按风险程度扣分，'
                     '**得分越低代表风险越高**（红色预警为低分档）。',
        'dimensions': [
            {'name': '投诉总量', 'weight': '25分', 'desc': '对数缩放，投诉总量越大扣分越多'},
            {'name': '同比增长率', 'weight': '25分',
             'desc': f"2026年1-{MONTH_MAX}月 vs 2025年同期，增长越多扣分越多"},
            {'name': '重复投诉率', 'weight': '20分', 'desc': '同小区同类≥3次的占比，越高扣分越多'},
            {'name': '类别集中度', 'weight': '15分', 'desc': '主要问题类别占比越高扣分越多'},
            {'name': '月度波动度', 'weight': '15分', 'desc': '月度投诉量标准差/均值，波动越大扣分越多'},
        ],
        'risk_levels': [
            {'level': '红色', 'score': '≤30', 'action': '紧急处置'},
            {'level': '橙色', 'score': '31-45', 'action': '重点关注'},
            {'level': '黄色', 'score': '46-60', 'action': '常规关注'},
            {'level': '蓝色', 'score': '61-75', 'action': '一般跟踪'},
            {'level': '绿色', 'score': '>75', 'action': '正常'},
        ]
    }
}

if ARGS.dry_run:
    print("\n[dry-run] 未写入 json / xlsx")
else:
    output_path = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/scripts/risk_scores.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 同时导出Excel
    df_export = pd.DataFrame(community_stats)
    df_export.columns = ['小区名称', '街道', '物业公司', '投诉总量', '2024年', '2025年',
                         f'2026年1-{MONTH_MAX}月', f'2025年1-{MONTH_MAX}月',
                         '同比增长率%', '重复投诉率%', '类别数', '主要问题', '主要问题占比%', '月度波动度%',
                         '总量扣分', '增长扣分', '重复扣分', '集中度扣分', '波动度扣分', '扣分合计',
                         '风险得分', '风险等级']
    excel_path = "/Users/macbookpro/Desktop/8-24 徐汇课题一期/高风险小区预警清单.xlsx"
    df_export.to_excel(excel_path, index=False, sheet_name="风险评分清单")
    print(f"\nExcel已保存: {excel_path}")

print(f"\nTop20高风险小区（100 分起扣，分越低越危险）:")
for i, c in enumerate(community_stats[:20]):
    print(f"  {i+1:2d}. {c['community'][:15]:15s} | {c['street']:6s} | 风险得分{c['total_score']:5.1f}"
          f"（扣{c['deduction']:5.1f}） | {c['risk_level']} | 总量{c['total']:4d}"
          f" | 增长{c['growth_rate']:+6.1f}% | 主要问题:{c['top_category']}")

print(f"\n完成!")
