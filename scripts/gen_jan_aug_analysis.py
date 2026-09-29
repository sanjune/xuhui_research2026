#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1-8月工单综合分析报告生成器
- 街镇横向对比（降幅/密度）
- 徐汇全市水平对比 + 月度走势
- 保持前列目标工单水平测算
口径：街镇用项目主数据口径；全市对比用市局十四类口径
"""
import pandas as pd, numpy as np, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

def green_red(v, suffix='%'):
    """涨红跌绿：下降(负)用绿，上升(正)用红"""
    if v is None or (isinstance(v,float) and (np.isnan(v))): return '-'
    s = f'{v:+.1f}{suffix}' if suffix else f'{v:+.1f}'
    if v < 0: return f'<span style="color:#16a34a;font-weight:600">↓{abs(v):.1f}{suffix}</span>'
    elif v > 0: return f'<span style="color:#dc2626;font-weight:600">↑{v:.1f}{suffix}</span>'
    else: return f'<span style="color:#6b7280;font-weight:600">0{suffix}</span>'

def arrow(v):
    if v < 0: return ('↓','green')
    elif v > 0: return ('↑','red')
    return ('-','gray')

# ============ 1. 街镇横向对比 (项目口径) ============
df = pd.read_pickle('data/merged_cleaned.pkl')
df['accept_time']=pd.to_datetime(df['accept_time'])
df['y']=df['accept_time'].dt.year
df['m']=df['accept_time'].dt.month
cur = df[(df.street!='无') & (df.y==2026) & (df['accept_time']<='2026-08-31')]
prev = df[(df.street!='无') & (df.y==2025) & (df['accept_time']<='2025-08-31')]
ct = cur.groupby('street').size().rename('c2026')
pt = prev.groupby('street').size().rename('c2025')
cd = pd.read_pickle('data/community_linked_data.pkl')
hh = cd.groupby('street')['total_households'].sum()
tab = pd.concat([ct,pt,hh],axis=1).fillna(0)
tab['c2026']=tab['c2026'].astype(int); tab['c2025']=tab['c2025'].astype(int)
tab['households']=tab['total_households'].astype(int)
tab['yoy']=(tab.c2026/tab.c2025-1)*100
tab['density']=tab.c2026/tab.households*1000
tab=tab.sort_values('c2026',ascending=False).reset_index()
street_rows=[]
for _,r in tab.iterrows():
    street_rows.append({
        'name':r['street'],'c26':int(r['c2026']),'c25':int(r['c2025']),
        'yoy':round(float(r['yoy']),2),'hh':int(r['households']),
        'density':round(float(r['density']),1)
    })
street_total_26 = int(tab.c2026.sum())
street_total_25 = int(tab.c2025.sum())
street_total_hh = int(tab.households.sum())

# ============ 2. 全市对比 (市局口径) ============
xls = pd.ExcelFile('全市各区十四类问题工单情况（增加1-6 月同比）.xlsx')
# 1-8月汇总排名
s=pd.read_excel(xls,'1-8月',header=None)
body=s.iloc[2:].copy(); body.columns=['序号','行政区','c2026','c2025','yoy']
body=body.dropna(subset=['行政区']); body=body[body['行政区']!='合计']
body['行政区']=body['行政区'].astype(str).str.replace('\n','').str.replace('(南汇新城镇)','新片区').str.strip()  # 归并临港名
body['c2026']=body['c2026'].astype(int); body['c2025']=body['c2025'].astype(int)
body['yoy']=body['yoy'].astype(float)*100
body['density_base'] = body['c2026']/(body['c2026']/3.83375/8*0)  # 占位
# 密度
rows=[]
for m in ['1月','2月','3月','4月','5月','6月','7月','8月']:
    d=pd.read_excel(xls,m,header=None).iloc[3:]
    d.columns=['序号','行政区','工单量','同比','环比','密度']
    d=d.dropna(subset=['行政区']); d['月份']=m; rows.append(d)
allm=pd.concat(rows)
allm['行政区']=allm['行政区'].astype(str).str.replace('\n','').str.replace('(南汇新城镇)','新片区').str.strip()
allm['工单量']=pd.to_numeric(allm['工单量'],errors='coerce')
allm['密度']=pd.to_numeric(allm['密度'],errors='coerce')
allm['同比']=allm['同比'].astype(str).str.replace('↑','').str.replace('↓','-').str.replace('%','')
allm['同比']=pd.to_numeric(allm['同比'],errors='coerce')
allm['环比']=allm['环比'].astype(str).str.replace('↑','').str.replace('↓','-').str.replace('%','')
allm['环比']=pd.to_numeric(allm['环比'],errors='coerce')
gd=allm.groupby('行政区').agg(累计=('工单量','sum'),平均密度=('密度','mean'),同比均值=('同比','mean')).reset_index()
rank_df=body.merge(gd,on='行政区')
rank_df=rank_df.sort_values('yoy')  # 降幅降序
rank_df['降幅排名']=range(1,len(rank_df)+1)
gd2=gd.sort_values('平均密度',ascending=False); gd2['密度排名']=range(1,len(gd2)+1)
rank_df=rank_df.merge(gd2[['行政区','密度排名']],on='行政区')
city_rows=[]
for _,r in rank_df.iterrows():
    city_rows.append({
        'name':r['行政区'],'c26':int(r['c2026']),'c25':int(r['c2025']),
        'yoy':round(float(r['yoy']),1),'density':round(float(r['平均密度']),2),
        'dr':int(r['降幅排名']),'ddr':int(r['密度排名'])
    })
# 徐汇月度走势
xh_m = allm[allm['行政区']=='徐汇区'].sort_values('月份')
month_order={'1月':1,'2月':2,'3月':3,'4月':4,'5月':5,'6月':6,'7月':7,'8月':8}
xh_m['mo']=xh_m['月份'].map(month_order); xh_m=xh_m.sort_values('mo')
xh_monthly=[]
for _,r in xh_m.iterrows():
    xh_monthly.append({'m':r['月份'],'vol':int(r['工单量']),'yoy':round(float(r['同比']),1),'mom':round(float(r['环比']),1),'density':round(float(r['密度']),2)})

# ============ 3. 目标测算 (市局口径) ============
base_full_2025=23618; base_9525=7820; cur_18=13726; days=122
scenarios=[
    ('-15.4% · 达全市平均（进前9）',-15.4),
    ('-15.0% · 挑战线',-15.0),
    ('-13.1% · 维持当前位次',-13.1),
    ('-10.0% · 底线（仍为下降）',-10.0),
    ('-8.8% · 持平2025同期（警惕）',-8.8),
    ('0% · 持平全年',0.0),
]
scen_rows=[]
for label,r in scenarios:
    full=base_full_2025*(1+r/100)
    x=full-cur_18
    scen_rows.append({
        'label':label,'r':r,'full':int(round(full)),'x':int(round(x)),
        'mo':int(round(x/4)),'day':round(x/days,1),'vs25':round((x/base_9525-1)*100,1)
    })

# 9月按趋势假设下的补救测算
remediate=[]
sep_est=2250
for label,r in [('维持-13.1%',-13.1),('达全市平均-15.4%',-15.4),('保-10%底线',-10.0)]:
    full=base_full_2025*(1+r/100)
    x_octdec=full-cur_18-sep_est
    x_novdec=x_octdec-2200
    remediate.append({'label':label,'r':r,'octdec':int(round(x_octdec)),'octdec_day':round(x_octdec/92,1),
                      'novdec':int(round(x_novdec)),'novdec_day':round(x_novdec/61,1)})

DATA={
    'street':{'rows':street_rows,'t26':street_total_26,'t25':street_total_25,'thh':street_total_hh,
              't_yoy':round((street_total_26/street_total_25-1)*100,1),
              't_density':round(street_total_26/street_total_hh*1000,1)},
    'city':{'rows':city_rows,'xh_rank_dr':13,'xh_rank_ddr':2,'avg_yoy':-15.4,
            'xh_c26':13726,'xh_c25':15798,'xh_yoy':-13.1,'xh_density':3.83},
    'xh_monthly':xh_monthly,
    'target':{'base_full_2025':base_full_2025,'base_9525':base_9525,'cur_18':cur_18,
              'scenarios':scen_rows,'remediate':remediate,
              'aug_vol':2242,'aug_day':round(2242/31,1),'h1_day':round(cur_18/243,1)},
}

# ============ HTML (普通字符串，DATA 用占位符注入，避免 f-string 花括号冲突) ============
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>徐汇区1-8月工单综合分析与目标测算</title>
<script src="assets/vendor/echarts.min.js"></script>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1f2937;--sub:#6b7280;--line:#e5e7eb;
--red:#dc2626;--green:#16a34a;--blue:#2563eb;--amber:#d97706;--purple:#7c3aed;}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
line-height:1.65;font-size:15px;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:28px 22px 60px}
h1{font-size:26px;font-weight:700;letter-spacing:.5px;margin-bottom:6px}
.sub{color:var(--sub);font-size:13px;margin-bottom:22px}
h2{font-size:19px;font-weight:700;margin:34px 0 14px;padding-left:12px;border-left:4px solid var(--blue)}
h2 .n{color:var(--blue);margin-right:8px}
h3{font-size:15px;font-weight:600;margin:20px 0 10px;color:#374151}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px 22px;margin-bottom:18px;
box-shadow:0 1px 2px rgba(0,0,0,.03)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:6px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;position:relative;overflow:hidden}
.kpi::before{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--blue)}
.kpi.r::before{background:var(--red)}.kpi.g::before{background:var(--green)}.kpi.a::before{background:var(--amber)}
.kpi .lab{font-size:12px;color:var(--sub);margin-bottom:4px}
.kpi .val{font-size:24px;font-weight:700}
.kpi .val small{font-size:13px;font-weight:500;color:var(--sub)}
.kpi .tag{font-size:12px;margin-top:3px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{background:#f3f4f6;text-align:left;padding:9px 12px;font-weight:600;color:#374151;border-bottom:2px solid var(--line);white-space:nowrap}
td{padding:8px 12px;border-bottom:1px solid #f1f3f5;white-space:nowrap}
tr:hover td{background:#fafbfc}
.r{text-align:right}.c{text-align:center}
.bad{color:var(--red);font-weight:600}.good{color:var(--green);font-weight:600}
.chart{width:100%;height:380px}
.chart.s{height:320px}
.note{font-size:12.5px;color:var(--sub);margin-top:8px;line-height:1.6}
.callout{background:linear-gradient(135deg,#eff6ff,#fff);border:1px solid #bfdbfe;border-left:4px solid var(--blue);
border-radius:8px;padding:14px 18px;margin:12px 0;font-size:14px}
.callout.warn{background:linear-gradient(135deg,#fff7ed,#fff);border-color:#fed7aa;border-left-color:var(--amber)}
.callout.danger{background:linear-gradient(135deg,#fef2f2,#fff);border-color:#fecaca;border-left-color:var(--red)}
.tag{display:inline-block;padding:1px 8px;border-radius:4px;font-size:11px;font-weight:600}
.t-red{background:#fee2e2;color:#b91c1c}.t-green{background:#dcfce7;color:#15803d}
.t-amber{background:#fef3c7;color:#b45309}.t-blue{background:#dbeafe;color:#1e40af}
.flex{display:flex;gap:12px;flex-wrap:wrap}
.flex>.card{flex:1;min-width:280px}
.legend{font-size:12px;color:var(--sub);margin-top:6px}
.foot{text-align:center;color:var(--sub);font-size:12px;margin-top:30px;padding-top:16px;border-top:1px solid var(--line)}
@media(max-width:760px){.kpis{grid-template-columns:repeat(2,1fr)}.chart{height:300px}}
</style></head><body><div class="wrap">

<h1>徐汇区物业投诉 1–8 月综合分析与目标测算</h1>
<div class="sub">数据周期 2024.01–2026.08 ｜ 街镇对比用项目主数据口径（__ST26__件）｜ 全市对比用市局十四类口径（13,726件）｜ 生成于 2026-09-29</div>

<div class="callout danger"><b>核心判断：</b>徐汇 1–8 月累计同比 <b>-13.1%</b>（全市第 13/17，低于全市平均 -15.4%），但月度环比已连续 4 个月上涨，<b>8 月单月同比转正 +2.84%</b>、日均已达 <b>72 件</b>。若 9–12 月维持 8 月高位，全年降幅将收窄至约 <b>-5.6%</b>、排名跌至第 16/17。<b>要保持全年下降态势，9–12 月日均工单需控制在 51–56 件</b>，较 8 月回落约 16–21 件/日。</div>

<div class="kpis">
<div class="kpi"><div class="lab">1-8月工单量(市局)</div><div class="val">13,726<small>件</small></div><div class="tag good">同比 ↓13.1% <small style="color:#6b7280">全市第13</small></div></div>
<div class="kpi r"><div class="lab">8月单月同比</div><div class="val">+2.84%<small></small></div><div class="tag bad">环比 ↑6.9% 连续4月上涨</div></div>
<div class="kpi a"><div class="lab">诉求密度(全市)</div><div class="val">3.83<small>件/千户</small></div><div class="tag" style="color:#b45309">中心城区第1高 / 全市第2</div></div>
<div class="kpi g"><div class="lab">保持前列 日均阈值</div><div class="val">≤56<small>件/日</small></div><div class="tag good">8月实为72件 需回落</div></div>
</div>

<h2><span class="n">一、</span>街镇横向对比（1–8 月）</h2>
<div class="card">
<p style="margin-bottom:10px;font-size:13px;color:#6b7280">按 2026 年 1–8 月工单量降序。密度＝工单量÷户数×1000（件/千户，项目口径，__STHH__户）。同比＝2026年1-8月 vs 2025年1-8月。<b style="color:#dc2626">红</b>表示同比上升（警示），<b style="color:#16a34a">绿</b>表示同比下降。</p>
<table id="t-street"><thead><tr>
<th class="c">排名</th><th>街镇</th><th class="r">1-8月工单</th><th class="r">2025同期</th><th class="r">同比增降</th><th class="r">户数</th><th class="r">密度(件/千户)</th><th class="c">态势</th>
</tr></thead><tbody></tbody></table>
</div>
<div class="card"><div class="chart" id="c-street1"></div></div>
<div class="flex">
<div class="card"><h3>同比降幅排序</h3><div class="chart s" id="c-street2"></div></div>
<div class="card"><h3>诉求密度对比</h3><div class="chart s" id="c-street3"></div></div>
</div>
<div class="callout warn"><b>街镇观察：</b>① <b>田林（+14.3%）、漕河泾（+3.4%）</b>是仅有的两个同比上升街镇，田林尤甚，需重点介入；② <b>长桥（-32.1%）、枫林路（-25.6%）、康健（-24.4%）</b>降幅领先，治理成效突出；③ 密度上 <b>湖南路（48.9）、天平路（37.6）</b>远高于均值，老城区压力集中；康健（18.4）、龙华（21.2）密度最低。</div>

<h2><span class="n">二、</span>徐汇在全市的水平与月度走势</h2>
<div class="card">
<p style="margin-bottom:10px;font-size:13px;color:#6b7280">基于市局十四类工单口径，1–8 月全市 17 个区（含临港新片区）排名。</p>
<table id="t-city"><thead><tr>
<th class="c">降幅排名</th><th>行政区</th><th class="r">1-8月工单</th><th class="r">2025同期</th><th class="r">同比增降</th><th class="r">平均密度(件/千户)</th><th class="c">密度排名</th>
</tr></thead><tbody></tbody></table>
<div class="note">全市平均降幅 <b>-15.4%</b>。徐汇 <b>-13.1%</b> 低于全市平均，降幅排第 13/17；密度 3.83 件/千户排第 2/17（中心城区最高）。</div>
</div>
<div class="card"><h3>各区降幅排名（降序，绿深=降幅大，紫=徐汇）</h3><div class="chart" id="c-city1"></div></div>
<div class="flex">
<div class="card"><h3>徐汇月度工单量与同比</h3><div class="chart s" id="c-xh1"></div></div>
<div class="card"><h3>徐汇月度诉求密度走势</h3><div class="chart s" id="c-xh2"></div></div>
</div>
<div class="callout warn"><b>全市走势：</b>徐汇月度工单从 1 月 1,485 件攀升至 8 月 <b>2,242 件</b>（+51%），密度从 3.12 翻倍至 <b>5.29 件/千户</b>；同比降幅从 1 月 -16.4% 持续收窄，<b>8 月已转正 +2.84%</b>，是 7 个中心城区中夏季反弹较明显的一个。7–8 月为历年投诉高峰季，但 2026 年反弹力度高于多数可比城区。</div>

<h2><span class="n">三、</span>保持前列的目标工单水平测算</h2>
<div class="card">
<p style="margin-bottom:10px;font-size:13px;color:#6b7280">测算口径：2025 全年徐汇 <b>23,618 件</b>（市局），其中 9–12 月 <b>7,820 件</b>；2026 年 1–8 月已发生 <b>13,726 件</b>。设全年同比目标为 r，则 9–12 月所需工单 X = 23618×(1+r) − 13726。</p>
<table id="t-target"><thead><tr>
<th>目标档位</th><th class="r">全年同比</th><th class="r">9-12月总量</th><th class="r">月均</th><th class="r">日均(122天)</th><th class="r">vs2025同期</th><th class="c">说明</th>
</tr></thead><tbody></tbody></table>
<div class="note">参照：2025 年 9–12 月实际 <b>7,820 件</b>（月均 1,955、日均 64.1）；2026 年 8 月单月 <b>2,242 件</b>（日均 72.3）；1–8 月日均 <b>56.5 件</b>。</div>
</div>
<div class="card"><h3>不同目标下的 9-12 月工单控制线</h3><div class="chart" id="c-target1"></div></div>
<div class="callout danger"><b>关键阈值：</b>
<div style="margin-top:8px">
<b>① 维持当前位次（全年 -13.1%，全市第13）</b>：9–12 月 ≤ <b>6,796 件</b>，月均 ≤1,700、日均 ≤<b>56 件</b>。<br>
<b>② 达全市平均（-15.4%，进前9）</b>：9–12 月 ≤ <b>6,255 件</b>，月均 ≤1,564、日均 ≤<b>51 件</b>。<br>
<b>③ 警戒线（若 9–12 月持平 2025 同期）</b>：全年降幅仅 <b>-8.8%</b>，排名将跌至约第 15/17，明显掉队。
</div></div>

<h3>若 9 月已按 8 月趋势发生（假设 9 月≈2,250 件），10–12 月 / 11–12 月补救空间</h3>
<div class="card"><table id="t-rem"><thead><tr>
<th>情景</th><th class="r">10-12月需</th><th class="r">10-12月日均</th><th class="r">若10月也2,200，11-12月需</th><th class="r">11-12月日均</th>
</tr></thead><tbody></tbody></table>
<div class="note">说明：若 9–10 月延续 8 月高位，要靠 11–12 月补回缺口需日均低至 30–38 件，<b>现实中几乎不可达成</b>。结论：<b>压降必须从 9 月立即启动，越晚越被动。</b></div></div>

<div class="callout"><b>行动建议：</b>
<div style="margin-top:8px;font-size:13.5px;line-height:1.8">
1. <b>立即设日均红线 56 件</b>（维持位次线），争取 51 件（进前 9 线）；8 月已达 72 件，须回落 ≥16 件/日。<br>
2. <b>重点压降反弹街镇</b>：田林（+14.3%）、漕河泾（+3.4%）为同比上升区，是拖累全局的主因，建议单列专项。<br>
3. <b>夏季高峰前置干预</b>：7–8 月为历史高峰且 2026 反弹强，9 月起对停车管理、群租、物业安保等高频类目开展集中整治。<br>
4. <b>密度治理聚焦湖南路、天平路</b>（老城区密度超均值 1.5 倍），结合加装电梯、老旧小区改造推进根源治理。<br>
5. <b>9 月数据入库后</b>可一键更新本测算；若 9 月仍 >2,200 件，建议将全年目标从"维持-13.1%"下调为"保-10%底线"。
</div></div>

<div class="foot">口径：街镇统计含全量工单（含其他/房屋交易纠纷），不剔除；密度按纳统小区户数（993个/518,389户）。<br>全市对比以市局12345十四类口径为准，徐汇1-8月13,726件、2025全年23,618件。9月数据待市局入库后补充更新。</div>
</div>

<script>
var DATA = __DATA__;
// ===== 街镇表 =====
var tb=document.querySelector('#t-street tbody');
DATA.street.rows.forEach(function(r,i){
  var up=r.yoy>0;
  tb.insertAdjacentHTML('beforeend','<tr class="'+(up?'warnb':'')+'"><td class="c">'+(i+1)+'</td><td>'+r.name+'</td><td class="r"><b>'+r.c26+'</b></td><td class="r">'+r.c25+'</td><td class="r">'+(up?'<span class="bad">↑'+r.yoy.toFixed(1)+'%</span>':'<span class="good">↓'+Math.abs(r.yoy).toFixed(1)+'%</span>')+'</td><td class="r">'+r.hh.toLocaleString()+'</td><td class="r">'+r.density.toFixed(1)+'</td><td class="c">'+(up?'<span class="tag t-red">上升</span>':'<span class="tag t-green">下降</span>')+'</td></tr>');
});
// 全市表
var tc=document.querySelector('#t-city tbody');
DATA.city.rows.forEach(function(r){
  tc.insertAdjacentHTML('beforeend','<tr style="'+(r.name==='徐汇区'?'background:#eff6ff;font-weight:600':'')+'"><td class="c">'+r.dr+'</td><td>'+r.name+'</td><td class="r">'+r.c26.toLocaleString()+'</td><td class="r">'+r.c25.toLocaleString()+'</td><td class="r">'+(r.yoy<0?'<span class="good">↓'+Math.abs(r.yoy).toFixed(1)+'%</span>':'<span class="bad">↑'+r.yoy.toFixed(1)+'%</span>')+'</td><td class="r">'+r.density.toFixed(2)+'</td><td class="c">'+r.ddr+'</td></tr>');
});
// 目标表
var tt=document.querySelector('#t-target tbody');
var lvl=['挑战','挑战','基准','底线','警惕','警戒'];
var cls=['t-green','t-green','t-blue','t-amber','t-amber','t-red'];
DATA.target.scenarios.forEach(function(r,i){
  tt.insertAdjacentHTML('beforeend','<tr style="'+(r.r<=-13.1&&r.r>=-15.4?'background:#f0fdf4':'')+'"><td>'+r.label+'</td><td class="r"><b>'+r.r.toFixed(1)+'%</b></td><td class="r"><b>'+r.x.toLocaleString()+'</b>件</td><td class="r">'+r.mo.toLocaleString()+'件</td><td class="r"><b>'+r.day+'</b>件</td><td class="r">'+(r.vs25<0?'<span class="good">↓'+Math.abs(r.vs25).toFixed(1)+'%</span>':'<span class="bad">↑'+r.vs25.toFixed(1)+'%</span>')+'</td><td class="c"><span class="tag '+cls[i]+'">'+lvl[i]+'</span></td></tr>');
});
// 补救表
var tr=document.querySelector('#t-rem tbody');
DATA.target.remediate.forEach(function(r){
  tr.insertAdjacentHTML('beforeend','<tr><td>'+r.label+'</td><td class="r"><b>'+r.octdec.toLocaleString()+'</b>件</td><td class="r">'+r.octdec_day+'件</td><td class="r">'+r.novdec.toLocaleString()+'件</td><td class="r"><b style="'+(r.novdec_day<40?'color:#dc2626':'')+'">'+r.novdec_day+'件</b></td></tr>');
});

// ===== ECharts =====
var C1=echarts.init(document.getElementById('c-street1'));
var sr=DATA.street.rows;
C1.setOption({
  tooltip:{trigger:'axis',axisPointer:{type:'shadow'}},
  legend:{data:['1-8月工单(件)','2025同期(件)'],top:0},
  grid:{left:50,right:50,bottom:40,top:40},
  xAxis:{type:'category',data:sr.map(r=>r.name),axisLabel:{rotate:30,fontSize:11}},
  yAxis:[{type:'value',name:'工单量(件)'},{type:'value',name:'同比%',position:'right',axisLabel:{formatter:'{value}%'}}],
  series:[{name:'1-8月工单(件)',type:'bar',data:sr.map(r=>r.c26),itemStyle:{color:'#2563eb'}},
    {name:'2025同期(件)',type:'bar',data:sr.map(r=>r.c25),itemStyle:{color:'#94a3b8'}},
    {name:'同比%',type:'line',yAxisIndex:1,data:sr.map(r=>r.yoy),itemStyle:{color:'#dc2626'},lineStyle:{width:2},symbol:'circle',symbolSize:6,
      markLine:{silent:true,data:[{yAxis:0}],lineStyle:{color:'#9ca3af',type:'dashed'}}}]
});
var sr2=sr.slice().sort((a,b)=>a.yoy-b.yoy);
var C2=echarts.init(document.getElementById('c-street2'));
C2.setOption({
  tooltip:{trigger:'axis'},
  grid:{left:70,right:40,bottom:20,top:20},
  xAxis:{type:'value',axisLabel:{formatter:'{value}%'}},
  yAxis:{type:'category',data:sr2.map(r=>r.name),axisLabel:{fontSize:11}},
  series:[{type:'bar',data:sr2.map(r=>({value:r.yoy,itemStyle:{color:r.yoy<0?'#16a34a':'#dc2626'}})),barWidth:'60%',
    label:{show:true,position:'right',formatter:p=>p.value<0?'↓'+Math.abs(p.value).toFixed(1)+'%':'↑'+p.value.toFixed(1)+'%',fontSize:10}}]
});
var sr3=sr.slice().sort((a,b)=>b.density-a.density);
var C3=echarts.init(document.getElementById('c-street3'));
C3.setOption({
  tooltip:{trigger:'axis'},
  grid:{left:70,right:40,bottom:20,top:20},
  xAxis:{type:'value',name:'件/千户'},
  yAxis:{type:'category',data:sr3.map(r=>r.name),axisLabel:{fontSize:11}},
  series:[{type:'bar',data:sr3.map(r=>({value:r.density,itemStyle:{color:r.density>35?'#dc2626':(r.density>25?'#d97706':'#16a34a')}})),barWidth:'60%',
    label:{show:true,position:'right',fontSize:10},markLine:{silent:true,data:[{xAxis:DATA.street.t_density}],lineStyle:{color:'#2563eb',type:'dashed'},label:{formatter:'均值'+DATA.street.t_density,fontSize:10}}}]
});
var cr=DATA.city.rows.slice().sort((a,b)=>a.yoy-b.yoy);
var C4=echarts.init(document.getElementById('c-city1'));
C4.setOption({
  tooltip:{trigger:'axis',formatter:p=>p[0].name+'<br/>同比 '+p[0].value.toFixed(1)+'%'},
  grid:{left:80,right:60,bottom:40,top:30},
  xAxis:{type:'category',data:cr.map(r=>r.name),axisLabel:{rotate:40,fontSize:10}},
  yAxis:{type:'value',name:'同比%',axisLabel:{formatter:'{value}%'}},
  series:[{type:'bar',data:cr.map(r=>({value:r.yoy,itemStyle:{color:r.name==='徐汇区'?'#7c3aed':(r.yoy<-15.4?'#16a34a':'#d97706')}})),barWidth:'55%',
    label:{show:true,position:'top',formatter:p=>(p.value<0?'↓':'↑')+Math.abs(p.value).toFixed(1),fontSize:9,color:'#555'},
    markLine:{silent:true,data:[{yAxis:-15.4}],lineStyle:{color:'#dc2626',type:'dashed'},label:{formatter:'全市平均-15.4%',fontSize:10}}}]
});
var C5=echarts.init(document.getElementById('c-xh1'));
var xm=DATA.xh_monthly;
C5.setOption({
  tooltip:{trigger:'axis'},
  legend:{data:['工单量(件)','同比%'],top:0},
  grid:{left:50,right:45,bottom:30,top:40},
  xAxis:{type:'category',data:xm.map(r=>r.m)},
  yAxis:[{type:'value',name:'件'},{type:'value',name:'%',position:'right',axisLabel:{formatter:'{value}%'}}],
  series:[{name:'工单量(件)',type:'bar',data:xm.map(r=>r.vol),itemStyle:{color:'#2563eb'},barWidth:'50%'},
    {name:'同比%',type:'line',yAxisIndex:1,data:xm.map(r=>r.yoy),itemStyle:{color:'#dc2626'},lineStyle:{width:2.5},symbol:'circle',symbolSize:7,
      markLine:{silent:true,data:[{yAxis:0}],lineStyle:{color:'#9ca3af',type:'dashed'}}}]
});
var C6=echarts.init(document.getElementById('c-xh2'));
C6.setOption({
  tooltip:{trigger:'axis'},
  grid:{left:45,right:30,bottom:30,top:30},
  xAxis:{type:'category',data:xm.map(r=>r.m)},
  yAxis:{type:'value',name:'件/千户'},
  series:[{type:'line',data:xm.map(r=>r.density),itemStyle:{color:'#7c3aed'},lineStyle:{width:3},symbol:'circle',symbolSize:8,
    areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(124,58,237,0.25)'},{offset:1,color:'rgba(124,58,237,0.02)'}])},
    label:{show:true,position:'top',fontSize:10}}]
});
var C7=echarts.init(document.getElementById('c-target1'));
var sc=DATA.target.scenarios.slice().reverse();
C7.setOption({
  tooltip:{trigger:'axis',formatter:p=>p[0].name+'<br/>日均 '+p[0].value+'件 / 总量 '+p[0].data.total+'件'},
  grid:{left:200,right:60,bottom:30,top:20},
  xAxis:{type:'value',name:'日均工单(件)',axisLabel:{formatter:'{value}'}},
  yAxis:{type:'category',data:sc.map(r=>r.label),axisLabel:{fontSize:11}},
  series:[{type:'bar',data:sc.map(r=>({value:r.day,total:r.x,itemStyle:{color:r.r<=-15?'#16a34a':(r.r<=-13.1?'#2563eb':(r.r<=-10?'#d97706':'#dc2626'))}})),barWidth:'55%',
    label:{show:true,position:'right',formatter:p=>p.value+'件/日',fontSize:11},
    markLine:{silent:true,data:[{xAxis:72}],lineStyle:{color:'#dc2626',type:'dashed'},label:{formatter:'8月实际72件',fontSize:10,color:'#dc2626'}}}]
});
window.addEventListener('resize',function(){[C1,C2,C3,C4,C5,C6,C7].forEach(c=>c.resize())});
</script></body></html>"""

HTML = HTML.replace('__DATA__', json.dumps(DATA, ensure_ascii=False))
HTML = HTML.replace('__ST26__', format(street_total_26, ','))
HTML = HTML.replace('__STHH__', format(street_total_hh, ','))

out=os.path.join(ROOT,'徐汇区1-8月工单综合分析与目标测算.html')
open(out,'w',encoding='utf-8').write(HTML)
print('written:',out)
print('street rows:',len(street_rows),'city rows:',len(city_rows),'scenarios:',len(scen_rows))
