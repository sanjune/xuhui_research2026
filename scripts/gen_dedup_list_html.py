# -*- coding: utf-8 -*-
"""
投诉去重建议清单（月度合集）页面生成器
=====================================

读取 scripts/dedup_monthly_all.json，按固定模板生成自包含 HTML 合集页，
覆盖 JSON 中存在的所有月份（当前为 2026年1-8月）。

用法：
    python scripts/gen_dedup_list_html.py                 # 自动取 JSON 中全部月份
    python scripts/gen_dedup_list_html.py --months 1-8    # 指定月份范围

模板资产（从既有页面提取，保持不变）：
    scripts/dedup_list_style.html    ← <style> 样式块
    scripts/dedup_list_script.html   ← 月份标签切换 + 浮动目录脚本

输出：
    2026年{首}-{末}月投诉去重建议清单.html （项目根目录）
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(ROOT, "scripts", "dedup_monthly_all.json")
STYLE_PATH = os.path.join(ROOT, "scripts", "dedup_list_style.html")
SCRIPT_PATH = os.path.join(ROOT, "scripts", "dedup_list_script.html")

BADGE = {"高": "high", "中": "medium", "低": "low"}


def n(x):
    """千分位整数；空值 → —"""
    if x is None or x == "":
        return "—"
    try:
        return f"{int(x):,}"
    except (TypeError, ValueError):
        return str(x)


def pct(num, base):
    return f"{num / base * 100:.1f}%" if base else "0.0%"


def strategy_rows(m, dup):
    """识别策略表 5 行。"""
    rows = [
        ("策略一：完全重复", "同小区+内容精确匹配",
         f"{n(m['s1_count'])}条（{n(m['s1_groups'])}组）", pct(m["s1_count"], dup)),
        ("策略二：催办/重发", "关键词检索",
         f"{n(m['s2_count'])}条", pct(m["s2_count"], dup)),
        ("策略三：同小区同类高频", "同小区+同类别≥3次",
         f"{n(m['s3_count'])}条（{n(m['s3_groups'])}组）", pct(m["s3_count"], dup)),
        ("策略四：文本相似", "余弦相似度≥0.6",
         f"{n(m['s4_count'])}条（{n(m['s4_pairs'])}对/{n(m['s4_comms'])}小区）",
         pct(m["s4_count"], dup)),
    ]
    out = "".join(
        f"          <tr><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td></tr>\n"
        for a, b, c, d in rows
    )
    out += (f'          <tr style="background:#e6f7ff;font-weight:700;">'
            f'<td>合并去重</td><td>四策略并集</td><td>{n(m["total_dup"])}条</td>'
            f'<td>100%</td></tr>\n')
    return out


def hf20_rows(m):
    out = ""
    for r in m["hf20"]:
        badge = BADGE.get(r.get("priority", "高"), "high")
        out += (f'<tr><td>{r["rank"]}</td><td style="font-weight:600;">{r["community"]}</td>'
                f'<td>{r.get("street","")}</td><td>{r["category"]}</td>'
                f'<td style="font-weight:700;color:#f5222d;">{n(r["count"])}</td>'
                f'<td>{r.get("property","")}</td>'
                f'<td><span class="badge {badge}">{r.get("priority","高")}</span></td></tr>\n')
    return out


def sim_rows(m):
    out = ""
    for i, r in enumerate(m.get("sim_top5", []), 1):
        sim = r.get("sim")
        sim_txt = f"{sim:.3f}" if isinstance(sim, (int, float)) else "—"
        out += (f'<tr><td>{i}</td><td>{r.get("community")}</td>'
                f'<td class="content-cell">{r.get("a","")}…</td>'
                f'<td class="content-cell">{r.get("b","")}…</td>'
                f'<td style="font-weight:700;color:#52c41a;">{sim_txt}</td></tr>\n')
    return out


def dist_rows(items):
    return "".join(
        f'<tr><td style="text-align:left;">{it["cat"] if "cat" in it else it["street"]}</td>'
        f'<td>{n(it["cnt"])}</td><td>{it["pct"]}%</td></tr>\n'
        for it in items
    )


def fmt_sim(sim):
    """相似度格式：整数保留 1 位小数（1.0），其余去尾零（0.66 / 0.6）"""
    if not isinstance(sim, (int, float)):
        return "—"
    return f"{sim:.1f}" if float(sim).is_integer() else f"{sim:g}"


def list15_rows(m):
    out = ""
    for i, r in enumerate(m.get("list15", []), 1):
        badge = BADGE.get(r.get("priority", "中"), "medium")
        sim_txt = fmt_sim(r.get("sim"))
        tags = '<span class="strategy-tag s3">同小区高频</span>'
        if r.get("strategies") == "S3+S4":
            tags += '<span class="strategy-tag s4">文本相似</span>'
        out += (f'<tr><td>{i}</td><td>{r.get("oid","")}</td>'
                f'<td style="font-weight:600;">{r["community"]}</td>'
                f'<td>{r.get("street","")}</td><td>{r["category"]}</td>'
                f'<td>{tags}</td>'
                f'<td>{n(r.get("freq"))}</td><td>{sim_txt}</td>'
                f'<td>{r.get("suggestion","")}</td>'
                f'<td><span class="badge {badge}">{r.get("priority","中")}</span></td></tr>\n')
    return out


def month_panel(month: int, m: dict, active: bool) -> str:
    dup = m["total_dup"] or 1
    hi_pct = f'{m["high_count"] / (m["high_count"] + m["mid_count"]) * 100:.1f}%' \
        if (m["high_count"] + m["mid_count"]) else "0.0%"
    lo_pct = f'{m["mid_count"] / (m["high_count"] + m["mid_count"]) * 100:.1f}%' \
        if (m["high_count"] + m["mid_count"]) else "0.0%"
    return f'''<div class="tab-panel{' active' if active else ''}" id="panel-m{month}">
      <div class="stat-grid">
        <div class="stat-card"><div class="num blue">{n(m["total"])}</div><div class="label">工单总数</div></div>
        <div class="stat-card"><div class="num red">{n(m["total_dup"])}</div><div class="label">重复投诉</div></div>
        <div class="stat-card"><div class="num red">{m["dup_rate"]}%</div><div class="label">重复占比</div></div>
        <div class="stat-card"><div class="num orange">{n(m["s3_groups"])}</div><div class="label">高频问题组</div></div>
      </div>

      <table class="data-table">
        <thead><tr><th>识别策略</th><th>技术手段</th><th>识别结果</th><th>占比</th></tr></thead>
        <tbody>
{strategy_rows(m, dup)}        </tbody>
      </table>

      <div class="stat-grid" style="margin-top:20px;">
        <div class="stat-card"><div class="num red">{n(m["high_count"])}</div><div class="label">高优先级（{hi_pct}）</div></div>
        <div class="stat-card"><div class="num orange">{n(m["mid_count"])}</div><div class="label">中优先级（{lo_pct}）</div></div>
        <div class="stat-card"><div class="num blue">{n(m["s3_groups"])}</div><div class="label">需专项治理组</div></div>
        <div class="stat-card"><div class="num green">{n(m["s4_comms"])}</div><div class="label">文本相似小区</div></div>
      </div>

      <div class="section-subtitle">高频热点小区Top20</div>
      <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>排名</th><th>小区</th><th>街道</th><th>问题类别</th><th>次数</th><th>物业公司</th><th>优先级</th></tr></thead>
        <tbody>{hf20_rows(m)}</tbody>
      </table>
      </div>

      <div class="section-subtitle">文本相似典型案例</div>
      <table class="data-table">
        <thead><tr><th>排名</th><th>小区</th><th>工单A</th><th>工单B</th><th>相似度</th></tr></thead>
        <tbody>{sim_rows(m)}</tbody>
      </table>

      <div class="two-col">
        <div>
          <div class="section-subtitle">类别分布</div>
          <table class="data-table">
            <thead><tr><th>类别</th><th>重复量</th><th>占比</th></tr></thead>
            <tbody>{dist_rows(m["cats"])}</tbody>
          </table>
        </div>
        <div>
          <div class="section-subtitle">街道分布</div>
          <table class="data-table">
            <thead><tr><th>街道</th><th>重复量</th><th>占比</th></tr></thead>
            <tbody>{dist_rows(m["streets"])}</tbody>
          </table>
        </div>
      </div>

      <div class="section-subtitle">去重建议清单（Top15）</div>
      <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>序</th><th>工单编号</th><th>小区</th><th>街道</th><th>类别</th><th>策略</th><th>频次</th><th>相似度</th><th>处置建议</th><th>优先级</th></tr></thead>
        <tbody>{list15_rows(m)}</tbody>
      </table>
      </div>
    </div>
'''


def build(months):
    data = json.load(open(JSON_PATH, encoding="utf-8"))
    months = [str(m) for m in months if str(m) in data]
    if not months:
        raise SystemExit("JSON 中无可用月份数据")

    tot = sum(data[str(m)]["total"] for m in months)
    dup = sum(data[str(m)]["total_dup"] for m in months)
    grp = sum(data[str(m)]["s3_groups"] for m in months)
    rate = f"{dup / tot * 100:.1f}%" if tot else "0.0%"
    first, last = months[0], months[-1]
    up = data[last]["dup_rate"] >= data[first]["dup_rate"]

    tabs = "".join(
        f'        <button class="tab-btn{" active" if i == 0 else " "}" data-tab="m{m}">{m}月</button>\n'
        for i, m in enumerate(months)
    )
    panels = "\n".join(month_panel(int(m), data[str(m)], i == 0) for i, m in enumerate(months))

    css = open(STYLE_PATH, encoding="utf-8").read()
    js = open(SCRIPT_PATH, encoding="utf-8").read()

    # 处置行动建议中的动态数字
    share_min = min((data[str(m)]["s2_count"] / (data[str(m)]["total_dup"] or 1)) for m in months)
    g_first, g_last = data[first]["s3_groups"], data[last]["s3_groups"]
    g_pct = abs(g_last - g_first) / g_first * 100 if g_first else 0
    g_verb = "增至" if g_last >= g_first else "降至"
    g_word = "增长" if g_last >= g_first else "下降"

    advice = f'''  <div class="section">
    <div class="section-title">处置行动建议</div>
    <div style="background:#f6f8fa;border-left:4px solid #f5222d;border-radius:6px;padding:14px 18px;margin-bottom:10px;">
      <div style="font-weight:700;font-size:14px;margin-bottom:4px;color:#cf1322;">行动一：催办工单质量提升</div>
      <div style="font-size:13px;color:#555;">各月催办类投诉占比均在{share_min * 100:.0f}%以上，核心问题是首次答复质量不高。建议建立答复内容审核机制，答复必须包含具体解决措施和时限，禁止模板化回复。</div>
    </div>
    <div style="background:#f6f8fa;border-left:4px solid #f5222d;border-radius:6px;padding:14px 18px;margin-bottom:10px;">
      <div style="font-weight:700;font-size:14px;margin-bottom:4px;color:#cf1322;">行动二：高频小区专项治理</div>
      <div style="font-size:13px;color:#555;">高频问题组从{first}月{g_first}组{g_verb}{last}月{g_last}组，{g_word}{g_pct:.0f}%。对每月Top20高频小区实施"一小区一方案"，街道牵头限期30天内解决核心问题。</div>
    </div>
    <div style="background:#f6f8fa;border-left:4px solid #fa8c16;border-radius:6px;padding:14px 18px;margin-bottom:10px;">
      <div style="font-weight:700;font-size:14px;margin-bottom:4px;color:#d46b08;">行动三：预警闭环机制</div>
      <div style="font-size:13px;color:#555;">当任一小区同类投诉达到3次时自动触发预警，推送至街道物业部门。预警后15天内未降至0新增，自动升级为"重点关注"，启动专项督查。</div>
    </div>
    <div style="background:#f6f8fa;border-left:4px solid #fa8c16;border-radius:6px;padding:14px 18px;">
      <div style="font-weight:700;font-size:14px;margin-bottom:4px;color:#d46b08;">行动四：文本相似工单核实合并</div>
      <div style="font-size:13px;color:#555;">相似度1.0的直接合并关闭；相似度0.6-0.99的由承办单位核实是否同一问题，确认后合并处理，减少无效工单流转。</div>
    </div>
  </div>

'''

    trend_txt = ("去重率呈逐月上升趋势" if up else "去重率总体平稳")
    head = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>2026年{first}-{last}月 投诉去重建议清单（月度合集）</title>
{css}
</head>
<body>

<div class="sub-nav-bar">
<div class="sub-nav-inner">
<a class="sub-nav-logo" href="课题成果总览.html">徐汇物业课题一期</a>
<a class="sub-nav-back" href="课题成果总览.html#c2">← 返回成果#2</a>
<div class="sub-nav-links">
<a href="课题成果总览.html#core">核心成果</a>
<a href="课题成果总览.html#analysis">深度分析</a>
<a href="课题成果总览.html#tools">工具成果</a>
</div>
</div>
</div>

<div class="header">
  <h1>2026年{first}-{last}月 投诉去重建议清单（月度合集）</h1>
  <div class="subtitle">四重识别策略 · 月度追踪 · 处置优先级分级</div>
  <div class="meta">徐汇物业课题一期 · 投诉去重识别模型应用实例 | 2026年9月</div>
</div>

<div class="container">

  <div class="section">
    <div class="section-title">月度去重趋势总览</div>
    <p>2026年{first}-{last}月共{len(months)}个月的12345物业投诉去重分析，{trend_txt}，从{first}月的{data[first]["dup_rate"]}%{'升至' if up else '至'}{last}月的{data[last]["dup_rate"]}%。</p>
    <div class="stat-grid">
      <div class="stat-card"><div class="num blue">{tot:,}</div><div class="label">{first}-{last}月总工单</div></div>
      <div class="stat-card"><div class="num red">{dup:,}</div><div class="label">累计重复投诉</div></div>
      <div class="stat-card"><div class="num red">{rate}</div><div class="label">平均去重率</div></div>
      <div class="stat-card"><div class="num orange">{grp:,}</div><div class="label">累计高频组</div></div>
    </div>
    <p class="note">点击下方月份标签查看各月详细分析</p>
  </div>

  <div class="section">
    <div class="section-title">月度详细分析</div>
    <div class="tab-container">
      <div class="tab-bar">
{tabs}      </div>
{panels}
    </div>
  </div>

</div>

{advice}<div class="footer">
  徐汇区物业课题一期项目 · 投诉去重识别模型应用实例 · 2026年9月
</div>

{js}
</body>
</html>
'''
    out_path = os.path.join(ROOT, f"2026年{first}-{last}月投诉去重建议清单.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(head)
    print(f"✅ 已生成 {out_path}")
    print(f"   月份 {months} | 总工单 {tot:,} | 累计重复 {dup:,} | 平均去重率 {rate} | 累计高频组 {grp:,}")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", help="月份范围，如 1-8；默认取 JSON 全部月份")
    args = ap.parse_args()
    if args.months:
        a, _, b = args.months.partition("-")
        months = list(range(int(a), int(b or a) + 1))
    else:
        data = json.load(open(JSON_PATH, encoding="utf-8"))
        months = sorted((int(k) for k in data), key=int)
    build(months)


if __name__ == "__main__":
    main()
