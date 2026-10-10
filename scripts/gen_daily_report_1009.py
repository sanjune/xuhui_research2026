#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成徐汇区12345物业工单日报（按街镇分类）
数据源：/Users/macbookpro/Desktop/20261010.xlsx（2026-10-09 热线数据）
"""
import pandas as pd
from datetime import datetime

SRC = '/Users/macbookpro/Desktop/20261010.xlsx'
OUT = '/Users/macbookpro/Desktop/8-24 徐汇课题一期/徐汇区12345物业工单日报_2026年10月9日.html'

df = pd.read_excel(SRC)
total = len(df)

# ---------- 街镇汇总 ----------
df['street'] = df['s30_str_name'].fillna('__未匹配__')
# 规整异常值
df.loc[df['street'].isin(['无', '/']), 'street'] = '__未匹配__'

street_order = ['枫林路街道', '斜土路街道', '漕河泾街道', '天平路街道', '虹梅路街道',
                '徐家汇街道', '康健新村街道', '田林街道', '长桥街道', '龙华街道',
                '华泾镇', '湖南路街道', '凌云路街道', '__未匹配__']

rows = []
for st in street_order:
    sub = df[df['street'] == st]
    if len(sub) == 0:
        continue
    n = len(sub)
    # 主要类别：按市局12345原生最细一级(problemtyped)取 TOP3
    sub_typed = sub['problemtyped'].fillna('未分类').value_counts().head(3)
    main_cat = '、'.join(f'{k} {v}' for k, v in sub_typed.items()) if n else '—'
    rep = int((sub['is_repeat'] == '是').sum())
    rep_rate = rep / n * 100 if n else 0
    label = '待关联街道' if st == '__未匹配__' else st
    rows.append({
        'street': label, 'n': n, 'main_cat': main_cat,
        'rep': rep, 'rep_rate': rep_rate,
    })

rows.sort(key=lambda r: r['n'], reverse=True)

# ---------- 问题细类 TOP ----------
typed_vc = df['problemtyped'].fillna('未分类').value_counts()
top_typed = list(typed_vc.items())[:10]

# ---------- 最细一级分类全量统计（problemtyped）----------
df['_typed'] = df['problemtyped'].fillna('未分类')
typed_full = []
for k, v in df['_typed'].value_counts().items():
    n_st = df.loc[(df['_typed'] == k) & (df['street'] != '__未匹配__'), 'street'].nunique()
    typed_full.append((k, int(v), v / total * 100, int(n_st)))

# ---------- 来源 ----------
src_vc = df['hotlinesource'].fillna('未知').value_counts()

# ---------- 热线类型 ----------
type_vc = df['hotlinetype'].fillna('未标注').value_counts()

# ---------- 问题中类 ----------
pb_vc = df['problemtypeb'].fillna('未分类').value_counts()

# 重复率
rep_total = int((df['is_repeat'] == '是').sum())
rep_rate_total = rep_total / total * 100

matched = sum(r['n'] for r in rows if r['street'] != '待关联街道')
unmatched = sum(r['n'] for r in rows if r['street'] == '待关联街道')

# 重点街镇（工单>=6 或 重复率>=40%）
focus = [r for r in rows if (r['n'] >= 6 or r['rep_rate'] >= 40) and r['street'] != '待关联街道']

now = datetime.now().strftime('%Y-%m-%d %H:%M')

# ======== 生成 HTML ========
def bar(val, mx, color='#3b82f6'):
    w = val / mx * 100 if mx else 0
    return f'<div class="bar-track"><div class="bar-fill" style="width:{w:.1f}%;background:{color}"></div></div>'

max_n = max(r['n'] for r in rows)

table_rows = ''
for i, r in enumerate(rows, 1):
    cls = ' class="alt"' if i % 2 == 0 else ''
    flag = ''
    if r['street'] == '待关联街道':
        flag = '<span class="tag warn">待关联</span>'
    elif r['rep_rate'] >= 40:
        flag = '<span class="tag danger">重复高</span>'
    elif r['n'] >= 10:
        flag = '<span class="tag info">量大</span>'
    street_cell = f'{r["street"]} {flag}' if flag else r['street']
    table_rows += f'''<tr{cls}>
      <td>{i}</td>
      <td class="left">{street_cell}</td>
      <td class="num"><b>{r["n"]}</b></td>
      <td>{bar(r["n"], max_n)}</td>
      <td class="left">{r["main_cat"]}</td>
      <td class="num">{r["rep"]}</td>
      <td class="num {("danger" if r["rep_rate"]>=40 else "")}">{r["rep_rate"]:.0f}%</td>
    </tr>'''

# 概览卡片
cards = f'''
  <div class="card"><div class="c-val">{total}</div><div class="c-lab">当日工单总量</div></div>
  <div class="card"><div class="c-val">{rep_total}</div><div class="c-lab">重复案件 · {rep_rate_total:.1f}%</div></div>
  <div class="card"><div class="c-val">{matched}</div><div class="c-lab">已关联街镇工单</div></div>
  <div class="card"><div class="c-val">{unmatched}</div><div class="c-lab">待关联街道工单</div></div>
  <div class="card"><div class="c-val">13</div><div class="c-lab">涉及街镇数</div></div>
'''

# 来源
src_items = ''.join(
    f'<div class="dist-row"><span class="dist-lab">{k}</span>'
    f'<span class="dist-bar">{bar(v, src_vc.max(), "#6366f1")}</span>'
    f'<span class="dist-num">{v}</span></div>'
    for k, v in src_vc.items()
)

# 热线类型
type_items = ''.join(
    f'<div class="dist-row"><span class="dist-lab">{k}</span>'
    f'<span class="dist-bar">{bar(v, type_vc.max(), "#0ea5e9")}</span>'
    f'<span class="dist-num">{v}</span></div>'
    for k, v in type_vc.items()
)

# 问题中类
pb_items = ''.join(
    f'<div class="dist-row"><span class="dist-lab">{k}</span>'
    f'<span class="dist-bar">{bar(v, pb_vc.max(), "#f59e0b")}</span>'
    f'<span class="dist-num">{v}</span></div>'
    for k, v in pb_vc.items()
)

# 问题细类 TOP
typed_items = ''.join(
    f'<div class="dist-row"><span class="dist-lab">{k}</span>'
    f'<span class="dist-bar">{bar(v, typed_vc.max(), "#ef4444")}</span>'
    f'<span class="dist-num">{v}</span></div>'
    for k, v in top_typed
)

# 重点街镇
def _clean_prob(s):
    """简化问题正文：去换行/多空格/系统引用块，截断到 60 字。"""
    s = str(s or '')
    import re
    # 剥离系统引用块（【最近派发的工单编号…】等）
    s = re.sub(r'【.*?】', '', s)
    s = re.sub(r'\s+', '', s)
    if len(s) > 60:
        s = s[:60] + '…'
    return s or '—'

focus_html = ''
for r in focus:
    st_name = r['street']
    # 提取该街镇重复案件明细
    rep_df = df[(df['street'] == st_name) & (df['is_repeat'] == '是')].copy()
    rep_items = ''
    for _, row in rep_df.iterrows():
        reporter = str(row.get('reporter', '') or '').strip() or '—'
        addr = str(row.get('appealaddr', '') or '').strip() or '—'
        typed = str(row.get('problemtyped', '') or '').strip() or '—'
        prob = _clean_prob(row.get('problem', ''))
        rep_items += (
            f'<div class="rep-row">'
            f'<span class="rep-who">{reporter}</span>'
            f'<span class="rep-addr">{addr}</span>'
            f'<span class="rep-type">{typed}</span>'
            f'<span class="rep-prob">{prob}</span>'
            f'</div>'
        )
    rep_block = ''
    if rep_items:
        rep_block = (f'<div class="rep-list"><div class="rep-head">'
                     f'重复案件明细（{len(rep_df)} 件 · 联系人 / 地址 / 问题细类 / 问题摘要）'
                     f'</div>{rep_items}</div>')
    focus_html += (
        f'<div class="focus-item"><div class="focus-head">'
        f'<span class="focus-name">{st_name}</span>'
        f'<span class="focus-n">{r["n"]} 件</span></div>'
        f'<div class="focus-meta">主要类别：{r["main_cat"]}'
        f' · 重复案件 {r["rep"]}（{r["rep_rate"]:.0f}%）'
        + f'</div>{rep_block}</div>'
    )
if not focus_html:
    focus_html = '<p class="empty">暂无重点街镇。</p>'

# 最细一级分类全量统计行
max_tf = max(t[1] for t in typed_full)
typed_full_rows = ''
for i, (k, v, pct, n_st) in enumerate(typed_full, 1):
    cls = ' class="alt"' if i % 2 == 0 else ''
    typed_full_rows += f'''<tr{cls}>
      <td>{i}</td>
      <td class="left">{k}</td>
      <td class="num"><b>{v}</b></td>
      <td class="num">{pct:.1f}%</td>
      <td>{bar(v, max_tf, '#ef4444')}</td>
      <td class="num">{n_st}</td>
    </tr>'''

back_href = '__BACK_HREF__'
html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>徐汇区12345物业工单日报 · 2026年10月9日</title>
<style>
  :root {{
    --bg:#f5f7fa; --card:#fff; --border:#e5e9f0; --txt:#1f2937; --muted:#6b7280;
    --accent:#3b82f6; --danger:#ef4444; --warn:#f59e0b; --info:#0ea5e9; --ok:#10b981;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:"PingFang SC","Microsoft YaHei","Helvetica Neue",sans-serif;
    background:var(--bg); color:var(--txt); line-height:1.6; padding:24px; }}
  .wrap {{ max-width:1100px; margin:0 auto; }}
  header {{ text-align:center; margin-bottom:24px; }}
  header h1 {{ font-size:24px; color:#111827; margin-bottom:6px; }}
  header .sub {{ color:var(--muted); font-size:14px; }}
  header .meta {{ color:var(--muted); font-size:12px; margin-top:4px; }}
  .cards {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:24px; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:10px;
    padding:16px 8px; text-align:center; }}
  .c-val {{ font-size:26px; font-weight:700; color:var(--accent); }}
  .c-lab {{ font-size:12px; color:var(--muted); margin-top:4px; }}
  section {{ background:var(--card); border:1px solid var(--border); border-radius:10px;
    padding:18px 20px; margin-bottom:20px; }}
  section h2 {{ font-size:17px; color:#111827; border-left:4px solid var(--accent);
    padding-left:10px; margin-bottom:14px; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
  .grid3 {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:20px; }}
  .dist-row {{ display:flex; align-items:center; gap:8px; margin-bottom:8px; font-size:13px; }}
  .dist-lab {{ width:96px; text-align:right; color:var(--muted); flex-shrink:0; }}
  .dist-bar {{ flex:1; }}
  .dist-num {{ width:34px; text-align:right; font-weight:600; flex-shrink:0; }}
  .bar-track {{ background:#eef1f6; border-radius:4px; height:14px; overflow:hidden; }}
  .bar-fill {{ height:100%; border-radius:4px; transition:width .4s; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th,td {{ padding:8px 6px; text-align:center; border-bottom:1px solid var(--border); }}
  th {{ background:#f0f4f9; color:#374151; font-weight:600; white-space:nowrap; }}
  td.num {{ font-variant-numeric:tabular-nums; }}
  td.left {{ text-align:left; }}
  td.danger {{ color:var(--danger); font-weight:600; }}
  tr.alt {{ background:#fafbfc; }}
  .tag {{ display:inline-block; font-size:11px; padding:1px 6px; border-radius:4px; margin-left:4px; }}
  .tag.danger {{ background:#fee2e2; color:#b91c1c; }}
  .tag.warn {{ background:#fef3c7; color:#92400e; }}
  .tag.info {{ background:#dbeafe; color:#1e40af; }}
  .focus-item {{ border-left:3px solid var(--accent); padding:10px 14px; background:#f8fafc;
    border-radius:0 8px 8px 0; margin-bottom:10px; }}
  .focus-head {{ display:flex; justify-content:space-between; align-items:center; }}
  .focus-name {{ font-weight:600; font-size:15px; }}
  .focus-n {{ color:var(--accent); font-weight:700; }}
  .focus-meta {{ font-size:13px; color:var(--muted); margin-top:2px; }}
  .focus-meta .em {{ color:var(--danger); font-weight:600; }}
  .empty {{ color:var(--muted); }}
  .rep-list {{ margin-top:10px; border-top:1px dashed var(--border); padding-top:8px; }}
  .rep-head {{ font-size:13px; font-weight:600; color:#374151; margin-bottom:6px; }}
  .rep-row {{ display:grid; grid-template-columns:78px 1fr 86px 2fr; gap:8px; font-size:12px;
    padding:5px 0; border-bottom:1px solid #f0f2f5; align-items:start; }}
  .rep-who {{ color:#1e40af; font-weight:500; word-break:break-all; }}
  .rep-addr {{ color:#374151; word-break:break-all; }}
  .rep-type {{ color:#92400e; background:#fef3c7; padding:0 4px; border-radius:3px;
    text-align:center; height:fit-content; white-space:nowrap; }}
  .rep-prob {{ color:var(--muted); word-break:break-all; }}
  .note {{ font-size:12px; color:var(--muted); margin-top:10px; }}
  footer {{ text-align:center; color:var(--muted); font-size:12px; padding:16px 0; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <a href="{back_href}" onclick="location.href='{back_href}';return false;" style="display:inline-block;font-size:13px;color:#9bb8e0;text-decoration:none;margin-bottom:10px;cursor:pointer;">← 返回日报日历索引</a>
    <h1>徐汇区12345物业工单日报</h1>
    <div class="sub">数据日期：2026年10月9日（星期五）</div>
    <div class="meta">数据源：20261010.xlsx 同步工单 · 报告生成：{now}</div>
  </header>

  <div class="cards">{cards}</div>

  <section>
    <h2>一、当日总体情况</h2>
    <p style="font-size:14px;margin-bottom:14px;">2026年10月9日，徐汇区12345热线共接入物业相关工单 <b>{total}</b> 件，
    其中已关联到所属街镇的 <b>{matched}</b> 件，待关联（地址未匹配标准街镇）<b>{unmatched}</b> 件。
    重复案件（即工单补充来电，含补充信息、催办、查进度等，每件通常指向一条不同原始工单，非同一工单的重复登记）<b>{rep_total}</b> 件，重复率 <b>{rep_rate_total:.1f}%</b>。
    问题集中在 <b>住房保障·物业服务管理</b>（{pb_vc.get("住房保障",0)} 件）与 <b>城管执法·物业相关执法</b>（{pb_vc.get("城管执法",0)} 件）。</p>
    <div class="grid3">
      <div><h3 style="font-size:14px;margin-bottom:10px;">受理来源</h3>{src_items}</div>
      <div><h3 style="font-size:14px;margin-bottom:10px;">热线类型</h3>{type_items}</div>
      <div><h3 style="font-size:14px;margin-bottom:10px;">问题中类</h3>{pb_items}</div>
    </div>
  </section>

  <section>
    <h2>二、街镇分类明细</h2>
    <table>
      <thead><tr>
        <th>#</th><th class="left">街镇</th><th>工单</th><th>占比</th>
        <th class="left">主要类别</th>
        <th>重复案件</th><th>重复率</th>
      </tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
    <p class="note">注："主要类别"= 当街镇内按市局12345原生最细一级(problemtyped)统计的前3个细类，格式"类别 件数"；
    "待关联街道"指工单地址未匹配到徐汇区13个标准街镇的记录，需人工补录街道归属；
    "重复案件"指市民就已有工单再次来电（补充信息、催办、查进度等，即工单补充），每件通常指向一条不同原始工单，非同一工单的重复登记；
    "重复率"= 当街镇内 is_repeat=是 工单数 ÷ 当街镇工单总量。</p>
  </section>

  <section>
    <h2>三、12345平台原生分类</h2>
    <p style="font-size:13px;margin-bottom:14px;color:var(--muted);">按市局12345原生分类最细一级（problemtyped）统计，共 {len(typed_full)} 类 {total} 件。</p>
    <table>
      <thead><tr><th>#</th><th class="left">最细一级分类</th><th>工单</th><th>占比</th><th>分布</th><th>涉及街镇</th></tr></thead>
      <tbody>{typed_full_rows}</tbody>
    </table>
    <p class="note">注：占比 = 该细类工单数 ÷ 当日总量 {total}；"涉及街镇"=该细类出现的已关联街镇数（不含待关联）。</p>
  </section>

  <section>
    <h2>四、重点街镇关注</h2>
    <p style="font-size:13px;margin-bottom:12px;color:var(--muted);">筛选标准：当日工单 ≥ 6 件 或 重复率 ≥ 40%。</p>
    {focus_html}
  </section>

  <footer>徐汇区物业投诉治理数字化分析项目 · 日报自动生成</footer>
</div>
</body>
</html>'''

import os
ROOT_DIR = os.path.dirname(OUT)
# 根目录中文名版（用户直接查看，回链指向 daily/index.html 源）
html_root = html.replace('__BACK_HREF__', 'daily/index.html')
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html_root)
print('已生成日报(根目录):', OUT)

# 源 daily/ 版（供 build_publish_site.py 复制到 _publish/daily/，回链同目录 index.html）
DAILY_SRC = os.path.join(ROOT_DIR, 'daily')
os.makedirs(DAILY_SRC, exist_ok=True)
out_daily = os.path.join(DAILY_SRC, '2026-10-09.html')
html_daily = html.replace('__BACK_HREF__', 'index.html')
with open(out_daily, 'w', encoding='utf-8') as f:
    f.write(html_daily)
print('已生成日报(daily源):', out_daily)
print('工单总数:', total, '| 重复:', rep_total, f'({rep_rate_total:.1f}%)', '| 已关联街镇:', matched, '| 待关联:', unmatched)
