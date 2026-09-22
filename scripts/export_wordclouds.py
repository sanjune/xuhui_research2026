#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 13 个街镇「诉求主题词」词云图（16:9 长方形边界）。

边界规则
--------
画布 1600×900（严格 16:9），词云填满矩形边界：
  - 不设 maskImage（echarts-wordcloud 缺省时布局区域为满矩形）
  - keepAspect=false，避免被收缩成正方形
  - width/height 100%，词不越界（drawOutOfBound=false）

渲染方式
--------
无头 Chrome 渲染 echarts-wordcloud（与《街镇专项分析报告》同一套配色与字号逻辑），
逐街镇截图导出 PNG；每个街镇一个独立 URL（?street=…），避免长页面截图的像素上限问题。

数据源：scripts/street_analysis.json → streets[].keywords（Top24，已过滤工单模板用语）
输出：词云图/<街镇>.png（1600×900）

用法：/usr/bin/python3 scripts/export_wordclouds.py
"""
import base64
import html
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "scripts", "street_analysis.json")
VENDOR = os.path.join(BASE, "assets", "vendor")
OUT_DIR = os.path.join(BASE, "词云图")
TMP_HTML = os.path.join(BASE, "scripts", "_wc_export.html")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

W, H = 1600, 900          # 16:9
SIZE_RANGE = [64, 240]    # 字号区间：实测填充率约 95%×88%（24词/画布）
GRID = 8
TOPN = 24
FONT = "'PingFang SC','Hiragino Sans GB','Heiti SC','Microsoft YaHei',sans-serif"

# 与 gen_street_report.py 保持一致的配色
WC_PALETTE = ["#1a3a5f", "#1890ff", "#13c2c2", "#52c41a", "#fa8c16",
              "#f5222d", "#7b1fa2", "#0f6e56"]


def build_html(streets):
    """生成导出用页面：按 ?street= 渲染对应街镇词云。"""
    payload = {}
    for name, kw in streets.items():
        items = sorted(kw, key=lambda x: -x["cnt"])[:TOPN]
        payload[name] = [{"name": x["word"], "value": x["cnt"],
                          "textStyle": {"color": WC_PALETTE[i % len(WC_PALETTE)]}}
                         for i, x in enumerate(items)]
    data_js = json.dumps(payload, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>街镇词云导出</title>
<style>
  html, body {{ margin:0; padding:0; background:#fff; }}
  #wc {{ width:{W}px; height:{H}px; }}
</style>
<script src="file://{VENDOR}/echarts.min.js"></script>
<script src="file://{VENDOR}/echarts-wordcloud.min.js"></script>
</head>
<body>
<div id="wc"></div>
<script>
var DATA = {data_js};
var name = decodeURIComponent((location.search.match(/street=([^&]*)/) || [])[1] || '');
var chart = echarts.init(document.getElementById('wc'));
if (DATA[name]) {{
  chart.setOption({{
    animation: false,
    series: [{{
      type: 'wordCloud',
      left: 0, top: 0, width: '{W}', height: '{H}',
      keepAspect: false,
      sizeRange: {json.dumps(SIZE_RANGE)},
      rotationRange: [0, 0],
      rotationStep: 0,
      gridSize: {GRID},
      drawOutOfBound: false,
      shrinkToFit: false,
      layoutAnimation: false,
      textStyle: {{ fontFamily: {json.dumps(FONT)}, fontWeight: 'normal' }},
      emphasis: {{ textStyle: {{ fontWeight: 'bold' }} }},
      data: DATA[name]
    }}]
  }});
  window.__wcReady = true;
}} else {{
  document.body.innerHTML = '<p>未知街镇：' + name + '</p>';
}}
</script>
</body>
</html>
"""


def main():
    d = json.load(open(DATA, encoding="utf-8"))
    # streets 形如 {街镇名: {name, keywords, ...}}
    streets = {k: (v.get("keywords") or []) for k, v in d["streets"].items()}
    streets = {k: v for k, v in streets.items() if v}
    print(f"街镇 {len(streets)} 个：{'、'.join(streets)}")

    os.makedirs(VENDOR, exist_ok=True)
    if not os.path.exists(os.path.join(VENDOR, "echarts.min.js")):
        sys.exit("缺少 assets/vendor/echarts.min.js，请先下载 vendor 依赖")
    if not os.path.exists(CHROME):
        sys.exit("未找到 Chrome")

    open(TMP_HTML, "w", encoding="utf-8").write(build_html(streets))
    os.makedirs(OUT_DIR, exist_ok=True)

    url_base = "file://" + urllib.parse.quote(TMP_HTML)
    ok, fail = [], []
    for i, name in enumerate(streets, 1):
        out = os.path.join(OUT_DIR, f"{name}.png")
        if os.path.exists(out):
            os.remove(out)
        url = f"{url_base}?street={urllib.parse.quote(name)}"
        cmd = [CHROME, "--headless", "--disable-gpu", "--no-sandbox",
               "--hide-scrollbars", "--force-device-scale-factor=1",
               f"--window-size={W},{H}", "--virtual-time-budget=6000",
               f"--screenshot={out}", url]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        if os.path.exists(out) and os.path.getsize(out) > 20000:
            ok.append(name)
            print(f"  [{i}/{len(streets)}] {name}.png  {os.path.getsize(out)//1024} KB")
        else:
            fail.append(name)
            print(f"  [{i}/{len(streets)}] {name} 失败")
        time.sleep(0.3)

    print(f"\n成功 {len(ok)} 张 → {OUT_DIR}")
    if fail:
        print("失败：", "、".join(fail))


if __name__ == "__main__":
    main()
