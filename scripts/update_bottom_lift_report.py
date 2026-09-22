# -*- coding: utf-8 -*-
"""
《底部抬升小区热线数据分析报告》口径统一改造

改造内容：
  1. 全部"2026年上半年 / 2026H1"口径 -> "2026年1-8月"，总数与同比同步重算
  2. 三、街道分布表 补"2026年1-8月总数"与"2026年1-8月同比"两列
  3. 七、重点小区榜单 列名 2025H1/2026H1 -> 2025年1-8月/2026年1-8月（数据同步重算）
  4. 一、总体概况 增加 pp（百分点）含义注释
  5. 月度图补 2026年7-8月数据

数据源：scripts/bottom_lift_2026_8m.json（由 recalc_bottom_lift_8m.py 生成）
可重复执行（幂等：已改过的片段会跳过）。
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, "底部抬升小区热线数据分析报告.html")
DATA = os.path.join(BASE, "scripts", "bottom_lift_2026_8m.json")

R = json.load(open(DATA, encoding="utf-8"))
html = open(HTML, encoding="utf-8").read()

done, skipped = [], []


def rep(old, new, tag):
    """精确替换，old 已存在则替换；不存在则记录跳过（幂等）"""
    global html
    if old in html:
        html = html.replace(old, new, 1)
        done.append(tag)
    elif new in html:
        skipped.append(tag + "(已改)")
    else:
        raise SystemExit(f"[FAIL] 未找到片段: {tag}\n{old[:200]}")


def fmt_pct(v, plus=False):
    if v is None:
        return "—"
    s = f"{v:+.1f}%" if plus else f"{v}%"
    return s


def cls_of(v):
    if v is None:
        return "trend-flat"
    return "trend-down" if v < 0 else ("trend-up" if v > 0 else "trend-flat")


def num(v):
    return f"{v:,}" if isinstance(v, int) else str(v)


# ============================================================
# 0. 页头 meta
# ============================================================
rep(
    '<div class="meta">数据周期：2024年-2026年6月 · 匹配成功78个小区 · 占全区投诉量18.0%</div>',
    '<div class="meta">数据周期：2024年1月-2026年8月 · 匹配成功78个小区 · 2026年1-8月占全区投诉量17.1%</div>',
    "页头meta",
)

# ============================================================
# 一、总体概况
# ============================================================
rep(
    '<div class="stat-card"><div class="num down">-19.2%</div><div class="label">2026上半年同比</div></div>',
    '<div class="stat-card"><div class="num down">-16.9%</div><div class="label">2026年1-8月同比</div></div>',
    "顶部卡片-同比",
)
rep(
    """      <div class="kpi-card">
        <div class="kpi-val green">-19.2%</div>
        <div class="kpi-label">2026上半年同比</div>
        <div class="kpi-sub">追平全区-18.5%</div>
      </div>""",
    """      <div class="kpi-card">
        <div class="kpi-val green">-16.9%</div>
        <div class="kpi-label">2026年1-8月同比</div>
        <div class="kpi-sub">优于全区-13.1%</div>
      </div>""",
    "KPI卡-同比",
)
rep(
    '<strong>核心发现：</strong>底部抬升小区2025年同比仅降5.5%，远低于全区19.9%的降幅，说明"硬骨头"治理难度大。'
    '但2026年上半年降幅扩大至19.2%，首次追平全区水平，治理攻坚成效开始显现。',
    '<strong>核心发现：</strong>底部抬升小区2025年同比仅降5.5%，远低于全区19.9%的降幅，说明"硬骨头"治理难度大。'
    '但2026年1-8月降幅扩大至16.9%，首次反超全区水平（-13.1%），降幅比全区多3.8个百分点，治理攻坚成效开始显现。',
    "核心发现",
)

# 一、对比表 三行
ov, ax, sh, yoy, pp = R["overall"], R["all_xuhui"], R["share"], R["yoy"], R["pp"]
rep(
    """      <tr>
        <td>2025年上半年</td>
        <td>2,057件</td>
        <td>11,516件</td>
        <td>占比17.9%</td>
        <td>—</td>
      </tr>
      <tr>
        <td>2026年上半年</td>
        <td>1,662件</td>
        <td>9,387件</td>
        <td>占比17.7%</td>
        <td>占比微降</td>
      </tr>
      <tr>
        <td>2026上半年同比</td>
        <td class="trend-down">-19.2%</td>
        <td class="trend-down">-18.5%</td>
        <td class="trend-down">-0.7pp</td>
        <td>追平全区</td>
      </tr>
    </table>""",
    f"""      <tr>
        <td>2025年1-8月</td>
        <td>{num(ov['m8_2025'])}件</td>
        <td>{num(ax['m8_2025'])}件</td>
        <td>占比{sh['m8_2025']}%</td>
        <td>—</td>
      </tr>
      <tr>
        <td>2026年1-8月</td>
        <td>{num(ov['m8_2026'])}件</td>
        <td>{num(ax['m8_2026'])}件</td>
        <td>占比{sh['m8_2026']}%</td>
        <td>占比下降</td>
      </tr>
      <tr>
        <td>2026年1-8月同比</td>
        <td class="trend-down">{fmt_pct(yoy['m8_2026_vs_m8_2025'])}</td>
        <td class="trend-down">{fmt_pct(yoy['all_m8_2026'])}</td>
        <td class="trend-down">{fmt_pct(pp['m8_2026_vs_all'], True)}</td>
        <td>优于全区</td>
      </tr>
    </table>
    <p style="font-size:12px;color:#888;margin-top:6px;line-height:1.7;">
      注：<b>pp = 百分点（percentage point）</b>，指两个百分数<b>直接相减</b>的差值，而非百分比的百分比。
      例：2025年底部抬升同比 -5.5%、全区 -19.9%，差距 =（-5.5）-（-19.9）＝ <b>+14.4pp</b>，
      表示底部抬升降幅比全区<b>少</b>14.4个百分点（治理滞后）；
      2026年1-8月为（-16.9）-（-13.1）＝ <b>-3.8pp</b>，表示降幅比全区<b>多</b>3.8个百分点（优于全区）。
    </p>""",
    "总体对比表+pp注释",
)

# ============================================================
# 二、月度趋势
# ============================================================
rep(
    '<strong>趋势解读：</strong>① 2024年投诉量"前低后高"，11月达峰值538件；② 2025年治理介入后呈"中间高两端低"，'
    '3-4月仍高位；③ 2026年上半年整体下行，5-6月略有抬头，需持续关注。',
    '<strong>趋势解读：</strong>① 2024年投诉量"前低后高"，11月达峰值546件；② 2025年治理介入后呈"中间高两端低"，'
    '3-4月仍高位；③ 2026年1-8月整体下行，月均294件（2025年同期354件），'
    '但7月（347件）、8月（345件）连续两月抬头，同比压力仍在，需持续关注。',
    "月度趋势解读",
)

# 月度图数据（补 2026年7-8月，并按78小区口径校准）
m24, m25, m26 = R["monthly"]["2024"], R["monthly"]["2025"], R["monthly"]["2026"]
rows = []
for i in range(12):
    v26 = m26[i] if m26[i] is not None else 0
    rows.append(f"  {i+1}: {{ '2024': {m24[i]}, '2025': {m25[i]}, '2026': {v26} }}")
rep(
    """var monthlyData = {
  1: { '2024': 303, '2025': 318, '2026': 254 },
  2: { '2024': 168, '2025': 276, '2026': 164 },
  3: { '2024': 374, '2025': 434, '2026': 269 },
  4: { '2024': 360, '2025': 364, '2026': 283 },
  5: { '2024': 369, '2025': 317, '2026': 333 },
  6: { '2024': 414, '2025': 320, '2026': 342 },
  7: { '2024': 368, '2025': 376, '2026': 344 },
  8: { '2024': 320, '2025': 389, '2026': 0 },
  9: { '2024': 411, '2025': 416, '2026': 0 },
  10: { '2024': 382, '2025': 330, '2026': 0 },
  11: { '2024': 538, '2025': 358, '2026': 0 },
  12: { '2024': 459, '2025': 305, '2026': 0 }
};
var maxVal = 538;""",
    "var monthlyData = {\n" + ",\n".join(rows) + "\n};\nvar maxVal = 546;",
    "月度图数据",
)

# ============================================================
# 三、街道分布（补 2026年1-8月 总数 + 同比）
# ============================================================
def street_eval(r):
    y8, y25 = r["yoy_m8"], r["yoy_2025"]
    if y8 is None:
        return '<span style="color:#757575; font-weight:700;">— 无同期基数</span>'
    if y25 is not None and y25 > 0 and y8 <= -10:
        return '<span style="color:#f57c00; font-weight:700;">⚡ 快速改善</span>'
    if y8 <= -30:
        return '<span style="color:#2e7d32; font-weight:700;">⭐ 成效显著</span>'
    if y8 <= -10:
        return '<span style="color:#388e3c; font-weight:700;">✓ 效果良好</span>'
    if y8 < 0:
        return '<span style="color:#fbc02d; font-weight:700;">⚠ 初见成效</span>'
    if y8 < 30:
        return '<span style="color:#e65100; font-weight:700;">🔴 出现反弹</span>'
    return '<span style="color:#c62828; font-weight:700;">🚨 严重恶化</span>'


st_rows = []
for r in R["street_stats"]:
    st_rows.append(f"""      <tr>
        <td>{r['street']}</td>
        <td>{r['n_community']}个</td>
        <td>{num(r['y2024'])}</td>
        <td>{num(r['y2025'])}</td>
        <td class="{cls_of(r['yoy_2025'])}">{fmt_pct(r['yoy_2025'], True)}</td>
        <td>{num(r['m8_2026'])}</td>
        <td class="{cls_of(r['yoy_m8'])}">{fmt_pct(r['yoy_m8'], True)}</td>
        <td>{street_eval(r)}</td>
      </tr>""")

i = html.index("      <tr>\n        <th>街道</th>")
j = html.index("    </table>", i) + len("    </table>")
html = html[:i] + f"""      <tr>
        <th>街道</th>
        <th>重点小区数</th>
        <th>2024年</th>
        <th>2025年</th>
        <th>2025同比</th>
        <th>2026年1-8月</th>
        <th>2026年1-8月同比</th>
        <th>治理评价</th>
      </tr>
""" + "\n".join(st_rows) + "\n    </table>" + html[j:]
done.append("街道分布表")

rep(
    """    <div class="highlight">
      <strong>街道梯队：</strong>
      第一梯队（降幅>30%）：凌云路、漕河泾、康健新村 — 治理经验可复制推广；
      第二梯队（降幅10-30%）：斜土路 — 稳步推进；
      第三梯队（先升后降）：湖南路、徐家汇、华泾 — 2026年发力见效；
      需关注：长桥、田林、枫林路、天平路 — 降幅有限；
      预警：龙华（反弹）、虹梅路（严重恶化）— 需重点督导。
    </div>""",
    """    <div class="highlight">
      <strong>街道梯队（按2026年1-8月同比）：</strong>
      第一梯队（降幅&gt;30%）：康健新村(-52.4%)、华泾(-43.3%)、湖南路(-32.5%) — 治理经验可复制推广；
      第二梯队（降幅10-30%）：徐家汇(-27.9%)、斜土路(-23.6%)、凌云路(-23.4%)、枫林路(-12.5%)、长桥(-10.1%) — 稳步推进；
      需关注：漕河泾(-2.8%) — 较2025年的-30.8%大幅收窄，降幅动能明显减弱；
      预警：田林(+11.2%)、天平路(+17.6%)出现反弹，龙华(+37.5%)、虹梅路(+113.3%)严重恶化 — 需重点督导。
    </div>""",
    "街道梯队",
)

# ============================================================
# 四、问题类别（2026年1-8月 + 同比）
# ============================================================
def cat_star(v):
    if v is None or v >= 0:
        return '<span style="color:#e65100;">★★★★★ 最难</span>'
    if v >= -15:
        return '<span style="color:#e65100;">★★★★☆ 难</span>'
    if v >= -30:
        return '<span style="color:#fbc02d;">★★★☆☆ 中等</span>'
    if v >= -45:
        return '<span style="color:#388e3c;">★★☆☆☆ 较易</span>'
    return '<span style="color:#388e3c;">★☆☆☆☆ 最易</span>'


KEEP_CATS = ["停车管理", "房屋维修", "邻里纠纷", "业主大会/业委会", "消防管理",
             "房屋违规使用", "物业安保", "旧住房改造", "清洁卫生", "群租管理"]
cmap = {c["category"]: c for c in R["category_stats"]}
cat_rows = []
for k in KEEP_CATS:
    c = cmap[k]
    cat_rows.append(
        f'<tr><td>{c["category"]}</td><td>{num(c["y2024"])}</td><td>{num(c["y2025"])}</td>'
        f'<td>{num(c["m8_2026"])}</td>'
        f'<td class="{cls_of(c["yoy_2025"])}">{fmt_pct(c["yoy_2025"], True)}</td>'
        f'<td class="{cls_of(c["yoy_m8"])}">{fmt_pct(c["yoy_m8"], True)}</td>'
        f'<td>{cat_star(c["yoy_m8"])}</td></tr>')

i = html.index("      <table>\n        <tr>\n          <th>问题类别</th>")
j = html.index("    </table>", i) + len("    </table>")
html = html[:i] + """      <table>
        <tr>
          <th>问题类别</th>
          <th>2024年</th>
          <th>2025年</th>
          <th>2026年1-8月</th>
          <th>2025同比</th>
          <th>2026年1-8月同比</th>
          <th>治理难度</th>
        </tr>
        """ + "\n        ".join(cat_rows) + """
    </table>""" + html[j:]
done.append("问题类别表")

# ============================================================
# 五、矛盾类型
# ============================================================
ct = {c["type"]: c for c in R["contradiction_stats"]}
rep('<div class="contra-num" style="color:#1565c0;">23个</div>',
    f'<div class="contra-num" style="color:#1565c0;">{ct["1"]["n_community"]}个</div>', "矛盾卡1数量")
rep('<div class="contra-num" style="color:#e64a19;">39个</div>',
    f'<div class="contra-num" style="color:#e64a19;">{ct["2"]["n_community"]}个</div>', "矛盾卡2数量")
rep('<div class="contra-change trend-down">2025同比 -15.2%</div>',
    f'<div class="contra-change trend-down">2026年1-8月同比 {fmt_pct(ct["1"]["yoy_m8"])}</div>', "矛盾卡1同比")
rep('<div class="contra-change trend-down">2025同比 -2.0%</div>',
    f'<div class="contra-change trend-down">2026年1-8月同比 {fmt_pct(ct["2"]["yoy_m8"])}</div>', "矛盾卡2同比")
rep('<div class="contra-change trend-down">2025同比 -12.2%</div>',
    f'<div class="contra-change trend-up">2026年1-8月同比 {fmt_pct(ct["3"]["yoy_m8"], True)}</div>', "矛盾卡3同比")

CT_FEATURE = {"1": "约谈物业、强化履约、引入竞争",
              "2": "量大面广、旧改带动、维修资金",
              "3": "街道介入、依法换届、能力建设"}
ct_rows = []
for t in ["1", "2", "3"]:
    c = ct[t]
    ct_rows.append(f"""        <tr>
          <td>{c['label']}</td>
          <td>{c['n_community']}个</td>
          <td>{num(c['y2024'])}</td>
          <td>{num(c['y2025'])}</td>
          <td>{num(c['m8_2026'])}</td>
          <td class="{cls_of(c['yoy_2025'])}">{fmt_pct(c['yoy_2025'], True)}</td>
          <td class="{cls_of(c['yoy_m8'])}">{fmt_pct(c['yoy_m8'], True)}</td>
          <td>{CT_FEATURE[t]}</td>
        </tr>""")

i = html.index("      <table>\n        <tr>\n          <th>矛盾类型</th>")
j = html.index("    </table>", i) + len("    </table>")
html = html[:i] + """      <table>
        <tr>
          <th>矛盾类型</th>
          <th>小区数</th>
          <th>2024年</th>
          <th>2025年</th>
          <th>2026年1-8月</th>
          <th>2025同比</th>
          <th>2026年1-8月同比</th>
          <th>治理特征</th>
        </tr>
""" + "\n".join(ct_rows) + """
    </table>""" + html[j:]
done.append("矛盾类型表")

share2 = round(ct["2"]["m8_2026"] / ov["m8_2026"] * 100, 1)
rep(
    '<strong>结论：</strong>二类矛盾小区数量最多（39个）、投诉量最大（占66.6%），但同比降幅最小（-2.0%），'
    '是底部抬升的"主战场"和"硬骨头"。一类矛盾降幅最大（-15.2%），说明物业收费和服务质量问题通过约谈和强化管理较易改善。',
    f'<strong>结论：</strong>2026年1-8月二类矛盾（{ct["2"]["n_community"]}个小区、{num(ct["2"]["m8_2026"])}件、'
    f'占{share2}%）受益于旧改与维修资金推进，同比降幅达{fmt_pct(ct["2"]["yoy_m8"])}，'
    f'已由"硬骨头"转为改善主力；三类矛盾（{ct["3"]["n_community"]}个小区、{num(ct["3"]["m8_2026"])}件）'
    f'同比{fmt_pct(ct["3"]["yoy_m8"], True)}，是<b>唯一上升</b>的矛盾类型，'
    '业委会组建与换届治理成为新的攻坚方向。',
    "矛盾结论",
)

# ============================================================
# 六、小区级变化（第二面板 -> 2026年1-8月）
# ============================================================
cc = R["community_change_m8"]
rep(
    '<div class="progress-title">2026上半年 vs 2025上半年（74个有效对比）</div>',
    f'<div class="progress-title">2026年1-8月 vs 2025年1-8月（{cc["valid"]}个有效对比）</div>',
    "小区级面板标题",
)
rep(
    f"""          <div class="progress-bar-label"><span>投诉下降（改善）</span><span class="val">43个 · 58.1%</span></div>
          <div class="progress-bar-bg"><div class="progress-bar-fill pb-green" style="width:58.1%;"></div></div>""",
    f"""          <div class="progress-bar-label"><span>投诉下降（改善）</span><span class="val">{cc['down']}个 · {cc['down_pct']}%</span></div>
          <div class="progress-bar-bg"><div class="progress-bar-fill pb-green" style="width:{cc['down_pct']}%;"></div></div>""",
    "小区级-改善条",
)
rep(
    f"""          <div class="progress-bar-label"><span>投诉上升（恶化）</span><span class="val">29个 · 39.2%</span></div>
          <div class="progress-bar-bg"><div class="progress-bar-fill pb-red" style="width:39.2%;"></div></div>""",
    f"""          <div class="progress-bar-label"><span>投诉上升（恶化）</span><span class="val">{cc['up']}个 · {cc['up_pct']}%</span></div>
          <div class="progress-bar-bg"><div class="progress-bar-fill pb-red" style="width:{cc['up_pct']}%;"></div></div>""",
    "小区级-恶化条",
)
rep(
    f"""          <div class="progress-bar-label"><span>基本持平</span><span class="val">2个 · 2.7%</span></div>
          <div class="progress-bar-bg"><div class="progress-bar-fill pb-yellow" style="width:2.7%;"></div></div>""",
    f"""          <div class="progress-bar-label"><span>基本持平</span><span class="val">{cc['flat']}个 · {cc['flat_pct']}%</span></div>
          <div class="progress-bar-bg"><div class="progress-bar-fill pb-yellow" style="width:{cc['flat_pct']}%;"></div></div>""",
    "小区级-持平条",
)
rep(
    '<strong>关键转折：</strong>改善小区比例从2025年的50.7%提升至2026上半年的58.1%，恶化小区从46.7%降至39.2%。'
    '底部抬升攻坚行动正在由"点上突破"转向"面上见效"。',
    f'<strong>关键判断：</strong>2026年1-8月改善小区{cc["down"]}个（占有效对比{cc["down_pct"]}%），'
    f'恶化{cc["up"]}个（{cc["up_pct"]}%）。与2025年全年相比改善面基本持平（50.7%），'
    f'但恶化面仍超四成，底部抬升攻坚处于"拉锯阶段"，尚未形成面上逆转。'
    '（有效对比：两期合计&gt;0；判定阈值：±5%）',
    "关键转折",
)

# ============================================================
# 七、重点小区榜单（列名 2025H1/2026H1 -> 2025年1-8月/2026年1-8月）
# ============================================================
def rank_cls(i):
    return {1: "rank-1", 2: "rank-2", 3: "rank-3"}.get(i, "rank-other")


vol_rows = []
for i2, r in enumerate(R["top10_volume_m8"], 1):
    vol_rows.append(
        f'<tr><td><span class="comm-rank {rank_cls(i2)}">{i2}</span></td><td>{r["name"]}</td>'
        f'<td>{r["street"]}</td><td>{num(r["m8_2025"])}</td><td>{num(r["m8_2026"])}</td>'
        f'<td class="{cls_of(r["yoy_m8"])}">{fmt_pct(r["yoy_m8"], True)}</td></tr>')

imp_rows = []
for i2, r in enumerate(R["top10_improve_m8"], 1):
    imp_rows.append(
        f'<tr><td><span class="comm-rank {rank_cls(i2)}">{i2}</span></td><td>{r["name"]}</td>'
        f'<td>{r["street"]}</td><td>{num(r["m8_2025"])}</td><td>{num(r["m8_2026"])}</td>'
        f'<td class="trend-down">{fmt_pct(r["yoy_m8"])}</td></tr>')

i = html.index("    <div class=\"two-col\">\n      <div>\n        <h4 style=\"font-size:13px; color:#c62828;")
j = html.index("  <!-- ===== 七-2、2026年近期专项分析 ===== -->")
html = html[:i] + f"""    <div class="two-col">
      <div>
        <h4 style="font-size:13px; color:#c62828; margin-bottom:8px;">🚨 投诉量Top10（2026年1-8月）</h4>
        <table class="comm-table">
          <tr><th>排名</th><th>小区</th><th>街道</th><th>2025年1-8月</th><th>2026年1-8月</th><th>同比</th></tr>
          {"".join(vol_rows)}
        </table>
      </div>

      <div>
        <h4 style="font-size:13px; color:#2e7d32; margin-bottom:8px;">✅ 改善幅度Top10（2026年1-8月，基数≥15件）</h4>
        <table class="comm-table">
          <tr><th>排名</th><th>小区</th><th>街道</th><th>2025年1-8月</th><th>2026年1-8月</th><th>降幅</th></tr>
          {"".join(imp_rows)}
        </table>
      </div>
    </div>
  </div>

""" + html[j:]
done.append("重点小区榜单")

# ============================================================
# 七-2、2026年1-8月专项分析（整节重算）
# ============================================================
vn = R["vs_normal"]
cat_sorted = sorted([cmap[k] for k in KEEP_CATS], key=lambda c: (c["yoy_m8"] if c["yoy_m8"] is not None else 999))


def cat_tag(v):
    if v is None:
        return "⚪ 无同期基数"
    if v <= -30:
        return "🟢 大幅改善"
    if v <= -10:
        return "🟢 改善"
    if v < 0:
        return "🟡 改善偏弱"
    return "🔴 逆势上升"


cat_tr = "\n".join(
    f'      <tr><td>{c["category"]}</td><td>{num(c["m8_2026"])}件</td><td>{num(c["m8_2025"])}件</td>'
    f'<td style="color:{"#00a854" if (c["yoy_m8"] or 0) < 0 else "#ff4d4f"};font-weight:700;">{fmt_pct(c["yoy_m8"], True)}</td>'
    f'<td>{cat_tag(c["yoy_m8"])}</td></tr>' for c in cat_sorted)


def comm_tag(v):
    if v is None:
        return "⚪ 持平"
    if v <= -30:
        return "🟢 大幅改善"
    if v <= -10:
        return "🟢 改善"
    if v < 0:
        return "🟡 改善偏弱"
    if v < 50:
        return "🔴 恶化"
    return "🔴 急剧恶化"


comm_tr = "\n".join(
    f'      <tr><td>{i2}</td><td>{r["name"]}</td><td>{r["street"]}</td>'
    f'<td>{num(r["m8_2026"])}件</td><td>{num(r["m8_2025"])}件</td>'
    f'<td style="color:{"#00a854" if (r["yoy_m8"] or 0) < 0 else "#ff4d4f"};font-weight:700;">{fmt_pct(r["yoy_m8"], True)}</td>'
    f'<td>{comm_tag(r["yoy_m8"])}</td></tr>'
    for i2, r in enumerate(R["top10_volume_m8"], 1))

worse = [r for r in R["top10_volume_m8"] if (r["yoy_m8"] or 0) > 0]
worse_txt = "、".join(f'{r["name"]}（{fmt_pct(r["yoy_m8"], True)}）' for r in worse)
risen = [c for c in cat_sorted if (c["yoy_m8"] or 0) > 0]
risen_txt = "、".join(f'{c["category"]}（{fmt_pct(c["yoy_m8"], True)}）' for c in risen)

i = html.index("  <!-- ===== 七-2、2026年近期专项分析 ===== -->")
j = html.index("  <!-- ===== 八、结论与建议 ===== -->")
html = html[:i] + f"""  <!-- ===== 七-2、2026年1-8月专项分析 ===== -->
  <div class="section">
    <div class="section-title"><span class="icon">📅</span>七-2、2026年1-8月专项分析</div>
    <p class="desc">将2026年1-8月数据单独提取，与2025年同期对比，聚焦底部抬升小区的"当下治理态势"。
      口径说明：本节与全报告一致，采用<b>全量热线工单口径</b>（底部抬升78个匹配小区 / 其余1,298个普通小区）。</p>

    <div class="highlight" style="background:#e8f5e9; border-left-color:#2e7d32;">
      <strong>核心发现：</strong>2026年1-8月底部抬升小区投诉<b>{num(vn["bl_m8_2026"])}件</b>，
      同比2025年1-8月（{num(vn["bl_m8_2025"])}件）<strong>下降{abs(vn["bl_yoy"])}%</strong>，
      降幅大于普通小区（{fmt_pct(vn["normal_yoy"])}），<strong>底部抬升专项治理成效优于面上</strong>。
    </div>

    <h4 style="font-size:14px; color:#bf360c; margin:15px 0 8px;">7-2.1 底部抬升 vs 普通小区对比</h4>
    <table class="data-table">
      <tr><th>类型</th><th>小区数</th><th>2026年1-8月</th><th>2025年1-8月</th><th>同比</th><th>小区均值</th><th>改善幅度</th></tr>
      <tr style="background:#e8f5e9;"><td>底部抬升</td><td>{R["matched"]}</td><td>{num(vn["bl_m8_2026"])}件</td>
        <td>{num(vn["bl_m8_2025"])}件</td><td style="color:#00a854;font-weight:700;">{fmt_pct(vn["bl_yoy"])}</td>
        <td>{vn["bl_avg"]}件</td><td style="color:#00a854;">优于普通{abs(vn["pp"])}pp</td></tr>
      <tr><td>普通小区</td><td>{num(vn["normal_comm"])}</td><td>{num(vn["normal_m8_2026"])}件</td>
        <td>{num(vn["normal_m8_2025"])}件</td><td style="color:#00a854;">{fmt_pct(vn["normal_yoy"])}</td>
        <td>{vn["normal_avg"]}件</td><td>—</td></tr>
    </table>

    <h4 style="font-size:14px; color:#bf360c; margin:15px 0 8px;">7-2.2 各分类2026年1-8月同比</h4>
    <table class="data-table">
      <tr><th>类别</th><th>2026年1-8月</th><th>2025年1-8月</th><th>同比</th><th>态势</th></tr>
{cat_tr}
    </table>

    <h4 style="font-size:14px; color:#bf360c; margin:15px 0 8px;">7-2.3 Top10小区2026年1-8月变化</h4>
    <table class="data-table">
      <tr><th>排名</th><th>小区</th><th>街道</th><th>2026年1-8月</th><th>2025年1-8月</th><th>同比</th><th>态势</th></tr>
{comm_tr}
    </table>
    <p style="font-size:12px;color:#888;margin-top:4px;">注：{worse_txt} 等小区逆势恶化，需启动专项督导。</p>

    <div class="highlight" style="background:#fff3e0; border-left-color:#e65100; margin-top:12px;">
      <strong>📌 近期管理建议：</strong>底部抬升小区整体治理成效优于普通小区
      （{fmt_pct(vn["bl_yoy"])} vs {fmt_pct(vn["normal_yoy"])}），
      但<strong>{worse_txt}</strong>逆势恶化，需立即启动专项督导；
      从类别看，{risen_txt}同比上升，是当前最难啃的两类问题，建议加强业委会组建指导与社区调解力量配备。
    </div>
  </div>

""" + html[j:]
done.append("七-2专项分析")

# ============================================================
# 八、结论与建议
# ============================================================
rep(
    '<li><strong>底部抬升见效慢但正在加速。</strong>2025年同比仅降5.5%，2026上半年扩大至19.2%，'
    '改善小区比例从50.7%升至58.1%，攻坚行动逐步显效。</li>',
    f'<li><strong>底部抬升见效慢但正在加速，并首次反超全区。</strong>2025年同比仅降5.5%（落后全区14.4pp），'
    f'2026年1-8月扩大至{fmt_pct(yoy["m8_2026_vs_m8_2025"])}，优于全区{fmt_pct(yoy["all_m8_2026"])}'
    f'共{abs(pp["m8_2026_vs_all"])}pp；改善小区{cc["down"]}个（{cc["down_pct"]}%），攻坚行动逐步显效。</li>',
    "结论1",
)
rep(
    '<li><strong>占比不降反升，仍是投诉"主力军"。</strong>84个重点小区占全区投诉比重从2024年15.3%升至2025年18.0%，'
    '说明普通小区降得更快，底部小区是治理深水区。</li>',
    f'<li><strong>占比仍高但已见顶回落。</strong>重点小区占全区投诉比重2024年{sh["y2024"]}%→2025年{sh["y2025"]}%，'
    f'2026年1-8月回落至{sh["m8_2026"]}%（较2025年同期{sh["m8_2025"]}%下降0.8pp），'
    '说明底部小区降速开始快于面上，但仍是投诉"主力军"。</li>',
    "结论2",
)
rep(
    '<li><strong>二类矛盾是"硬骨头"。</strong>设施设备/房屋本体类矛盾占66.6%的投诉量，但降幅仅-2.0%，'
    '需要旧改、维修资金等系统性方案。</li>',
    f'<li><strong>矛盾主战场发生转移：三类矛盾成为新"硬骨头"。</strong>'
    f'二类（设施/房屋）占{share2}%的投诉量，2026年1-8月同比{fmt_pct(ct["2"]["yoy_m8"])}，已大幅改善；'
    f'三类（业委会/治理）同比{fmt_pct(ct["3"]["yoy_m8"], True)}，是唯一上升的矛盾类型，'
    '需要街道牵头、依法换届、业委会能力建设等系统性方案。</li>',
    "结论3",
)
rep(
    '<li><strong>街道差距显著。</strong>凌云路(-44.8%)、漕河泾(-30.8%)、康健(-26.0%)三街道成效显著，'
    '而虹梅路(+156.7%)、龙华(+20.5%)出现反弹，需督导。</li>',
    '<li><strong>街道差距显著。</strong>康健新村(-52.4%)、华泾(-43.3%)、湖南路(-32.5%)三街道成效显著，'
    '而虹梅路(+113.3%)、龙华(+37.5%)严重恶化，田林(+11.2%)、天平路(+17.6%)出现反弹，需督导。</li>',
    "结论4",
)
rep(
    '<li><strong>停车管理和邻里纠纷最难治。</strong>两类问题在底部小区中投诉量大且几乎没有下降，需要创新治理手段。</li>',
    f'<li><strong>{risen_txt.split("（")[0]}最难治。</strong>'
    f'{risen_txt}是2026年1-8月仅有的两个同比上升类别，且投诉量分居第1、3位，需要创新治理手段。</li>',
    "结论5",
)

# ============================================================
open(HTML, "w", encoding="utf-8").write(html)
print("已改造片段：")
for d in done:
    print("  ✓", d)
if skipped:
    print("跳过（已改造过）：")
    for s in skipped:
        print("  -", s)

# 残留下半年口径检查
left = []
for kw in ["2026上半年", "2026年上半年", "2026H1", "2025H1"]:
    if kw in html:
        left.append(kw)
print("\n残留旧口径关键词：", left if left else "无 ✓")
