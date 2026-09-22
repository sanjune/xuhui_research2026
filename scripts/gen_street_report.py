# -*- coding: utf-8 -*-
"""
街镇专项分析页生成器 — 数据 → HTML（可复现）
=============================================

输入：scripts/street_analysis.json
产出：街镇专项分析报告.html

页面结构：
    第一层  全区街镇总表（KPI + 对比表 + 3 张全区图）
    第二层  13 个街镇分页（标签切换，每镇 5 图 + 6 张表 + 结论要点）

用法：
    python scripts/gen_street_report.py

下月扩展：先跑 scripts/build_street_dataset.py 重算数据，再跑本脚本即可。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "scripts", "street_analysis.json")
OUT = os.path.join(ROOT, "街镇专项分析报告.html")
# 词云遮罩（徐汇区行政边界）：scripts/gen_xuhui_mask.py 生成
MASK_B64_FILE = os.path.join(ROOT, "assets", "xuhui_mask.b64")


def load_mask_b64():
    """读取徐汇区边界遮罩的 base64（内联进 HTML，保持报告单文件自包含）。"""
    if not os.path.exists(MASK_B64_FILE):
        return None
    with open(MASK_B64_FILE, encoding="ascii") as f:
        return f.read().strip()

C = {
    "blue": "#1890ff", "deep": "#1a3a5f", "green": "#52c41a", "red": "#f5222d",
    "orange": "#fa8c16", "gray": "#bfbfbf", "purple": "#7b1fa2", "teal": "#13c2c2",
    "yellow": "#fadb14",
}
LEVEL_COLOR = {"红色": "#f5222d", "橙色": "#fa8c16", "黄色": "#e6b800", "蓝色": "#1890ff"}
LEVEL_CLASS = {"红色": "lv-red", "橙色": "lv-orange", "黄色": "lv-yellow", "蓝色": "lv-blue"}


def n(v):
    """千分位。"""
    if v is None or v == "":
        return "—"
    if isinstance(v, float):
        v = round(v, 1)
    return f"{v:,}" if isinstance(v, (int, float)) else str(v)


def pct_txt(v, digits=1):
    if v is None:
        return "—"
    return f"{v:+.{digits}f}%" if v > 0 else f"{v:.{digits}f}%"


def pct_sum(values, digits=2):
    """百分比求和：先四舍五入到目标位数，避免浮点尾差（如 81.80000000000001）。"""
    vals = [v for v in values if v is not None]
    if not vals:
        return "—"
    return f"{round(sum(vals), digits):.{digits}f}"


def color_of(v, invert=False):
    """投诉量变化着色：上升红、下降绿（沿用报告既有约定）。"""
    if v is None:
        return "#999"
    if v > 0:
        return "#52c41a" if invert else "#f5222d"
    if v < 0:
        return "#f5222d" if invert else "#52c41a"
    return "#999"


# ─────────────────────────── 图表配置 ───────────────────────────

def chart_monthly_trend(st, s):
    m = s["monthly"]
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["2024年", "2025年", "2026年"], "top": 6},
        "grid": {"left": 60, "right": 30, "bottom": 36, "top": 44},
        "xAxis": {"type": "category", "data": m["labels"]},
        "yAxis": {"type": "value", "name": "件"},
        "series": [
            {"name": "2024年", "type": "line", "smooth": True, "data": m["y2024"],
             "itemStyle": {"color": C["gray"]}, "lineStyle": {"width": 2, "type": "dashed"}},
            {"name": "2025年", "type": "line", "smooth": True, "data": m["y2025"],
             "itemStyle": {"color": C["blue"]}, "lineStyle": {"width": 2}},
            {"name": "2026年", "type": "line", "smooth": True, "data": m["y2026"],
             "itemStyle": {"color": C["green"]}, "lineStyle": {"width": 3},
             "areaStyle": {"opacity": 0.12}, "connectNulls": False},
        ],
    }


def chart_yoy_monthly(s):
    data = s["yoy_monthly"]
    return {
        "tooltip": {"trigger": "axis", "formatter": "{b}<br/>2026年 {c} 件<br/>同比 {d}%"},
        "legend": {"data": ["2026年投诉量", "同比变化率"], "top": 6},
        "grid": {"left": 60, "right": 60, "bottom": 36, "top": 44},
        "xAxis": {"type": "category", "data": [f"{x['month']}月" for x in data]},
        "yAxis": [
            {"type": "value", "name": "件"},
            {"type": "value", "name": "同比%", "axisLabel": {"formatter": "{value}%"}},
        ],
        "series": [
            {"name": "2026年投诉量", "type": "bar", "data": [x["y2026"] for x in data],
             "itemStyle": {"color": C["blue"], "borderRadius": [4, 4, 0, 0]}},
            {"name": "同比变化率", "type": "line", "yAxisIndex": 1, "smooth": True,
             "data": [x["yoy"] for x in data], "itemStyle": {"color": C["orange"]},
             "label": {"show": True, "fontSize": 10, "formatter": "{c}%"}},
        ],
    }


def chart_category_delta(s):
    cats = sorted(s["category"], key=lambda x: x["delta"])
    return {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"},
                    "formatter": "{b}<br/>2026年1-8月 {c} 件（同期增减）"},
        "grid": {"left": 120, "right": 60, "bottom": 30, "top": 32},
        "xAxis": {"type": "value", "name": "同比增减（件）"},
        "yAxis": {"type": "category", "data": [x["cat"] for x in cats],
                  "axisLabel": {"fontSize": 11}},
        "series": [{
            "type": "bar", "data": [{"value": x["delta"],
                                     "itemStyle": {"color": color_of(x["delta"])}} for x in cats],
            "label": {"show": True, "position": "right", "fontSize": 10,
                      "formatter": "{c}"},
        }],
    }


def chart_category_donut(s):
    cats = [x for x in s["category"] if x["n2026"] > 0][:9]
    return {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} 件 ({d}%)"},
        "legend": {"type": "scroll", "orient": "vertical", "right": 6, "top": 20,
                   "itemWidth": 10, "itemHeight": 10, "textStyle": {"fontSize": 11}},
        "series": [{
            "type": "pie", "radius": ["42%", "68%"], "center": ["36%", "52%"],
            "avoidLabelOverlap": True,
            "label": {"show": True, "fontSize": 10, "formatter": "{b}\n{d}%"},
            "labelLine": {"length": 8, "length2": 8},
            "data": [{"name": x["cat"], "value": x["n2026"]} for x in cats],
        }],
    }


def chart_same_period(s):
    q = s["quarterly"]
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["2024年", "2025年", "2026年"], "top": 6},
        "grid": {"left": 60, "right": 30, "bottom": 36, "top": 44},
        "xAxis": {"type": "category", "data": [x["label"] for x in q]},
        "yAxis": {"type": "value", "name": "件"},
        "series": [
            {"name": "2024年", "type": "bar", "data": [x["y2024"] for x in q],
             "itemStyle": {"color": C["gray"]}},
            {"name": "2025年", "type": "bar", "data": [x["y2025"] for x in q],
             "itemStyle": {"color": C["blue"]}},
            {"name": "2026年", "type": "bar", "data": [x["y2026"] for x in q],
             "itemStyle": {"color": C["green"]}},
        ],
    }


def chart_overview_compare(ov):
    names = [r["street"] for r in ov]
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["2025年1-8月", "2026年1-8月", "同比降幅"], "top": 6},
        "grid": {"left": 60, "right": 60, "bottom": 60, "top": 44},
        "xAxis": {"type": "category", "data": names, "axisLabel": {"rotate": 30, "fontSize": 11}},
        "yAxis": [{"type": "value", "name": "件"},
                  {"type": "value", "name": "同比%", "axisLabel": {"formatter": "{value}%"}}],
        "series": [
            {"name": "2025年1-8月", "type": "bar", "data": [r["n2025_same"] for r in ov],
             "itemStyle": {"color": C["blue"]}},
            {"name": "2026年1-8月", "type": "bar", "data": [r["n2026"] for r in ov],
             "itemStyle": {"color": C["green"]}},
            {"name": "同比降幅", "type": "line", "yAxisIndex": 1, "smooth": True,
             "data": [r["yoy"] for r in ov], "itemStyle": {"color": C["orange"]},
             "label": {"show": True, "fontSize": 10, "formatter": "{c}%"}},
        ],
    }


def chart_overview_contribution(ov):
    rows = [r for r in sorted(ov, key=lambda x: -(x["contribution"] or -999))
            if r["contribution"] is not None]
    rows = rows[:10]
    return {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"},
                    "formatter": "{b}<br/>对全区下降贡献 {c}%"},
        "grid": {"left": 90, "right": 60, "bottom": 30, "top": 32},
        "xAxis": {"type": "value", "name": "贡献率%", "axisLabel": {"formatter": "{value}%"}},
        "yAxis": {"type": "category", "data": [r["street"] for r in rows][::-1],
                  "axisLabel": {"fontSize": 11}},
        "series": [{
            "type": "bar", "data": [r["contribution"] for r in rows][::-1],
            "itemStyle": {"color": C["deep"], "borderRadius": [0, 4, 4, 0]},
            "label": {"show": True, "position": "right", "formatter": "{c}%", "fontSize": 11},
        }],
    }


# 词云配色（按权重从高到低循环取用，中文词云不旋转，保证可读）
WC_PALETTE = ["#1a3a5f", "#1890ff", "#13c2c2", "#52c41a", "#fa8c16",
              "#f5222d", "#7b1fa2", "#0f6e56"]


def chart_wordcloud(kws):
    """诉求主题词词云。kws: [{'word':..,'cnt':..}]，按词频降序。

    轮廓为徐汇区行政边界：maskImage 在页面 JS 侧注入（图片对象无法放进 JSON），
    这里只声明 keepAspect —— 让词云按遮罩真实宽高比（约 0.605，南北长）居中收缩，
    避免被容器拉扁。遮罩未就绪时页面会跳过词云，就绪后自动补绘。
    """
    items = sorted(kws, key=lambda x: -x["cnt"])[:24]
    if not items:
        return None
    data = [{"name": x["word"], "value": x["cnt"],
             "textStyle": {"color": WC_PALETTE[i % len(WC_PALETTE)]}}
            for i, x in enumerate(items)]
    return {
        "tooltip": {"formatter": "{b}：{c} 次"},
        "series": [{
            "type": "wordCloud",
            "shape": "circle",
            "keepAspect": True,
            "left": "center", "top": "center",
            "width": "96%", "height": "92%",
            "sizeRange": [12, 44],
            "rotationRange": [0, 0],
            "rotationStep": 0,
            "gridSize": 5,
            "drawOutOfBound": False,
            "layoutAnimation": False,
            "emphasis": {"textStyle": {"fontWeight": "bold"}},
            "data": data,
        }],
    }


def chart_street_heatmap(ov, streets):
    months = [f"{m}月" for m in range(1, 9)]
    data, mx = [], 1
    for i, st in enumerate(streets):
        yoym = {x["month"]: x["y2026"] for x in st["yoy_monthly"]}
        for j, m in enumerate(range(1, 9)):
            v = yoym.get(m, 0)
            mx = max(mx, v)
            data.append([j, i, v])
    return {
        "grid": {"left": 70, "right": 30, "bottom": 70, "top": 20},
        "xAxis": {"type": "category", "data": months, "splitArea": {"show": True}},
        "yAxis": {"type": "category", "data": [s["name"] for s in streets],
                  "splitArea": {"show": True}, "axisLabel": {"fontSize": 11}},
        "visualMap": {"min": 0, "max": mx, "calculable": True, "orient": "horizontal",
                      "left": "center", "bottom": 6,
                      "inRange": {"color": ["#e6f7ff", "#1890ff", "#1a3a5f"]}},
        "series": [{"type": "heatmap", "data": data,
                    "label": {"show": True, "fontSize": 9},
                    "emphasis": {"itemStyle": {"shadowBlur": 6}}}],
    }


# ─────────────────────────── HTML 片段 ───────────────────────────

NAV = """<div class="nav-bar">
  <div class="nav-inner">
    <a class="nav-logo" href="课题成果总览.html">徐汇物业课题一期</a>
    <a class="nav-back" href="课题成果总览.html#c1">← 返回成果#1</a>
    <div class="nav-links">
      <div class="nav-dropdown">
        <a href="课题成果总览.html#core">核心成果</a>
        <div class="dropdown-menu">
          <a class="dropdown-item" href="12345投诉量下降数据报告.html"><span class="badge">#1</span>12345投诉量下降数据报告</a>
          <a class="dropdown-item" href="投诉去重识别方法论说明.html"><span class="badge">#2</span>投诉去重识别方法论说明</a>
          <div class="dropdown-divider"></div>
          <a class="dropdown-item" href="数据质量优化专项报告.html"><span class="badge">#3</span>数据质量优化专项报告</a>
          <a class="dropdown-item" href="高风险小区预警清单.html"><span class="badge">#6</span>高风险小区预警清单</a>
        </div>
      </div>
      <div class="nav-dropdown">
        <a href="课题成果总览.html#analysis">深度分析</a>
        <div class="dropdown-menu">
          <a class="dropdown-item" href="物业投诉根因分析报告.html"><span class="badge">#4</span>物业投诉根因分析报告</a>
          <a class="dropdown-item" href="重点问题专题分析报告（5份）.html"><span class="badge">#5</span>重点问题专题分析报告（5份）</a>
          <div class="dropdown-divider"></div>
          <a class="dropdown-item" href="治理效果追踪分析报告.html"><span class="badge">#7</span>治理效果追踪分析报告</a>
        </div>
      </div>
    </div>
  </div>
</div>"""

CSS = """<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Microsoft YaHei","PingFang SC","Helvetica Neue",sans-serif; background:#f0f2f5; color:#333; line-height:1.8; }
  .header { background:linear-gradient(135deg,#1a3a5f 0%,#2c5282 100%); color:#fff; padding:40px 0; text-align:center; }
  .header h1 { font-size:26px; font-weight:700; letter-spacing:1px; }
  .header .subtitle { font-size:14px; margin-top:8px; opacity:.85; }
  .header .meta { font-size:12px; margin-top:10px; opacity:.6; }
  .container { max-width:1100px; margin:0 auto; padding:28px 20px; }

  .stats-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
  .stat-card { background:#fff; border-radius:12px; padding:20px 16px; text-align:center; box-shadow:0 2px 12px rgba(0,0,0,.06); position:relative; overflow:hidden; }
  .stat-card::before { content:''; position:absolute; top:0; left:0; width:4px; height:100%; background:#1890ff; }
  .stat-card.green::before { background:#52c41a; } .stat-card.red::before { background:#f5222d; }
  .stat-card.orange::before { background:#fa8c16; } .stat-card.purple::before { background:#7b1fa2; }
  .stat-label { font-size:12px; color:#888; margin-bottom:6px; }
  .stat-value { font-size:30px; font-weight:700; line-height:1.2; color:#1a3a5f; }
  .stat-card.green .stat-value { color:#52c41a; } .stat-card.red .stat-value { color:#f5222d; }
  .stat-card.orange .stat-value { color:#fa8c16; } .stat-card.purple .stat-value { color:#7b1fa2; }
  .stat-unit { font-size:13px; font-weight:400; margin-left:3px; }
  .stat-sub { font-size:11px; color:#999; margin-top:4px; }

  .section { background:#fff; border-radius:12px; padding:26px 28px; margin-bottom:22px; box-shadow:0 2px 12px rgba(0,0,0,.05); }
  .section-title { font-size:19px; font-weight:700; color:#1a3a5f; margin-bottom:6px; display:flex; align-items:center; }
  .section-title::before { content:''; width:6px; height:22px; background:#1890ff; border-radius:3px; margin-right:12px; flex-shrink:0; }
  .section-desc { font-size:13px; color:#888; margin-bottom:18px; margin-left:18px; }
  .sub-title { font-size:15px; font-weight:700; color:#2c5282; margin:22px 0 10px; padding-left:10px; border-left:3px solid #1890ff; }
  .chart-box { width:100%; height:360px; }
  .chart-box.tall { height:440px; }
  .chart-box.mid { height:320px; }
  .chart-box.wordcloud { height:660px; max-width:470px; margin:0 auto; }
  .wc-note { max-width:470px; margin:6px auto 0; text-align:center; font-size:11.5px; color:#94a3b8; line-height:1.6; }

  .data-table { width:100%; border-collapse:collapse; margin-top:12px; font-size:12.5px; }
  .data-table th { background:#1a3a5f; color:#fff; padding:9px 10px; text-align:center; font-weight:600; font-size:12px; }
  .data-table td { padding:7px 10px; text-align:center; border-bottom:1px solid #eee; }
  .data-table tr:nth-child(even) { background:#fafafa; }
  .data-table tr:hover { background:#e6f7ff; }
  .data-table td.left { text-align:left; }
  .decline { color:#52c41a; font-weight:600; }
  .increase { color:#f5222d; font-weight:600; }
  .rank-1 { background:#fff7e6 !important; font-weight:700; }

  .tabs { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px; padding:12px 0; background:#fff;
          position:sticky; top:48px; z-index:900; border-bottom:1px solid #f0f0f0;
          box-shadow:0 6px 10px -6px rgba(0,0,0,.10); }
  .tab-btn { padding:6px 14px; font-size:12.5px; border:1px solid #d9d9d9; background:#fff; border-radius:18px; cursor:pointer; color:#555; transition:all .2s; }
  .tab-btn:hover { border-color:#1890ff; color:#1890ff; }
  .tab-btn.active { background:#1890ff; border-color:#1890ff; color:#fff; font-weight:600; }
  .tab-panel { display:none; }
  .tab-panel.active { display:block; }

  .rank-tabs { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 14px; }
  .rank-tab-btn { padding:7px 18px; font-size:13px; border:1px solid #d9d9d9; background:#fff; border-radius:18px; cursor:pointer; color:#555; transition:all .2s; }
  .rank-tab-btn:hover { border-color:#1890ff; color:#1890ff; }
  .rank-tab-btn.active { background:#1890ff; border-color:#1890ff; color:#fff; font-weight:600; }
  .rank-panel { display:none; }
  .rank-panel.active { display:block; }

  .kpi-row { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:6px; }
  .kpi { background:#f6f8fa; border-radius:8px; padding:12px 14px; }
  .kpi .k { font-size:11px; color:#888; } .kpi .v { font-size:20px; font-weight:700; color:#1a3a5f; }
  .kpi .v.up { color:#f5222d; } .kpi .v.down { color:#52c41a; }

  .insight-list { list-style:none; }
  .insight-list li { position:relative; padding:8px 0 8px 22px; font-size:13.5px; color:#444; border-bottom:1px dashed #eee; }
  .insight-list li::before { content:'▸'; position:absolute; left:4px; color:#1890ff; font-weight:700; }

  .chip-wrap { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
  .chip { background:#f0f5ff; color:#2c5282; font-size:12px; padding:4px 12px; border-radius:14px; border:1px solid #d6e4ff; }
  .chip .c { color:#888; font-size:11px; margin-left:4px; }

  .badge-lv { display:inline-block; font-size:11px; padding:1px 8px; border-radius:10px; color:#fff; font-weight:600; }
  .lv-red { background:#f5222d; } .lv-orange { background:#fa8c16; }
  .lv-yellow { background:#e6b800; } .lv-blue { background:#1890ff; }

  .note-box { background:#fffbe6; border-left:4px solid #faad14; border-radius:8px; padding:14px 18px; font-size:12.5px; color:#7a5c00; margin-bottom:20px; }
  .note-box b { color:#ad6800; }
  .ext-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:10px; }
  .ext-card { background:#f6f8fa; border-radius:8px; padding:12px 14px; font-size:12.5px; }
  .ext-card .ext-t { font-size:12px; font-weight:700; color:#2c5282; margin-bottom:6px; }
  .ext-card .ext-v { color:#555; }
  .ext-card .ext-v span { color:#1a3a5f; font-weight:700; }

  .footer { text-align:center; padding:28px 0; font-size:12px; color:#999; }
  .nav-bar { background:#fff; border-bottom:1px solid #e8e8e8; position:sticky; top:0; z-index:1000; box-shadow:0 1px 4px rgba(0,0,0,.06); }
  .nav-inner { max-width:1100px; margin:0 auto; padding:0 16px; display:flex; align-items:center; height:48px; }
  .nav-logo { font-size:14px; font-weight:700; color:#0d47a1; text-decoration:none; }
  .nav-back { font-size:12px; color:#0d47a1; text-decoration:none; margin-left:12px; }
  .nav-links { margin-left:auto; display:flex; gap:16px; }
  .nav-links a { font-size:12px; color:#666; text-decoration:none; }
  .nav-dropdown { position:relative; display:inline-block; }
  .nav-dropdown > a { display:inline-block; padding:4px 0; font-size:12px; color:#666; text-decoration:none; }
  .nav-dropdown > a::after { content:' ▾'; font-size:10px; opacity:.6; }
  .dropdown-menu { position:absolute; top:100%; left:50%; transform:translateX(-50%) translateY(8px); min-width:260px; background:#fff; border-radius:10px; box-shadow:0 4px 20px rgba(0,0,0,.12); padding:8px 0; opacity:0; visibility:hidden; transition:all .25s; z-index:1001; border:1px solid #f0f0f0; }
  .nav-dropdown:hover .dropdown-menu { opacity:1; visibility:visible; transform:translateX(-50%) translateY(0); }
  .dropdown-item { display:block; padding:8px 16px; font-size:12px; color:#444 !important; text-decoration:none; }
  .dropdown-item:hover { background:#e3f2fd; color:#0d47a1 !important; }
  .dropdown-item .badge { display:inline-block; font-size:10px; padding:1px 6px; border-radius:8px; background:#e3f2fd; color:#1565c0; margin-right:6px; font-weight:600; }
  .dropdown-divider { height:1px; background:#f0f0f0; margin:6px 0; }

  @media(max-width:900px) {
    .stats-grid, .kpi-row { grid-template-columns:repeat(2,1fr); }
    .ext-grid { grid-template-columns:1fr; }
  }
</style>"""


def overview_section(data):
    ov = data["overview"]
    d = data["district"]
    top = ov[0]
    up = [r for r in ov if (r["yoy"] or 0) > 0]
    dup_best = min([r for r in ov if r["dup_rate"]], key=lambda x: x["dup_rate"])
    dup_worst = max([r for r in ov if r["dup_rate"]], key=lambda x: x["dup_rate"])

    district_decline = d["n2025_same"] - d["n2026"]
    top5_contrib = pct_sum(
        sorted([r["contribution"] for r in ov if r["contribution"] is not None], reverse=True)[:5])

    notes = "".join(f"<div>· {x}</div>" for x in data["meta"]["notes"])

    rows = []
    for r in ov:
        s = data["streets"][r["street"]]
        rows.append(f"""<tr{' class="rank-1"' if r['rank_total'] == 1 else ''}>
  <td>{r['rank_total']}</td>
  <td class="left"><b>{r['street']}</b></td>
  <td>{n(r['n2026'])}</td>
  <td>{n(r['n2025_same'])}</td>
  <td style="color:{color_of(r['yoy'])};font-weight:700;">{pct_txt(r['yoy'])}</td>
  <td>{r['rank_yoy']}</td>
  <td>{r['share']}%</td>
  <td>{'—' if r['contribution'] is None else str(r['contribution']) + '%'}</td>
  <td>{n(r['communities'])}</td>
  <td>{'—' if r['dup_rate'] is None else str(r['dup_rate']) + '%'}</td>
  <td>{n(r['dup_high'])}</td>
  <td><span class="badge-lv lv-red">{r['risk_red']}</span> / {r['risk_orange']}</td>
</tr>""")

    dens_rows = []
    for r in sorted([x for x in ov if x.get("density") is not None],
                    key=lambda x: x["rank_density"]):
        gap = r["rank_total"] - r["rank_density"]      # 正 = 密度位次领先于总量位次
        gap_txt = "—" if gap == 0 else (f"+{gap}" if gap > 0 else str(gap))
        gap_color = "#f5222d" if gap > 0 else ("#52c41a" if gap < 0 else "#888")
        dens_rows.append(f"""<tr{' class="rank-1"' if r['rank_density'] == 1 else ''}>
  <td>{r['rank_density']}</td>
  <td class="left"><b>{r['street']}</b></td>
  <td style="font-weight:700;color:#1890ff;">{r['density']}</td>
  <td>{n(r['n2026'])}</td>
  <td>{n(r['households'])}</td>
  <td>{n(r['communities'])}</td>
  <td>{r['density_per_community']}</td>
  <td>{r['rank_total']}</td>
  <td style="color:{gap_color};font-weight:700;">{gap_txt}</td>
  <td style="color:{color_of(r['yoy'])};font-weight:700;">{pct_txt(r['yoy'])}</td>
  <td>{r['share']}%</td>
</tr>""")

    return f"""<div class="note-box">
  <b>口径说明</b>
  {notes}
  <div>· 重复投诉口径：同小区内容完全重复 ∪ 催办关键词 ∪ 同小区同类≥3次 ∪ 文本相似≥0.6，逐月独立去重后汇总</div>
</div>

<div class="stats-grid">
  <div class="stat-card green">
    <div class="stat-label">全区2026年1-8月投诉量</div>
    <div class="stat-value">{n(d['total_all'])}<span class="stat-unit">件</span></div>
    <div class="stat-sub">同比 {pct_txt(d['yoy'])}，减少 {n(d['n2025_same'] - d['n2026'])} 件</div>
  </div>
  <div class="stat-card blue">
    <div class="stat-label">13个街镇投诉量合计</div>
    <div class="stat-value">{n(d['n2026'])}<span class="stat-unit">件</span></div>
    <div class="stat-sub">占全区 {round(d['n2026'] / d['total_all'] * 100, 1)}%（另 {d['unassigned']} 件归属待确认）</div>
  </div>
  <div class="stat-card orange">
    <div class="stat-label">降幅最大街镇</div>
    <div class="stat-value">{top['street']}</div>
    <div class="stat-sub">同比 {pct_txt(top['yoy'])}，占全区下降 {top['contribution']}%</div>
  </div>
  <div class="stat-card red">
    <div class="stat-label">同比上升街镇</div>
    <div class="stat-value">{len(up)}<span class="stat-unit">个</span></div>
    <div class="stat-sub">{'、'.join(x['street'] + pct_txt(x['yoy']) for x in up) if up else '无'}</div>
  </div>
</div>

<div class="section">
  <div class="section-title">一、13个街镇单独分析</div>
  <div class="section-desc">点击下方街镇名称切换，查看该街镇的趋势、归因、结构、热点、重复与风险全维度画像；切换栏已吸顶，向下滚动查看图表时仍可随时切换街镇</div>
  <div class="tabs" id="street-tabs">{''.join(f'<button class="tab-btn{" active" if i == 0 else ""}" data-tab="{i}">{r["street"]}</button>' for i, r in enumerate(ov))}</div>
  {''.join(street_panel(i, data["streets"][r["street"]], r, i == 0) for i, r in enumerate(ov))}
</div>

<div class="section">
  <div class="section-title">二、全区街镇总表</div>
  <div class="section-desc">总量排名看规模负担，投诉密度排名看单位居民投诉强度（件/千户）；两张表可切换查看</div>
  <div class="rank-tabs">
    <button class="rank-tab-btn active" data-rank="rank-total">总量排名</button>
    <button class="rank-tab-btn" data-rank="rank-density">投诉密度排名</button>
  </div>

  <div class="rank-panel active" id="rank-total">
    <div class="section-desc">13个街镇 2026年1-8月 投诉量与同比表现（按投诉量排序）；降幅排名 1 为下降最多；重复率为逐月独立去重口径</div>
    <table class="data-table">
      <tr>
        <th>总量<br>排名</th><th>街镇</th><th>2026年<br>1-8月</th><th>2025年<br>1-8月</th>
        <th>同比</th><th>降幅<br>排名</th><th>占全区</th><th>下降<br>贡献率</th>
        <th>有投诉<br>小区数</th><th>重复率</th><th>高优先级<br>重复件</th><th>红色/橙色<br>预警小区</th>
      </tr>
      {''.join(rows)}
    </table>
  </div>

  <div class="rank-panel" id="rank-density">
    <div class="section-desc">投诉密度 = 2026年1-8月投诉量 ÷ 户数 × 1000（<b>件/千户</b>），衡量平均每千户居民的投诉强度；户数为该街镇「2026年1-8月有投诉小区」的总户数（取自纳统小区档案 total_households）。位次差 = 总量排名 − 密度排名，正数表示该街镇"总量不大但单位居民投诉更重"；末列「件/小区」为对照口径</div>
    <table class="data-table">
      <tr>
        <th>密度<br>排名</th><th>街镇</th><th>投诉密度<br>（件/千户）</th><th>2026年<br>1-8月</th>
        <th>户数</th><th>有投诉<br>小区数</th><th>件/小区<br>（对照）</th><th>总量<br>排名</th><th>位次差</th><th>同比</th><th>占全区</th>
      </tr>
      {''.join(dens_rows)}
    </table>
  </div>
</div>

<div class="section">
  <div class="section-title">三、街镇投诉量对比与降幅</div>
  <div class="section-desc">柱状为 2026年与 2025年 同期投诉量，折线为同比降幅（负值表示下降）</div>
  <div id="ov-compare" class="chart-box tall"></div>
</div>

<div class="section">
  <div class="section-title">四、对全区下降的贡献度排行</div>
  <div class="section-desc">贡献率 = 该街镇减少量 ÷ 全区减少量；{n(district_decline)} 件的全区降幅中，前 5 个街镇贡献了 {top5_contrib}%</div>
  <div id="ov-contribution" class="chart-box tall"></div>
</div>

<div class="section">
  <div class="section-title">五、街镇 × 月度热力（2026年1-8月）</div>
  <div class="section-desc">颜色越深表示当月投诉量越大，可快速定位"某镇某月异常抬头"</div>
  <div id="ov-heatmap" class="chart-box tall"></div>
</div>"""


def street_panel(i, s, r, active):
    c = s["core"]
    kpi = f"""<div class="kpi-row">
  <div class="kpi"><div class="k">2026年1-8月投诉量</div><div class="v">{n(c['n2026'])}</div></div>
  <div class="kpi"><div class="k">同比变化</div><div class="v {'up' if (c['yoy'] or 0) > 0 else 'down'}">{pct_txt(c['yoy'])}</div></div>
  <div class="kpi"><div class="k">占全区比重</div><div class="v">{c['share']}%</div></div>
  <div class="kpi"><div class="k">对全区下降贡献</div><div class="v">{'—' if c['contribution'] is None else str(c['contribution']) + '%'}</div></div>
  <div class="kpi"><div class="k">总量/降幅排名</div><div class="v">第{c['rank_total']}/第{c['rank_yoy']}</div></div>
  <div class="kpi"><div class="k">有投诉小区数</div><div class="v">{n(c['active_communities'])}</div></div>
  <div class="kpi"><div class="k">重复投诉率</div><div class="v">{'—' if not s['dup'] else str(s['dup']['rate']) + '%'}</div><div class="k" style="font-size:10px;">全区 {r.get('district_dup_rate', '')}</div></div>
  <div class="kpi"><div class="k">红色/橙色预警小区</div><div class="v">{s['risk']['red']}/{s['risk']['orange']}</div></div>
</div>"""

    # 类别表
    cat_rows = "".join(
        f"<tr><td class='left'>{x['cat']}</td><td>{n(x['n2026'])}</td><td>{n(x['n2025'])}</td>"
        f"<td class='{'increase' if x['delta'] > 0 else ('decline' if x['delta'] < 0 else '')}'>{x['delta']:+d}</td>"
        f"<td class='{'increase' if (x['yoy'] or 0) > 0 else 'decline'}'>{pct_txt(x['yoy'])}</td>"
        f"<td>{x['pct']}%</td><td>{x['district_pct']}%</td></tr>"
        for x in s["category"])

    # Top 小区
    comm_rows = "".join(
        f"<tr><td>{i2}</td><td class='left'>{x['name']}</td><td>{n(x['n2026'])}</td>"
        f"<td>{n(x['n2025'])}</td>"
        f"<td class='{'increase' if (x['yoy'] or 0) > 0 else 'decline'}'>{pct_txt(x['yoy'])}</td>"
        f"<td>{x['pct']}%</td><td>{x['top_category']}</td><td>{x['freq_groups']}</td></tr>"
        for i2, x in enumerate(s["top_communities"], 1))

    # 地址热点
    addr_rows = "".join(
        f"<tr><td>{i2}</td><td class='left'>{x['addr']}</td><td>{n(x['n2026'])}</td>"
        f"<td>{n(x['n2025'])}</td>"
        f"<td class='{'increase' if x['n2026'] > x['n2025'] else 'decline'}'>"
        f"{x['n2026'] - x['n2025']:+d}</td><td>{x['top_category']}</td></tr>"
        for i2, x in enumerate(s["addresses"], 1))

    # 企业
    comp_rows = "".join(
        f"<tr><td>{i2}</td><td class='left'>{x['name']}</td><td>{n(x['n2026'])}</td>"
        f"<td>{n(x['n2025'])}</td>"
        f"<td class='{'increase' if (x['yoy'] or 0) > 0 else 'decline'}'>{pct_txt(x['yoy'])}</td>"
        f"<td>{x['pct']}%</td><td>{x['communities']}</td></tr>"
        for i2, x in enumerate(s["companies"], 1))

    # 风险 Top5
    risk_rows = "".join(
        f"<tr><td>{i2}</td><td class='left'>{x['community']}</td>"
        f"<td><b>{x['score']}</b></td>"
        f"<td><span class='badge-lv {LEVEL_CLASS.get(x['level'], 'lv-blue')}'>{x['level'] or '—'}</span></td>"
        f"<td>{n(x['total'])}</td>"
        f"<td class='increase'>{pct_txt(x['growth_rate'])}</td>"
        f"<td>{x['repeat_rate']}%</td><td>{x['top_category']}</td></tr>"
        for i2, x in enumerate(s["risk"]["top"], 1))

    # 治理案例
    cases = s["governance"].get("cases_success", []) + s["governance"].get("cases_rebound", []) + \
            s["governance"].get("cases_worsening", [])
    case_html = ""
    if cases:
        rows = "".join(
            f"<tr><td class='left'>{x['community']}</td><td>{x['kind']}</td>"
            f"<td>{n(x['n2024'])}</td><td>{n(x['n2025'])}</td>"
            f"<td>{n(x['n2025_same'])}</td><td>{n(x['n2026'])}</td>"
            f"<td class='{'decline' if (x['improvement_2026'] or 0) > 0 else 'increase'}'>"
            f"{pct_txt(x['improvement_2026'])}</td><td>{x['top_category']}</td></tr>"
            for x in cases)
        case_html = f"""<div class="sub-title">治理追踪案例（2026年1-8月同期口径）</div>
<table class="data-table">
  <tr><th>小区</th><th>类型</th><th>2024<br>全年</th><th>2025<br>全年</th>
      <th>2025年<br>1-8月</th><th>2026年<br>1-8月</th><th>同期<br>同比</th><th>首要类别</th></tr>
  {rows}
</table>"""

    # 外部数据
    ext = s["externals"]
    ext_cards = []
    if ext.get("elevator"):
        e = ext["elevator"]
        ext_cards.append(f"""<div class="ext-card"><div class="ext-t">电梯加装（区房管局）</div>
      <div class="ext-v">涉及 <span>{n(e['total'])}</span> 台，覆盖 <span>{n(e['communities'])}</span> 个小区<br>
      完工 <span>{n(e['done'])}</span> 台 · 在建 <span>{n(e['building'])}</span> 台</div></div>""")
    if ext.get("expropriation"):
        e = ext["expropriation"]
        ext_cards.append(f"""<div class="ext-card"><div class="ext-t">征收基地（区房管局）</div>
      <div class="ext-v">基地 <span>{n(e['projects'])}</span> 个 · 户数 <span>{n(e['households'])}</span> 户<br>
      涉及面积 <span>{n(e['area'])}</span> ㎡</div></div>""")
    if ext.get("renovation"):
        e = ext["renovation"]
        ext_cards.append(f"""<div class="ext-card"><div class="ext-t">修缮项目（按小区名关联）</div>
      <div class="ext-v">项目 <span>{n(e['projects'])}</span> 个 · 总投资 <span>{n(e['investment'])}</span> 万元<br>
      建筑面积 <span>{n(e['area'])}</span> ㎡</div></div>""")
    ext_html = ""
    if ext_cards:
        ext_html = f"""<div class="sub-title">外部数据关联（区房管局各科室业务数据）</div>
<div class="ext-grid">{''.join(ext_cards)}</div>"""


    # 来源 / 工单类型 / 质量
    src_rows = "".join(f"<tr><td class='left'>{x['name']}</td><td>{n(x['cnt'])}</td><td>{x['pct']}%</td></tr>"
                       for x in s["sources"])
    ot_rows = "".join(f"<tr><td class='left'>{x['name']}</td><td>{n(x['cnt'])}</td><td>{x['pct']}%</td></tr>"
                      for x in s["order_types"])
    q = s["quality"]
    q_rows = (f"<tr><td class='left'>小区名未匹配</td><td>{q['miss_community_pct']}%</td></tr>"
              f"<tr><td class='left'>小区地址缺失</td><td>{q['miss_addr_pct']}%</td></tr>"
              f"<tr><td class='left'>来源渠道缺失</td><td>{q['miss_source_pct']}%</td></tr>"
              f"<tr><td class='left'>无物业企业（自管/无）</td><td>{q['no_company_pct']}%</td></tr>")

    dup = s["dup"]
    dup_html = ""
    if dup:
        dup_html = f"""<div class="sub-title">重复投诉（逐月独立去重口径）</div>
<div class="kpi-row">
  <div class="kpi"><div class="k">重复投诉件数</div><div class="v">{n(dup['dup_count'])}</div></div>
  <div class="kpi"><div class="k">重复率</div><div class="v">{dup['rate']}%</div></div>
  <div class="kpi"><div class="k">高优先级</div><div class="v">{n(dup['high_count'])}</div></div>
  <div class="kpi"><div class="k">中优先级</div><div class="v">{n(dup['mid_count'])}</div></div>
</div>
<table class="data-table">
  <tr><th>策略</th><th>识别件数</th><th>组数</th><th>说明</th></tr>
  <tr><td>S1 完全重复</td><td>{n(dup['s1'])}</td><td>{n(dup['s1_groups'])}</td><td class="left">同小区内容完全一致</td></tr>
  <tr><td>S2 催办关键词</td><td>{n(dup['s2'])}</td><td>—</td><td class="left">催单/重新交办/反复/相同事项</td></tr>
  <tr><td>S3 同小区同类高频</td><td>{n(dup['s3'])}</td><td>{n(dup['s3_groups'])}</td><td class="left">同小区同十四类≥3次</td></tr>
  <tr><td>S4 文本相似</td><td>{n(dup['s4'])}</td><td>{n(dup['s4_pairs'])}</td><td class="left">TF-IDF 余弦≥0.6 且 90 天内</td></tr>
</table>"""

    gov = s["governance"]
    gov_html = ""
    if gov.get("effect_2026") is not None:
        gov_html = f"""<div class="sub-title">治理成效（2026年1-8月同期口径）</div>
<div class="kpi-row">
  <div class="kpi"><div class="k">2026年1-8月</div><div class="v">{n(gov['volume_2026_h1'])}</div></div>
  <div class="kpi"><div class="k">2025年同期</div><div class="v">{n(gov['volume_2025_h1'])}</div></div>
  <div class="kpi"><div class="k">同比改善率</div><div class="v {'down' if gov['effect_2026'] > 0 else 'up'}">{pct_txt(gov['effect_2026'], 1)}</div></div>
  <div class="kpi"><div class="k">2025全年</div><div class="v">{n(gov['volume_2025'])}</div></div>
</div>"""

    insights = "".join(f"<li>{x}</li>" for x in s["insights"])
    bl = s["bottom_lift"]
    bl_html = (f"<div class='chip' style='background:#e6fffb;border-color:#b5f5ec;color:#006d75;'>"
               f"党建引领重点小区 {bl['count']} 个</div>") if bl["count"] else ""

    return f"""<div class="tab-panel{' active' if active else ''}" id="panel-{i}">
  {kpi}

  <div class="sub-title">趋势与同比</div>
  <div id="c{i}-trend" class="chart-box"></div>
  <div id="c{i}-yoy" class="chart-box mid"></div>
  <div id="c{i}-quarter" class="chart-box mid"></div>

  <div class="sub-title">下降归因：类别增减分解</div>
  <div id="c{i}-catdelta" class="chart-box tall"></div>
  <table class="data-table">
    <tr><th>十四类</th><th>2026年1-8月</th><th>2025年同期</th><th>同期增减</th><th>同比</th><th>占本镇</th><th>占全区</th></tr>
    {cat_rows}
  </table>

  <div class="sub-title">结构画像</div>
  <div id="c{i}-catdonut" class="chart-box tall"></div>
  <table class="data-table">
    <tr><th colspan="3" style="background:#2c5282;">来源渠道</th></tr>
    <tr><th>渠道</th><th>件数</th><th>占比</th></tr>
    {src_rows}
  </table>
  <table class="data-table">
    <tr><th colspan="3" style="background:#2c5282;">工单类型</th></tr>
    <tr><th>类型</th><th>件数</th><th>占比</th></tr>
    {ot_rows}
  </table>

  <div class="sub-title">热点对象</div>
  <table class="data-table">
    <tr><th colspan="8" style="background:#2c5282;">投诉最集中小区 Top10</th></tr>
    <tr><th>#</th><th>小区</th><th>2026年1-8月</th><th>2025年同期</th><th>同比</th><th>占本镇</th><th>首位类别</th><th>高频组数</th></tr>
    {comm_rows}
  </table>
  <table class="data-table">
    <tr><th colspan="6" style="background:#2c5282;">地址级热点（可下派核查的具体地址）</th></tr>
    <tr><th>#</th><th>地址</th><th>2026年1-8月</th><th>2025年同期</th><th>增减</th><th>首要类别</th></tr>
    {addr_rows}
  </table>
  <table class="data-table">
    <tr><th colspan="6" style="background:#2c5282;">物业企业投诉 Top10</th></tr>
    <tr><th>#</th><th>企业</th><th>2026年1-8月</th><th>2025年同期</th><th>同比</th><th>占本镇 / 涉及小区</th></tr>
    {comp_rows}
  </table>
  <div class="sub-title">诉求主题词（已过滤工单模板用语）</div>
  <div id="c{i}-wordcloud" class="chart-box wordcloud"></div>
  <div class="wc-note">词云轮廓＝徐汇区行政区域边界 ｜ 字号＝词频，展示 Top24</div>

  <div class="sub-title">重复投诉与数据质量</div>
  {dup_html}
  <table class="data-table">
    <tr><th colspan="2" style="background:#2c5282;">数据质量画像</th></tr>
    <tr><th>检查项</th><th>占比</th></tr>
    {q_rows}
  </table>

  <div class="sub-title">风险预警与治理成效</div>
  <div class="kpi-row">
    <div class="kpi"><div class="k">红色预警小区</div><div class="v up">{s['risk']['red']}</div></div>
    <div class="kpi"><div class="k">橙色预警小区</div><div class="v" style="color:#fa8c16;">{s['risk']['orange']}</div></div>
    <div class="kpi"><div class="k">黄色 / 蓝色</div><div class="v">{s['risk']['yellow']} / {s['risk']['blue']}</div></div>
    <div class="kpi"><div class="k">参评小区数</div><div class="v">{n(s['risk']['total'])}</div></div>
  </div>
  <table class="data-table">
    <tr><th>#</th><th>小区</th><th>风险分</th><th>等级</th><th>三年累计<br>投诉量</th><th>同比增长率</th><th>重复率</th><th>首要类别</th></tr>
    {risk_rows}
  </table>
  {gov_html}
  {case_html}
  {ext_html}
  <div class="chip-wrap">{bl_html}</div>

  <div class="sub-title">结论要点</div>
  <ul class="insight-list">{insights}</ul>
</div>"""


def build_html(data):
    # 全区重复率注入每行（供分页 KPI 展示对比）
    dr = data["district"]["dup"]["rate"] if data["district"].get("dup") else None
    for r in data["overview"]:
        r["district_dup_rate"] = f"{dr}%" if dr is not None else ""

    streets = [data["streets"][r["street"]] for r in data["overview"]]
    charts = {
        "ov-compare": chart_overview_compare(data["overview"]),
        "ov-contribution": chart_overview_contribution(data["overview"]),
    }
    for i, s in enumerate(streets):
        charts[f"c{i}-trend"] = chart_monthly_trend(s["name"], s)
        charts[f"c{i}-yoy"] = chart_yoy_monthly(s)
        charts[f"c{i}-catdelta"] = chart_category_delta(s)
        charts[f"c{i}-catdonut"] = chart_category_donut(s)
        charts[f"c{i}-quarter"] = chart_same_period(s)
        wc = chart_wordcloud(s.get("keywords") or [])
        if wc:
            charts[f"c{i}-wordcloud"] = wc

    charts_js = json.dumps(charts, ensure_ascii=False)

    # 词云遮罩（徐汇区行政边界）内联为 dataURL；缺失则降级为圆形词云
    _b64 = load_mask_b64()
    mask_js = json.dumps("data:image/png;base64," + _b64) if _b64 else "null"

    heat = chart_street_heatmap(data["overview"], streets)
    heat_js = json.dumps(heat, ensure_ascii=False)
    heat_js = (heat_js[:-1] +
               ', "tooltip": {"formatter": function(p){ return p.value[1] + " " + p.marker + '
               'p.value[2] + " 件"; }} }')

    header = f"""<div class="header">
  <h1>徐汇区12345物业投诉 · 街镇专项分析报告</h1>
  <div class="subtitle">数据周期：2024年1月 — {data['meta']['period_label'][:4]}年8月 ｜ 13个街镇 × 7组维度 ｜ 同比口径：{data['meta']['period_label']} vs {data['meta']['compare_label']}</div>
  <div class="meta">徐汇物业课题一期 · 核心成果一·附 · 口径：12345热线物业类投诉全量（含归属为空 {data['district']['unassigned']} 件单列）</div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>徐汇区12345物业投诉 · 街镇专项分析报告</title>
{CSS}
</head>
<body>
{NAV}
{header}
<div class="container">
{overview_section(data)}
</div>
<div class="footer">
  徐汇区物业课题一期项目 · 数据分析中心 · 2026年9月 · 数据截至 2026年8月
</div>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts-wordcloud@2.1.0/dist/echarts-wordcloud.min.js"></script>
<script>
var CHARTS = {{}};
var OPTS = {charts_js};
OPTS['ov-heatmap'] = {heat_js};

// 词云遮罩：徐汇区行政区域边界（黑色形状 + 透明背景，内联 base64）
// 边界数据来源：高德开放平台行政区划（徐汇区 adcode 310104），仅用于词云轮廓示意
var WC_MASK_SRC = {mask_js};
var WC_MASK = null, WC_MASK_READY = false;
if (WC_MASK_SRC) {{
  WC_MASK = new Image();
  WC_MASK.onload = function () {{ WC_MASK_READY = true; initCharts(document); resizeVisible(); }};
  WC_MASK.onerror = function () {{ WC_MASK = null; WC_MASK_READY = true; initCharts(document); resizeVisible(); }};
  WC_MASK.src = WC_MASK_SRC;
}} else {{
  WC_MASK_READY = true;
}}

function initCharts(scope) {{
  scope.querySelectorAll('.chart-box[id]').forEach(function (el) {{
    if (!OPTS[el.id]) return;
    // 隐藏面板（display:none）内尺寸为 0，此时初始化会得到被压扁的图表，跳过，等切到该标签再画
    if (!el.clientWidth || !el.clientHeight) return;
    if (CHARTS[el.id]) {{ CHARTS[el.id].resize(); return; }}
    var opt = OPTS[el.id];
    // 词云：等边界遮罩就绪后再画（就绪前跳过，onload 回调里会重试）
    if (el.id.indexOf('wordcloud') >= 0) {{
      if (!WC_MASK_READY) return;
      if (WC_MASK) opt.series[0].maskImage = WC_MASK;
    }}
    var c = echarts.init(el);
    c.setOption(opt);
    CHARTS[el.id] = c;
  }});
}}

// 排名表切换（总量 / 投诉密度），与街镇切换互不影响
document.querySelectorAll('.rank-tab-btn').forEach(function (btn) {{
  btn.addEventListener('click', function () {{
    document.querySelectorAll('.rank-tab-btn').forEach(function (b) {{ b.classList.remove('active'); }});
    document.querySelectorAll('.rank-panel').forEach(function (p) {{ p.classList.remove('active'); }});
    btn.classList.add('active');
    var panel = document.getElementById(btn.dataset.rank);
    if (panel) panel.classList.add('active');
  }});
}});

// 标签页切换
document.querySelectorAll('.tab-btn').forEach(function (btn) {{
  btn.addEventListener('click', function () {{
    document.querySelectorAll('.tab-btn').forEach(function (b) {{ b.classList.remove('active'); }});
    document.querySelectorAll('.tab-panel').forEach(function (p) {{ p.classList.remove('active'); }});
    btn.classList.add('active');
    var panel = document.getElementById('panel-' + btn.dataset.tab);
    panel.classList.add('active');
    // 若街镇切换栏不在吸顶位置，把视图带回标签栏顶部，从该街镇画像的开头看起
    var bar = document.getElementById('street-tabs');
    var navH = document.querySelector('.nav-bar') ? document.querySelector('.nav-bar').offsetHeight : 0;
    if (bar && bar.getBoundingClientRect().top > navH + 4) {{
      window.scrollBy(0, bar.getBoundingClientRect().top - navH - 4);
    }}
    // 立即初始化（读取 clientWidth 会强制浏览器完成布局，此时宽度已可用）
    initCharts(panel);
    // 再补一帧：只重算当前可见面板内的图表（隐藏面板宽为 0，重算会被压成 100px 兜底宽）
    window.requestAnimationFrame(function () {{
      initCharts(panel);
      resizeVisible();
    }});
  }});
}});

// 对「当前可见」的图表重算尺寸，隐藏面板里的跳过
function resizeVisible() {{
  Object.keys(CHARTS).forEach(function (k) {{
    var el = CHARTS[k].getDom();
    if (el && el.clientWidth) CHARTS[k].resize();
  }});
}}

// 首屏初始化（隐藏面板会被自动跳过）
initCharts(document);
window.addEventListener('load', function () {{
  initCharts(document);
  resizeVisible();
}});
var _rt;
window.addEventListener('resize', function () {{
  clearTimeout(_rt);
  _rt = setTimeout(resizeVisible, 120);
}});
</script>
</body>
</html>"""


def main():
    data = json.load(open(DATA, encoding="utf-8"))
    html = build_html(data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    n_wc = sum(1 for s in data["streets"].values() if s.get("keywords"))
    n_chart = len(data["overview"]) * 5 + 3 + n_wc
    print(f"✔ 生成 {OUT}（{os.path.getsize(OUT)/1024:.1f} KB）")
    print(f"  街镇 {len(data['overview'])} 个 | 图表 {n_chart} 个（含 {n_wc} 张主题词词云）")


if __name__ == "__main__":
    main()
