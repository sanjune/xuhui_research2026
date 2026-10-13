#!/usr/bin/env python3
"""
seed_daily_reports.py — 从 热线日报数据/*.xlsx 提取结构化数据，输出 JSON 供导入 cloud-service DB。

输出：online_upload_app/data/seed_YYYY-MM-DD.json（每日期一份）
结构：summary 字段 + report_data JSONB（streetRows / categoryStats / focusStreets）
逻辑：与 app.py:_generate_one() 完全一致，仅输出 JSON 而非 HTML。
"""
import os, sys, json, re
import pandas as pd
from datetime import datetime

# PII 脱敏（与 app.py:mask_pii / _clean_prob 一致）
RE_PHONE = re.compile(r'1[3-9]\d{9}')
RE_IDCARD = re.compile(r'\d{17}[\dXx]')
RE_EMAIL = re.compile(r'[\w.-]+@[\w.-]+\.\w+')

def mask_pii(text):
    text = RE_PHONE.sub('[手机]', str(text))
    text = RE_IDCARD.sub('[证件]', text)
    text = RE_EMAIL.sub('[邮箱]', text)
    return text

def _clean_prob(prob):
    prob = str(prob or '').strip()
    prob = re.sub(r'\s+', ' ', prob)
    prob = mask_pii(prob)
    if len(prob) > 60:
        prob = prob[:60] + '…'
    return prob or '—'

STREET_ORDER = ['枫林路街道', '斜土路街道', '漕河泾街道', '天平路街道', '虹梅路街道',
                '徐家汇街道', '康健新村街道', '田林街道', '长桥街道', '龙华街道',
                '华泾镇', '湖南路街道', '凌云路街道', '__未匹配__']

WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
WEEKDAYS_SHORT = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def extract_for_date(df, data_date, src_name):
    """对单个日期的 df 提取 summary + report_data，与 _generate_one 逻辑一致"""
    total = len(df)
    date_cn = f"{data_date.year}年{data_date.month}月{data_date.day}日"
    date_weekday = WEEKDAYS[data_date.weekday()]
    date_slug = data_date.isoformat()

    # 街镇汇总
    df['street'] = df['s30_str_name'].fillna('__未匹配__')
    df.loc[df['street'].isin(['无', '/']), 'street'] = '__未匹配__'

    rows = []
    for st in STREET_ORDER:
        sub = df[df['street'] == st]
        if len(sub) == 0:
            continue
        n = len(sub)
        sub_typed = sub['problemtyped'].fillna('未分类').value_counts().head(3)
        main_cat = '、'.join(f'{k} {v}' for k, v in sub_typed.items()) if n else '—'
        rep = int((sub['is_repeat'] == '是').sum())
        rep_rate = round(rep / n * 100, 1) if n else 0
        label = '待关联街道' if st == '__未匹配__' else st
        rows.append({'street': label, 'n': n, 'mainCat': main_cat, 'rep': rep, 'repRate': rep_rate})

    rows.sort(key=lambda r: r['n'], reverse=True)

    # 最细一级分类全量统计
    df['_typed'] = df['problemtyped'].fillna('未分类')
    typed_full = []
    for k, v in df['_typed'].value_counts().items():
        n_st = df.loc[(df['_typed'] == k) & (df['street'] != '__未匹配__'), 'street'].nunique()
        typed_full.append({'name': k, 'count': int(v), 'pct': round(v / total * 100, 1), 'streets': int(n_st)})

    src_vc = df['hotlinesource'].fillna('未知').value_counts()
    type_vc = df['hotlinetype'].fillna('未标注').value_counts()
    pb_vc = df['problemtypeb'].fillna('未分类').value_counts()

    rep_total = int((df['is_repeat'] == '是').sum())
    rep_rate_total = round(rep_total / total * 100, 1)

    matched = sum(r['n'] for r in rows if r['street'] != '待关联街道')
    unmatched = sum(r['n'] for r in rows if r['street'] == '待关联街道')

    focus = [r for r in rows if (r['n'] >= 6 or r['repRate'] >= 40) and r['street'] != '待关联街道']

    # 重点街镇重复案件明细
    focus_streets = []
    for r in focus:
        st_name = r['street']
        # 注意：rows 里的 street 已是 label（'待关联街道'），但原 df 里是 '__未匹配__'
        st_key = '__未匹配__' if st_name == '待关联街道' else st_name
        rep_df = df[(df['street'] == st_key) & (df['is_repeat'] == '是')]
        repeat_cases = []
        for _, row in rep_df.iterrows():
            addr = mask_pii(str(row.get('appealaddr', '') or '').strip()) or '—'
            typed = str(row.get('problemtyped', '') or '').strip() or '—'
            prob = _clean_prob(row.get('problem', ''))
            repeat_cases.append({'addr': addr, 'typed': typed, 'prob': prob})
        focus_streets.append({
            'street': st_name,
            'n': r['n'],
            'mainCat': r['mainCat'],
            'rep': r['rep'],
            'repRate': r['repRate'],
            'repeatCases': repeat_cases
        })

    main_cat_list = [f'{k} {v}' for k, v in df['_typed'].value_counts().head(3).items()]

    summary = {
        'report_date': date_slug,
        'weekday': WEEKDAYS_SHORT[data_date.weekday()],
        'total': total,
        'matched': matched,
        'unmatched': unmatched,
        'rep': rep_total,
        'rep_rate': rep_rate_total,
        'streets': sum(1 for r in rows if r['street'] != '待关联街道'),
        'main_cat': main_cat_list,
    }

    report_data = {
        'dateCn': date_cn,
        'weekdayFull': date_weekday,
        'srcName': src_name,
        'generatedAt': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'streetRows': rows,
        'categoryStats': {
            'typed': typed_full,
            'source': [{'name': k, 'count': int(v)} for k, v in src_vc.items()],
            'type': [{'name': k, 'count': int(v)} for k, v in type_vc.items()],
            'problemTypeB': [{'name': k, 'count': int(v)} for k, v in pb_vc.items()],
        },
        'focusStreets': focus_streets,
    }

    # PII 断言：对 report_data 全文做正则检查
    raw = json.dumps(report_data, ensure_ascii=False)
    assert not RE_PHONE.search(raw), f'PII 断言失败：手机号残留 ({date_slug})'
    assert not RE_IDCARD.search(raw), f'PII 断言失败：证件号残留 ({date_slug})'
    assert not RE_EMAIL.search(raw), f'PII 断言失败：邮箱残留 ({date_slug})'

    return summary, report_data


def main():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '热线日报数据')
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'online_upload_app', 'data')
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    xlsx_files = sorted([f for f in os.listdir(data_dir) if f.endswith('.xlsx') and not f.startswith('_') and not f.startswith('~')])
    if not xlsx_files:
        print('未找到 xlsx 文件', file=sys.stderr)
        sys.exit(1)

    all_records = []
    for fname in xlsx_files:
        fpath = os.path.join(data_dir, fname)
        df = pd.read_excel(fpath)
        _data_dates = pd.to_datetime(df['processtime']).dt.date
        unique_dates = sorted(_data_dates.unique())
        print(f'{fname}: {len(df)} 行, {len(unique_dates)} 个日期')
        for d in unique_dates:
            df_date = df[_data_dates == d].copy()
            summary, report_data = extract_for_date(df_date, d, fname)
            record = {**summary, 'report_data': report_data}
            out_path = os.path.join(out_dir, f'seed_{d.isoformat()}.json')
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            all_records.append(record)
            print(f'  → {d.isoformat()}: {summary["total"]}件 重复{summary["rep"]} → {out_path}')

    print(f'\n共生成 {len(all_records)} 条种子数据')
    return all_records


if __name__ == '__main__':
    main()
