# -*- coding: utf-8 -*-
"""
更新《治理效果追踪分析报告.html》为 v2 口径（2026年1-8月同期）
===============================================================

数据来源：scripts/governance_tracking.json（由 governance_tracking.py v2 生成）

替换范围：
  1. 副标题与总体概况统计卡、结论段
  2. 治理闭环模型表（4 类 → 5 类，新增「本期无投诉」）
  3. 十四类治理效果表 tbody
  4. 街道治理效果表 tbody
  5. 五/六/七节案例卡（成功Top10 / 反弹Top5 / 恶化Top5）

脚本可重复执行（每次都从 governance_tracking.json 重新生成对应区块）。
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOV = os.path.join(ROOT, "scripts", "governance_tracking.json")
REPORT = os.path.join(ROOT, "治理效果追踪分析报告.html")


def fmt(v):
    return f"{v:,}" if isinstance(v, (int, float)) else "—"


def pct_span(v, digits=1):
    """改善率（正数=改善）→ 带颜色的 span。"""
    if v is None:
        return '<span style="color:#666;font-weight:600;">—</span>'
    # 报告风格：改善用绿色显示负号（下降），恶化用红色显示正号（上升）
    if v > 0:
        return f'<span style="color:#2e7d32;font-weight:600;">-{v:.{digits}f}%</span>'
    if v < 0:
        return f'<span style="color:#c62828;font-weight:600;">+{abs(v):.{digits}f}%</span>'
    return '<span style="color:#666;font-weight:600;">0.0%</span>'


def ratio(a, b, digits=1):
    return f"{a / b * 100:.{digits}f}%" if b else "—"


def build_stat_grid(d):
    tot = d["total_tracking"]
    return f"""<div class="stat-grid">
      <div class="stat-card green"><div class="num">{tot}</div><div class="label">追踪小区总数（2025年同期≥10件）</div></div>
      <div class="stat-card green"><div class="num">{d['success_count']}</div><div class="label">改善(同期同比>10%)</div><div class="pct" style="color:#52c41a;">{ratio(d['success_count'], tot)}</div></div>
      <div class="stat-card red"><div class="num">{d['worsening_count']}</div><div class="label">恶化(同期同比&lt;-10%)</div><div class="pct" style="color:#f5222d;">{ratio(d['worsening_count'], tot)}</div></div>
      <div class="stat-card orange"><div class="num">{d['rebound_count']}</div><div class="label">改善后反弹</div><div class="pct" style="color:#fa8c16;">{ratio(d['rebound_count'], tot)}</div></div>
      <div class="stat-card" style="background:#f0f5ff;"><div class="num">{d['stable_count']}</div><div class="label">基本稳定(±10%内)</div><div class="pct" style="color:#1890ff;">{ratio(d['stable_count'], tot)}</div></div>
    </div>"""


def build_loop_table(d):
    tot = d["total_tracking"]
    rows = [
        ("green", "显著改善", d["success_count"],
         "2026年1-8月 vs 2025年同期，投诉量下降>10%", "总结经验，推广做法"),
        ("red", "持续恶化", d["worsening_count"],
         "2026年1-8月 vs 2025年同期，投诉量上升>10%（含反弹）", "紧急介入，专项治理"),
        ("orange", "改善后反弹", d["rebound_count"],
         "2025年改善>20% 但 2026年同期恶化>10%", "分析反弹原因，重新施策"),
        ("", "基本稳定", d["stable_count"],
         "同期同比波动在±10%以内", "常规跟踪，预防恶化"),
        ("", "本期无投诉", d.get("nodata_count", 0),
         "2026年1-8月零工单（可能为拆迁/更名/归并），不参与成效排名", "核实小区状态，单独标注"),
    ]
    style4 = 'background:#e6f7ff;color:#1890ff;border:1px solid #91d5ff;'
    out = []
    for color, name, cnt, desc, advice in rows:
        if cnt is None:
            continue
        badge = (f'<span class="badge {color}">{name}</span>' if color
                 else f'<span class="badge" style="{style4}">{name}</span>')
        out.append(f'<tr><td>{badge}</td><td>{cnt}</td><td>{ratio(cnt, tot)}</td>'
                   f'<td style="text-align:left;">{desc}</td>'
                   f'<td style="text-align:left;">{advice}</td></tr>')
    return "\n        ".join(out)


def build_category_rows(d):
    """十四类：按 2026年同期改善率（正数=改善）降序。"""
    items = [v for v in d["category_effects"].items()]
    items.sort(key=lambda kv: -(kv[1]["effect_2026"] if kv[1]["effect_2026"] is not None else -999))
    out = []
    for cat, v in items:
        e26 = v["effect_2026"]
        if e26 is None:
            eval_txt, badge = "—", '<span class="badge">无同期基数</span>'
        elif e26 > 20:
            eval_txt, badge = "效果显著", '<span class="badge green">效果显著</span>'
        elif e26 > 5:
            eval_txt, badge = "效果良好", '<span class="badge green">效果良好</span>'
        elif e26 > -5:
            eval_txt, badge = "效果一般", '<span class="badge orange">效果一般</span>'
        else:
            eval_txt, badge = "效果不佳", '<span class="badge red">效果不佳</span>'
        out.append(
            f'<tr><td style="text-align:left;font-weight:600;">{cat}</td>'
            f'<td>{fmt(v["2024"])}</td><td>{fmt(v["2025"])}</td>'
            f'<td>{pct_span(v["effect_2025"])}</td>'
            f'<td>{fmt(v["2025_h1"])}</td><td>{fmt(v["2026_h1"])}</td>'
            f'<td>{pct_span(e26)}</td><td>{badge}</td></tr>')
    return "\n        ".join(out)


def build_street_rows(d):
    items = list(d["street_effects"].items())
    items.sort(key=lambda kv: -(kv[1]["effect_2026"] if kv[1]["effect_2026"] is not None else -999))
    out = []
    for i, (st, v) in enumerate(items, 1):
        out.append(
            f'<tr><td>{i}</td><td style="text-align:left;font-weight:600;">{st}</td>'
            f'<td>{fmt(v["2024"])}</td><td>{fmt(v["2025"])}</td>'
            f'<td>{pct_span(v["effect_2025"])}</td>'
            f'<td>{fmt(v["2025_h1"])}</td><td>{fmt(v["2026_h1"])}</td>'
            f'<td>{pct_span(v["effect_2026"])}</td></tr>')
    return "\n        ".join(out)


def case_cards(cases, kind_cls, kind_label, limit):
    out = []
    for i, t in enumerate(cases[:limit], 1):
        imp26 = t["improvement_2026"]
        imp25 = t["improvement_2025"]
        if kind_cls == "success":
            tail = (f"同期同比改善 {imp26:.1f}%，治理成效显著，建议总结经验并推广。")
        elif kind_cls == "rebound":
            tail = (f"同期同比恶化 {abs(imp26):.1f}%。2025年治理效果良好，但2026年投诉量再次上升，"
                    f"需深入调研反弹根因，防止“治标不治本”。")
        else:
            tail = (f"同期同比恶化 {abs(imp26):.1f}%。2026年投诉量持续上升，需紧急介入、专项治理。")
        imp25_txt = (f"（2024全年 {fmt(t['n2024'])} → 2025全年 {fmt(t['n2025'])}，"
                     f"{'改善' if (imp25 or 0) > 0 else '上升'} {abs(imp25):.1f}%）"
                     if imp25 is not None else "")
        out.append(
            f'<div class="case-card {kind_cls}">\n'
            f'      <div class="cc-title">案例{i}：{t["community"]}（{t["street"]}）— {t["top_category"]}</div>\n'
            f'      <div class="cc-desc">2025年1-8月 {fmt(t["n2025_same"])}件 '
            f'<span class="arrow">→</span> 2026年1-8月 {fmt(t["n2026"])}件。{tail}{imp25_txt}</div>\n'
            f'    </div>')
    return "\n    ".join(out)


def build_charts(d):
    """重建三张图的 setOption 数据（2026年1-8月口径）。"""
    tot = d["total_tracking"]
    loop = f"""var chart1 = echarts.init(document.getElementById('chart-loop'));
chart1.setOption({{
  tooltip: {{ trigger: 'item', formatter: '{{a}}<br/>{{b}}: {{c}}个 ({{d}}%)' }},
  legend: {{ orient: 'vertical', left: 'left', top: 30 }},
  series: [{{
    name: '治理效果',
    type: 'pie',
    radius: ['35%', '65%'],
    center: ['55%', '50%'],
    data: [
      {{ value: {d['success_count']}, name: '改善', itemStyle: {{ color: '#52c41a' }} }},
      {{ value: {d['worsening_count']}, name: '恶化（含反弹{d['rebound_count']}）', itemStyle: {{ color: '#f5222d' }} }},
      {{ value: {d['stable_count']}, name: '基本稳定', itemStyle: {{ color: '#1890ff' }} }},
      {{ value: {d.get('nodata_count', 0)}, name: '本期无投诉', itemStyle: {{ color: '#bfbfbf' }} }}
    ],
    label: {{ formatter: '{{b}}\\n{{c}}个 ({{d}}%)', fontSize: 11 }}
  }}]
}});"""

    # 十四类：按 2026年1-8月 投诉量降序（yAxis 自下而上，需反序）
    cats = sorted(d["category_effects"].items(), key=lambda kv: -kv[1]["2026_h1"])
    names = [c for c, _ in cats][::-1]
    d24 = [v["2024"] for _, v in cats][::-1]
    d25 = [v["2025"] for _, v in cats][::-1]
    d26 = [v["2026_h1"] for _, v in cats][::-1]
    cat_chart = f"""var chart2 = echarts.init(document.getElementById('chart-category'));
chart2.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
  legend: {{ data: ['2024年','2025年','2026年1-8月'], top: 5 }},
  grid: {{ left: 130, right: 30, bottom: 40, top: 50 }},
  xAxis: {{ type: 'value', name: '投诉量（件）' }},
  yAxis: {{ type: 'category', data: {json.dumps(names, ensure_ascii=False)} }},
  series: [
    {{ name: '2024年', type: 'bar', data: {d24}, itemStyle: {{ color: '#bfbfbf' }} }},
    {{ name: '2025年', type: 'bar', data: {d25}, itemStyle: {{ color: '#fa8c16' }} }},
    {{ name: '2026年1-8月', type: 'bar', data: {d26}, itemStyle: {{ color: '#1890ff' }} }}
  ]
}});"""

    sts = sorted(d["street_effects"].items(), key=lambda kv: -kv[1]["2026_h1"])
    snames = [k for k, _ in sts]
    s24 = [v["2024"] for _, v in sts]
    s25 = [v["2025"] for _, v in sts]
    s26 = [v["2026_h1"] for _, v in sts]
    street_chart = f"""var chart3 = echarts.init(document.getElementById('chart-street'));
chart3.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
  legend: {{ data: ['2024年','2025年','2026年1-8月'], top: 5 }},
  grid: {{ left: 80, right: 30, bottom: 40, top: 50 }},
  xAxis: {{ type: 'category', data: {json.dumps(snames, ensure_ascii=False)}, axisLabel: {{ rotate: 30 }} }},
  yAxis: {{ type: 'value', name: '投诉量（件）' }},
  series: [
    {{ name: '2024年', type: 'bar', data: {s24}, itemStyle: {{ color: '#bfbfbf' }} }},
    {{ name: '2025年', type: 'bar', data: {s25}, itemStyle: {{ color: '#fa8c16' }} }},
    {{ name: '2026年1-8月', type: 'bar', data: {s26}, itemStyle: {{ color: '#1890ff' }} }}
  ]
}});"""
    return {"chart-loop": loop, "chart-category": cat_chart, "chart-street": street_chart}


def replace_chart(s, cid, block):
    pat = (r"var (chart\d+) = echarts\.init\(document\.getElementById\('" + cid + r"'\)\);"
           r"\s*\n\1\.setOption\(\{.*?\n\}\);")
    new, cnt = re.subn(pat, lambda m: block, s, flags=re.S)
    return new, cnt


def build_benchmark_rows(d):
    """5.3「近期持续改善标杆」：2025 与 2026 同期均改善的小区，按 2026 同比降序。"""
    both = [t for t in d["success_top20"]
            if (t["improvement_2025"] or 0) > 0 and (t["improvement_2026"] or 0) > 0]
    both.sort(key=lambda x: -x["improvement_2026"])
    out = []
    for t in both[:6]:
        out.append(
            f'<tr><td style="text-align:left;font-weight:600;">{t["community"]}</td>'
            f'<td>{t["street"]}</td>'
            f'<td style="color:#2e7d32;">-{t["improvement_2025"]:.1f}%</td>'
            f'<td style="color:#2e7d32;font-weight:600;">-{t["improvement_2026"]:.1f}%</td>'
            f'<td>🟢 持续改善</td></tr>')
    return "\n        ".join(out)


def refresh_stale_text(s, d):
    """把散落在正文里的旧计数（v1 口径）同步为 v2。"""
    pairs = [
        ("从269个扩展到500个以上", f"从{d['success_count']}个向同类小区推广复制"),
        ("269个显著改善小区", f"{d['success_count']}个改善小区"),
        ("115个反弹小区", f"{d['rebound_count']}个反弹小区"),
        ("31个恶化小区", f"{d['worsening_count']}个恶化小区"),
        ("7月单月降幅消失（-0.2%）", "8月单月同比转为上升（+2.8%）"),
        ("馨宁公寓等标杆小区", "江南新村等标杆小区"),
    ]
    for old, new in pairs:
        if old in s:
            s = s.replace(old, new)

    # 单月同比 KPI 卡：7月(-0.2%) → 8月(+2.8%)
    s = re.sub(r'>-0\.2%<', '>+2.8%<', s)
    s = s.replace('7月单月同比', '8月单月同比').replace('降幅消失', '同比转升')

    # 恶化街道 KPI 卡：按 v2 口径重算
    worse = sorted([k for k, v in d["street_effects"].items()
                    if v["effect_2026"] is not None and v["effect_2026"] < 0],
                   key=lambda k: d["street_effects"][k]["effect_2026"])
    i = s.find('恶化街道数')
    if i > 0:
        head = max(0, i - 300)
        s = s[:head] + re.sub(r'>(\d+)/13<', f'>{len(worse)}/13<', s[head:i]) + s[i:]
    s = s.replace('斜土/漕河泾/徐家汇', '/'.join(worse))
    s = re.sub(r'第四象限\d+个恶化街道',
               f'同比恶化的 {len(worse)} 个街道（{"、".join(worse)}）', s)
    return s


def main():
    d = json.load(open(GOV, encoding="utf-8"))
    s = open(REPORT, encoding="utf-8").read()
    orig_len = len(s)

    # ── 0. 散落在正文的旧计数
    s = refresh_stale_text(s, d)

    # ── 1. 副标题
    s = re.sub(r'<div class="subtitle">[^<]*?</div>',
               f'<div class="subtitle">{d["total_tracking"]}个小区追踪 · 改善/恶化/反弹/稳定四类 · '
               f'2026年1-8月 vs 2025年同期口径</div>', s, count=1)

    # ── 2. 总体概况：统计卡 + 结论段
    s = re.sub(r'<div class="stat-grid">.*?</div>\s*</div>\s*<p>追踪结果显示：.*?</p>',
               lambda m: build_stat_grid(d) + "\n    </div>\n    "
               + f'<p>追踪结果显示：<strong>{ratio(d["success_count"], d["total_tracking"])}的小区治理效果显著</strong>'
                 f'（2026年1-8月较2025年同期下降超10%），'
                 f'<strong>{ratio(d["worsening_count"], d["total_tracking"])}的小区投诉恶化</strong>'
                 f'（上升超10%，其中 {d["rebound_count"]} 个为“2025年改善但2026年反弹”），'
                 f'<strong>{ratio(d["stable_count"], d["total_tracking"])}基本稳定</strong>。'
                 f'另有 {d.get("nodata_count", 0)} 个小区2026年1-8月零工单（可能为拆迁、更名或数据归并），'
                 f'单列“本期无投诉”，不计入成效排名。</p>',
               s, count=1, flags=re.S)

    # ── 3. 闭环表 tbody
    s = re.sub(r'(<th>处置建议</th></tr></thead>\s*<tbody>)(.*?)(</tbody>)',
               lambda m: m.group(1) + "\n        " + build_loop_table(d) + "\n      " + m.group(3),
               s, count=1, flags=re.S)

    # ── 4. 十四类表 tbody（定位「治理评价」表头）
    s = re.sub(r'(<th>2026同期改善率</th><th>治理评价</th></tr></thead>\s*<tbody>)(.*?)(</tbody>)',
               lambda m: m.group(1) + "\n        " + build_category_rows(d) + "\n      " + m.group(3),
               s, count=1, flags=re.S)

    # ── 5. 街道表 tbody（定位「2026同期改善率」且无「治理评价」的表头）
    def street_sub(m):
        return m.group(1) + "\n        " + build_street_rows(d) + "\n      " + m.group(3)
    s = re.sub(r'(<th>2026年1-8月</th><th>2026同期改善率</th></tr></thead>\s*<tbody>)(.*?)(</tbody>)',
               street_sub, s, count=1, flags=re.S)

    # ── 6. 三张图表的数据块
    charts = build_charts(d)
    for cid, block in charts.items():
        s, cnt = replace_chart(s, cid, block)
        print(f"图表 {cid}: 替换 {cnt} 处")

    # ── 6.5 5.3 近期持续改善标杆表（该表无 thead/tbody，需按 </table> 边界整段替换）
    marker = "<th>持续改善</th></tr>"
    i = s.find(marker)
    if i > 0:
        head_end = i + len(marker)
        end = s.find("</table>", head_end)
        rows = build_benchmark_rows(d)
        s = (s[:head_end] + "\n      " +
             rows.replace("<tr>", '<tr style="background:#e8f5e9;">') +
             "\n    " + s[end:])
        print(f"5.3 标杆表: 替换 1 处（{rows.count('<tr>')} 行）")
    else:
        print("5.3 标杆表: 未找到锚点")

    # ── 7. 案例卡（五/六/七节）
    def replace_cases(start_marker, end_marker, cards):
        nonlocal s
        i = s.find(start_marker)
        if i < 0:
            return False
        j = s.find(end_marker, i)
        if j < 0:
            j = s.find("</div>\n\n  <!-- ", i)
        seg = s[i:j]
        k = seg.find('<div class="case-card')
        if k < 0:
            return False
        new_seg = seg[:k] + cards + "\n  "
        s = s[:i] + new_seg + s[j:]
        return True

    ok5 = replace_cases("<!-- 五、成功案例Top10 -->", "<!-- 六、", case_cards(d["success_top20"], "success", "改善", 10))
    ok6 = replace_cases("<!-- 六、反弹案例Top5 -->", "<!-- 七、", case_cards(d["rebound_top10"], "rebound", "反弹", 5))
    ok7 = replace_cases("<!-- 七、恶化案例Top5 -->", "<!-- 八、", case_cards(d["worsening_top10"], "worsening", "恶化", 5))
    print(f"案例替换: 成功={ok5} 反弹={ok6} 恶化={ok7}")

    # ── 7. 章节标题里的口径说明
    s = s.replace("六、治理反弹案例Top5（2025改善→2026恶化）",
                  "六、治理反弹案例Top5（2025年改善→2026年同期恶化）")

    # ── 8. 口径注释
    note = ('<p class="note">口径说明：同比采用同期对比 —— 2025同比 = 2025全年 vs 2024全年；'
            '2026同比 = 2026年1-8月 vs 2025年1-8月。'
            '成效判定以2026年同期同比为准（恶化&lt;-10%｜改善&gt;+10%｜稳定±10%内），'
            '入榜门槛为三年合计≥15件、2024全年≥5件、2025年1-8月≥10件（抑制小基数放大）。'
            '首位类别取2026年1-8月实际首位。数据源：data/merged_cleaned.pkl（66,812条）。</p>')
    if "口径说明：同比采用同期对比" not in s:
        s = s.replace('<p class="note">注：另有346个小区', note + '\n    <p class="note">注：另有')
        if "口径说明：同比采用同期对比" not in s:
            # 兜底：插到总体概况段落后
            idx = s.find("一、总体概况")
            end = s.find("</div>", s.find("追踪结果显示", idx))
            s = s[:end + 6] + "\n    " + note + s[end + 6:]

    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"✔ 已更新 {REPORT}")
    print(f"  {orig_len:,} → {len(s):,} 字符")
    print(f"  追踪{d['total_tracking']} 改善{d['success_count']} 恶化{d['worsening_count']} "
          f"反弹{d['rebound_count']} 稳定{d['stable_count']} 无投诉{d.get('nodata_count', 0)}")


if __name__ == "__main__":
    main()
