#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
徐汇区12345物业工单日报 - 在线上传服务

功能：
  1. 日历索引页面（GET /）
  2. 上传页面（GET /upload）
  3. 接收每日 excel 文件并自动生成日报（POST /upload）
  4. 报告 API（GET /api/reports）
  5. 已生成日报的访问（GET /YYYY-MM-DD.html）

部署：通过 WorkBuddy sites 发布为在线应用
  - 必须监听 PORT 环境变量并绑定 0.0.0.0
  - 依赖：pandas, openpyxl
"""
import os, sys, re, json, html as html_mod
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, 'data')
REPORTS_JSON = os.path.join(DATA_DIR, 'reports.json')
INDEX_TEMPLATE = os.path.join(APP_DIR, 'index_template.html')

PORT = int(os.environ.get('PORT', 8766))

# GitHub Pages 门户地址（日历索引的"返回"按钮指向这里）
PORTAL_URL = 'https://sanjune.github.io/xuhui_research2026/'


# ============================================================
# 个人信息脱敏（与 gen_daily_report_1009.py 完全一致）
# ============================================================
_PII_RULES = [
    (re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)'),
     lambda m: m.group()[:3] + '****' + m.group()[-4:]),
    (re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)'),
     lambda m: m.group()[:6] + '*' * 8 + m.group()[-4:]),
    (re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
     lambda m: m.group()[0] + '*' * (len(m.group().split('@')[0]) - 1) + '@' + m.group().split('@')[1]),
]


def mask_pii(s):
    s = str(s or '')
    for rx, rep in _PII_RULES:
        s = rx.sub(rep, s)
    return s


def _assert_no_pii(text, label):
    for rx, name in ((_PII_RULES[0][0], '手机号'), (_PII_RULES[1][0], '身份证号'), (_PII_RULES[2][0], '邮箱')):
        hits = sorted(set(rx.findall(text)))
        if hits:
            raise ValueError(f'{label} 仍残留{name}：{hits[:3]}（脱敏未生效，拒绝出稿）')


def _clean_prob(s):
    s = str(s or '')
    s = re.sub(r'【.*?】', '', s)
    s = re.sub(r'\s+', '', s)
    s = mask_pii(s)
    if len(s) > 60:
        s = s[:60] + '…'
    return s or '—'


# ============================================================
# 报告生成（从 gen_daily_report_1009.py 移植，自包含）
# ============================================================
def generate_report(xlsx_path):
    """读取 xlsx → 生成日报 HTML → 返回 (html_string, summary_dict)"""
    import pandas as pd

    df = pd.read_excel(xlsx_path)
    total = len(df)

    _data_dates = pd.to_datetime(df['processtime']).dt.date
    data_date = _data_dates.mode().iloc[0]
    WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
    date_cn = f"{data_date.year}年{data_date.month}月{data_date.day}日"
    date_weekday = WEEKDAYS[data_date.weekday()]
    date_slug = data_date.isoformat()
    src_name = os.path.basename(xlsx_path)

    # 街镇汇总
    df['street'] = df['s30_str_name'].fillna('__未匹配__')
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
        sub_typed = sub['problemtyped'].fillna('未分类').value_counts().head(3)
        main_cat = '、'.join(f'{k} {v}' for k, v in sub_typed.items()) if n else '—'
        rep = int((sub['is_repeat'] == '是').sum())
        rep_rate = rep / n * 100 if n else 0
        label = '待关联街道' if st == '__未匹配__' else st
        rows.append({'street': label, 'n': n, 'main_cat': main_cat, 'rep': rep, 'rep_rate': rep_rate})

    rows.sort(key=lambda r: r['n'], reverse=True)

    # 最细一级分类全量统计
    df['_typed'] = df['problemtyped'].fillna('未分类')
    typed_vc = df['_typed'].value_counts()
    top_typed = list(typed_vc.items())[:10]
    typed_full = []
    for k, v in df['_typed'].value_counts().items():
        n_st = df.loc[(df['_typed'] == k) & (df['street'] != '__未匹配__'), 'street'].nunique()
        typed_full.append((k, int(v), v / total * 100, int(n_st)))

    src_vc = df['hotlinesource'].fillna('未知').value_counts()
    type_vc = df['hotlinetype'].fillna('未标注').value_counts()
    pb_vc = df['problemtypeb'].fillna('未分类').value_counts()

    rep_total = int((df['is_repeat'] == '是').sum())
    rep_rate_total = rep_total / total * 100

    matched = sum(r['n'] for r in rows if r['street'] != '待关联街道')
    unmatched = sum(r['n'] for r in rows if r['street'] == '待关联街道')

    focus = [r for r in rows if (r['n'] >= 6 or r['rep_rate'] >= 40) and r['street'] != '待关联街道']

    now = datetime.now().strftime('%Y-%m-%d %H:%M')

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

    cards = f'''
  <div class="card"><div class="c-val">{total}</div><div class="c-lab">当日工单总量</div></div>
  <div class="card"><div class="c-val">{rep_total}</div><div class="c-lab">重复案件 · {rep_rate_total:.1f}%</div></div>
  <div class="card"><div class="c-val">{matched}</div><div class="c-lab">已关联街镇工单</div></div>
  <div class="card"><div class="c-val">{unmatched}</div><div class="c-lab">待关联街道工单</div></div>
  <div class="card"><div class="c-val">13</div><div class="c-lab">涉及街镇数</div></div>
'''

    src_items = ''.join(
        f'<div class="dist-row"><span class="dist-lab">{k}</span>'
        f'<span class="dist-bar">{bar(v, src_vc.max(), "#6366f1")}</span>'
        f'<span class="dist-num">{v}</span></div>'
        for k, v in src_vc.items()
    )
    type_items = ''.join(
        f'<div class="dist-row"><span class="dist-lab">{k}</span>'
        f'<span class="dist-bar">{bar(v, type_vc.max(), "#0ea5e9")}</span>'
        f'<span class="dist-num">{v}</span></div>'
        for k, v in type_vc.items()
    )
    pb_items = ''.join(
        f'<div class="dist-row"><span class="dist-lab">{k}</span>'
        f'<span class="dist-bar">{bar(v, pb_vc.max(), "#f59e0b")}</span>'
        f'<span class="dist-num">{v}</span></div>'
        for k, v in pb_vc.items()
    )
    typed_items = ''.join(
        f'<div class="dist-row"><span class="dist-lab">{k}</span>'
        f'<span class="dist-bar">{bar(v, typed_vc.max(), "#ef4444")}</span>'
        f'<span class="dist-num">{v}</span></div>'
        for k, v in top_typed
    )

    # 重点街镇重复案件明细
    focus_html = ''
    for r in focus:
        st_name = r['street']
        rep_df = df[(df['street'] == st_name) & (df['is_repeat'] == '是')].copy()
        rep_items = ''
        for _, row in rep_df.iterrows():
            addr = str(row.get('appealaddr', '') or '').strip() or '—'
            typed = str(row.get('problemtyped', '') or '').strip() or '—'
            prob = _clean_prob(row.get('problem', ''))
            rep_items += (
                f'<div class="rep-row">'
                f'<span class="rep-addr">{addr}</span>'
                f'<span class="rep-type">{typed}</span>'
                f'<span class="rep-prob">{prob}</span>'
                f'</div>'
            )
        rep_block = ''
        if rep_items:
            rep_block = (f'<div class="rep-list"><div class="rep-head">'
                         f'重复案件明细（{len(rep_df)} 件 · 地址 / 问题细类 / 问题摘要）'
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

    report_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>徐汇区12345物业工单日报 · {date_cn}</title>
<style>
  :root {{ --bg:#f5f7fa; --card:#fff; --border:#e5e9f0; --txt:#1f2937; --muted:#6b7280;
    --accent:#3b82f6; --danger:#ef4444; --warn:#f59e0b; --info:#0ea5e9; --ok:#10b981; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:"PingFang SC","Microsoft YaHei","Helvetica Neue",sans-serif;
    background:var(--bg); color:var(--txt); line-height:1.6; padding:24px; }}
  .wrap {{ max-width:1100px; margin:0 auto; }}
  header {{ text-align:center; margin-bottom:24px; }}
  header h1 {{ font-size:24px; color:#111827; margin-bottom:6px; }}
  header .sub {{ color:var(--muted); font-size:14px; }}
  header .meta {{ color:var(--muted); font-size:12px; margin-top:4px; }}
  .cards {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:24px; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px 8px; text-align:center; }}
  .c-val {{ font-size:26px; font-weight:700; color:var(--accent); }}
  .c-lab {{ font-size:12px; color:var(--muted); margin-top:4px; }}
  section {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:18px 20px; margin-bottom:20px; }}
  section h2 {{ font-size:17px; color:#111827; border-left:4px solid var(--accent); padding-left:10px; margin-bottom:14px; }}
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
  .focus-item {{ border-left:3px solid var(--accent); padding:10px 14px; background:#f8fafc; border-radius:0 8px 8px 0; margin-bottom:10px; }}
  .focus-head {{ display:flex; justify-content:space-between; align-items:center; }}
  .focus-name {{ font-weight:600; font-size:15px; }}
  .focus-n {{ color:var(--accent); font-weight:700; }}
  .focus-meta {{ font-size:13px; color:var(--muted); margin-top:2px; }}
  .empty {{ color:var(--muted); }}
  .rep-list {{ margin-top:10px; border-top:1px dashed var(--border); padding-top:8px; }}
  .rep-head {{ font-size:13px; font-weight:600; color:#374151; margin-bottom:6px; }}
  .rep-row {{ display:grid; grid-template-columns:110px 92px 1fr; gap:8px; font-size:12px; padding:5px 0; border-bottom:1px solid #f0f2f5; align-items:start; }}
  .rep-addr {{ color:#374151; word-break:break-all; }}
  .rep-type {{ color:#92400e; background:#fef3c7; padding:0 4px; border-radius:3px; text-align:center; height:fit-content; white-space:nowrap; }}
  .rep-prob {{ color:var(--muted); word-break:break-all; }}
  .note {{ font-size:12px; color:var(--muted); margin-top:10px; }}
  footer {{ text-align:center; color:var(--muted); font-size:12px; padding:16px 0; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <a href="index.html" onclick="location.href='index.html';return false;" style="display:inline-block;font-size:13px;color:#9bb8e0;text-decoration:none;margin-bottom:10px;cursor:pointer;">← 返回日报日历索引</a>
    <h1>徐汇区12345物业工单日报</h1>
    <div class="sub">数据日期：{date_cn}（{date_weekday}）</div>
    <div class="meta">数据源：{src_name} 同步工单 · 报告生成：{now}</div>
  </header>
  <div class="cards">{cards}</div>
  <section>
    <h2>一、当日总体情况</h2>
    <p style="font-size:14px;margin-bottom:14px;">{date_cn}，徐汇区12345热线共接入物业相关工单 <b>{total}</b> 件，
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
        <th class="left">主要类别</th><th>重复案件</th><th>重复率</th>
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

    # 整页兜底脱敏
    report_html = mask_pii(report_html)
    _assert_no_pii(report_html, '在线日报')

    # 构造摘要
    WEEKDAYS_SHORT = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    summary = {
        'date': date_slug,
        'weekday': WEEKDAYS_SHORT[data_date.weekday()],
        'total': total,
        'matched': matched,
        'unmatched': unmatched,
        'rep': rep_total,
        'repRate': round(rep_rate_total, 1),
        'streets': sum(1 for r in rows if r['street'] != '待关联街道'),
        'mainCat': [f'{k} {v}' for k, v in typed_vc.head(3).items()],
        'file': f'{date_slug}.html'
    }
    return report_html, summary


# ============================================================
# 日历索引页面
# ============================================================
def _report_to_js(r):
    """将单条报告 dict 转为 JS 对象字面量字符串（避免嵌套 f-string）"""
    mc = ', '.join("'" + str(x) + "'" for x in r['mainCat'])
    return (
        "  { date:'%s', weekday:'%s', total:%d, matched:%d, unmatched:%d, "
        "rep:%d, repRate:%s, streets:%d, mainCat:[%s], file:'%s' }" % (
            r['date'], r['weekday'], r['total'], r['matched'], r['unmatched'],
            r['rep'], r['repRate'], r['streets'], mc, r['file']
        )
    )


def serve_index():
    """读取模板 → 注入 REPORTS JSON → 返回 HTML"""
    with open(INDEX_TEMPLATE, 'r', encoding='utf-8') as f:
        tpl = f.read()
    reports = load_reports()
    if reports:
        reports_js = '[\n' + ',\n'.join(_report_to_js(r) for r in reports) + '\n]'
    else:
        reports_js = '[]'
    return tpl.replace('__REPORTS__', reports_js)


def load_reports():
    if os.path.exists(REPORTS_JSON):
        with open(REPORTS_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_reports(reports):
    with open(REPORTS_JSON, 'w', encoding='utf-8') as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)


def update_reports(summary):
    """更新 reports.json（去重按日期，同日替换）"""
    reports = load_reports()
    date = summary['date']
    reports = [r for r in reports if r.get('date') != date]
    reports.append(summary)
    reports.sort(key=lambda r: r['date'])
    save_reports(reports)
    return True


# ============================================================
# 上传页面
# ============================================================
CSS_UPLOAD = '''
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: #f0f4f8; color: #1a2a3a; min-height: 100vh; padding: 20px; }
.wrap { max-width: 640px; margin: 40px auto; background: #fff;
  border-radius: 14px; box-shadow: 0 6px 24px rgba(0,0,0,.08); padding: 36px 40px; }
h1 { font-size: 22px; color: #1a3a5c; margin-bottom: 4px; }
.sub { font-size: 13px; color: #6b7c8e; margin-bottom: 24px; }
.upload-zone { display:block; border: 2px dashed #b8c8d8; border-radius: 10px; padding: 32px 20px;
  text-align: center; transition: all .2s; cursor: pointer; background: #fafcfe; }
.upload-zone:hover { border-color: #4a7ab8; background: #f0f6fc; }
.upload-zone.drag { border-color: #2a6ab8; background: #e8f0fc; }
.upload-zone p { color: #6b7c8e; font-size: 14px; margin-top: 8px; }
.upload-icon { font-size: 36px; color: #b8c8d8; }
input[type=file] { display: none; }
.file-name { margin-top: 12px; font-size: 13px; color: #2a6ab8; word-break: break-all; }
.btn { display: inline-block; background: #2a6ab8; color: #fff; border: none;
  padding: 12px 32px; border-radius: 8px; font-size: 15px; cursor: pointer;
  margin-top: 20px; transition: background .2s; }
.btn:hover { background: #1a5a98; }
.btn:disabled { background: #b8c8d8; cursor: not-allowed; }
.back { display: inline-block; font-size: 13px; color: #4a7ab8; text-decoration: none;
  margin-bottom: 16px; cursor: pointer; }
.result { margin-top: 24px; padding: 18px 20px; border-radius: 10px; font-size: 14px; }
.result.ok { background: #e8f6e8; border: 1px solid #8cc88c; color: #2a6a2a; }
.result.err { background: #fde8e8; border: 1px solid #e8a8a8; color: #8a2a2a; }
.result b { font-size: 15px; }
.stats { margin-top: 14px; display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; }
.stat { background: #f4f8fc; border-radius: 8px; padding: 12px; text-align: center; }
.stat .v { font-size: 22px; font-weight: 700; color: #1a3a5c; }
.stat .l { font-size: 11px; color: #6b7c8e; margin-top: 2px; }
.links { margin-top: 18px; display: flex; gap: 12px; flex-wrap: wrap; }
.links a { font-size: 13px; color: #2a6ab8; text-decoration: none; padding: 8px 16px;
  background: #eef4fc; border-radius: 6px; border: 1px solid #cce0f0; cursor: pointer; }
.links a:hover { background: #e0ecf8; }
.spin { display: none; margin-top: 16px; color: #6b7c8e; font-size: 13px; }
.spin.show { display: block; }
.spin::after { content: ''; display: inline-block; width: 14px; height: 14px;
  border: 2px solid #b8c8d8; border-top: 2px solid #2a6ab8; border-radius: 50%;
  animation: sp .6s linear infinite; vertical-align: middle; margin-left: 6px; }
@keyframes sp { to { transform: rotate(360deg); } }
.note { margin-top: 20px; padding: 12px 14px; background: #fffbe8; border-radius: 8px;
  font-size: 12px; color: #8a6a2a; line-height: 1.6; }
'''

UPLOAD_PAGE = f'''<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>每日数据上传 · 12345物业工单日报</title>
<style>{CSS_UPLOAD}</style></head><body>
<div class="wrap">
  <a class="back" onclick="location.href='index.html'">← 返回日报日历索引</a>
  <h1>每日热线数据上传</h1>
  <div class="sub">选择当日 12345 热线工单 Excel 文件，自动生成日报并更新日历索引</div>
  <form id="upForm" enctype="multipart/form-data" method="POST" action="/upload">
    <label class="upload-zone" id="dropZone" for="fileInput">
      <div class="upload-icon">📁</div>
      <p>点击选择文件 或 拖拽 Excel 到此处</p>
      <p style="font-size:12px;color:#a8b8c8;margin-top:4px;">支持 .xlsx 格式</p>
      <div class="file-name" id="fileName"></div>
    </label>
    <input type="file" id="fileInput" name="file" accept=".xlsx,.xls" required>
    <button type="submit" class="btn" id="submitBtn" disabled>上传并生成日报</button>
  </form>
  <div class="spin" id="spin">正在处理：保存文件 → 生成日报 → 更新索引</div>
  <div id="resultBox"></div>
  <div class="note">
    <b>说明</b>：上传的 Excel 将自动生成日报并更新日历索引。数据经脱敏处理（手机号/身份证/邮箱），
    确保无个人隐私泄露。已上传的日报可通过日历索引随时查看。
  </div>
</div>
<script>
const fi = document.getElementById('fileInput');
const fn = document.getElementById('fileName');
const sb = document.getElementById('submitBtn');
const dz = document.getElementById('dropZone');
fi.addEventListener('change', function() {{
  if (this.files.length) {{ fn.textContent = '已选择：' + this.files[0].name; sb.disabled = false; }}
}});
dz.addEventListener('dragover', e => {{ e.preventDefault(); dz.classList.add('drag'); }});
dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
dz.addEventListener('drop', e => {{
  e.preventDefault(); dz.classList.remove('drag');
  if (e.dataTransfer.files.length) {{
    fi.files = e.dataTransfer.files;
    fn.textContent = '已选择：' + e.dataTransfer.files[0].name;
    sb.disabled = false;
  }}
}});
document.getElementById('upForm').addEventListener('submit', function() {{
  document.getElementById('spin').classList.add('show');
  sb.disabled = true;
}});
</script>
</body></html>'''


def build_result_page(ok, summary, error_msg=''):
    if not ok:
        return f'''<div class="result err">
  <b>❌ 生成失败</b>
  <div style="margin-top:10px;font-size:13px;white-space:pre-wrap;">{html_mod.escape(error_msg)}</div>
</div>'''
    s = summary
    mc = '、'.join(s['mainCat'])
    return f'''<div class="result ok">
  <b>✅ 日报已生成：{s['date']}（{s['weekday']}）</b>
  <div class="stats">
    <div class="stat"><div class="v">{s['total']}</div><div class="l">工单总量</div></div>
    <div class="stat"><div class="v">{s['rep']}</div><div class="l">重复案件</div></div>
    <div class="stat"><div class="v">{s['repRate']}%</div><div class="l">重复率</div></div>
  </div>
  <div style="margin-top:12px;font-size:13px;color:#4a5a6a;">
    已关联街镇 <b>{s['matched']}</b> 件（{s['streets']} 个街镇）· 待关联 <b>{s['unmatched']}</b> 件<br>
    主要类别：{mc}
  </div>
  <div class="links">
    <a onclick="location.href='index.html'">查看日历索引</a>
    <a onclick="location.href='{s['file']}'">查看当日日报</a>
    <a onclick="location.href='/upload'">继续上传</a>
  </div>
</div>'''


# ============================================================
# multipart 解析
# ============================================================
def parse_multipart(body, boundary):
    fields = {}
    delim = b'--' + boundary
    parts = body.split(delim)
    for part in parts:
        part = part.strip(b'\r\n')
        if not part or part == b'--':
            continue
        header_end = part.find(b'\r\n\r\n')
        if header_end < 0:
            continue
        header = part[:header_end].decode('utf-8', 'ignore')
        content = part[header_end + 4:]
        name_m = re.search(r'name="([^"]+)"', header)
        file_m = re.search(r'filename="([^"]*)"', header)
        if name_m:
            name = name_m.group(1)
            filename = file_m.group(1) if file_m else None
            if content.endswith(b'\r\n'):
                content = content[:-2]
            fields[name] = (filename, content)
    return fields


# ============================================================
# HTTP Handler
# ============================================================
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        msg = fmt % args if args else fmt
        sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

    def _send(self, code, body, ctype='text/html; charset=utf-8'):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/index.html'):
            self._send(200, serve_index())
        elif path == '/api/reports':
            reports = load_reports()
            self._send(200, json.dumps(reports, ensure_ascii=False), 'application/json; charset=utf-8')
        elif path == '/upload':
            self._send(200, UPLOAD_PAGE)
        elif path.endswith('.html'):
            report_path = os.path.join(DATA_DIR, path.lstrip('/'))
            if os.path.exists(report_path):
                with open(report_path, 'rb') as f:
                    self._send(200, f.read())
            else:
                self._send(404, '<h1>404</h1><p>日报不存在</p>')
        else:
            self._send(404, '<h1>404 Not Found</h1>')

    def do_POST(self):
        path = urlparse(self.path).path
        if path != '/upload':
            self._send(404, '<h1>404 Not Found</h1>')
            return
        clen = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(clen) if clen else b''
        ctype = self.headers.get('Content-Type', '')
        bmatch = re.search(r'boundary=(.+)', ctype)
        if not bmatch:
            self._send(400, '错误的 Content-Type')
            return
        boundary = bmatch.group(1).strip().encode('utf-8')
        fields = parse_multipart(body, boundary)
        if 'file' not in fields:
            self._send(400, '未收到文件')
            return
        filename, content = fields['file']
        if not filename:
            self._send(400, '文件名为空')
            return
        if not filename.lower().endswith(('.xlsx', '.xls')):
            self._send(400, '仅支持 .xlsx / .xls 格式')
            return

        # 保存上传文件到临时目录
        tmp_path = os.path.join(DATA_DIR, '_upload_' + filename)
        with open(tmp_path, 'wb') as f:
            f.write(content)
        self.log_message(f"已接收上传文件: {filename} ({len(content)} bytes)")

        # 生成日报
        try:
            report_html, summary = generate_report(tmp_path)
            # 保存日报 HTML
            report_path = os.path.join(DATA_DIR, summary['file'])
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_html)
            # 更新 reports.json
            update_reports(summary)
            self.log_message(
                f"日报已生成: {summary['date']} | 工单{summary['total']} | "
                f"重复{summary['rep']}({summary['repRate']}%)"
            )
            page = UPLOAD_PAGE.replace(
                '<div id="resultBox"></div>',
                build_result_page(True, summary)
            )
            self._send(200, page)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.log_message(f"日报生成失败: {e}\n{tb}")
            page = UPLOAD_PAGE.replace(
                '<div id="resultBox"></div>',
                build_result_page(False, None, f'{e}\n\n{tb[-500:]}')
            )
            self._send(200, page)
        finally:
            # 清理临时文件
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f"=" * 56)
    print(f"  12345 物业工单日报 · 在线上传服务")
    print(f"  监听端口: 0.0.0.0:{PORT}")
    print(f"  数据目录: {DATA_DIR}")
    print(f"  按 Ctrl+C 停止服务")
    print(f"=" * 56)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.server_close()


if __name__ == '__main__':
    main()
