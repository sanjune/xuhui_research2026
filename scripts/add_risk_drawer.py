# -*- coding: utf-8 -*-
"""《高风险小区预警清单.html》第 9 项整改：预警等级卡片点击直达明细抽屉
================================================================================

整改清单第 9 项（方案二 · 范围收窄）：
  · 采用「抽屉」交互；可达范围**仅限「小区及数字」** —— 本轮落地为
    「各等级预警小区数 → 抽屉列出该等级小区清单」。
  · **不做**「重复投诉数」与「投诉总量」的明细展示。

实现方式（幂等，可重复执行）
---------------------------
1. 读 `scripts/risk_scores.json`（唯一数据源，100 分起扣制）→ 生成按等级分组的
   精简小区清单，以 `<script type="application/json" id="riskDrawerData">` 内嵌；
2. 在 `</style>` 前注入抽屉 CSS；在 `</body>` 前注入抽屉 DOM + 交互 JS；
3. 给 4 个等级卡片（红/橙/黄/蓝）加 `data-level` / `role=button` / `tabindex`，
   使其可点击、可键盘操作（Enter/Space），Esc 或点击遮罩关闭。

注意：`update_risk_report.py` 的等级卡正则已放宽为允许卡片带额外属性，
      两脚本可任意顺序重复执行。

用法
----
    python3 scripts/add_risk_drawer.py [--dry-run]
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RISK = os.path.join(ROOT, "scripts", "risk_scores.json")
REPORT = os.path.join(ROOT, "高风险小区预警清单.html")

LEVELS = ["红色", "橙色", "黄色", "蓝色"]
LEVEL_COLOR = {"红色": "#f5222d", "橙色": "#fa8c16", "黄色": "#faad14", "蓝色": "#1890ff"}
LEVEL_CLASS = {"红色": "red", "橙色": "orange", "黄色": "yellow", "蓝色": "blue"}

CSS = """
  /* ============ 第 9 项：预警小区明细抽屉 ============ */
  .stat-card[data-level] { cursor: pointer; transition: transform .15s ease, box-shadow .15s ease; }
  .stat-card[data-level]:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(0,0,0,.13); }
  .stat-card[data-level]:focus-visible { outline: 2px solid #1890ff; outline-offset: 2px; }
  .stat-card .drill-hint { font-size: 11px; color: #1890ff; margin-top: 3px; }
  .stat-card .drill-hint::after { content: " ▸"; }
  .risk-drawer-mask { position: fixed; inset: 0; background: rgba(15,23,42,.45);
    opacity: 0; visibility: hidden; transition: opacity .22s ease, visibility .22s ease; z-index: 9998; }
  .risk-drawer-mask.open { opacity: 1; visibility: visible; }
  .risk-drawer { position: fixed; top: 0; right: 0; height: 100%; width: min(900px, 94vw);
    background: #fff; box-shadow: -8px 0 28px rgba(0,0,0,.18);
    transform: translateX(102%); transition: transform .28s cubic-bezier(.4,0,.2,1);
    z-index: 9999; display: flex; flex-direction: column; }
  .risk-drawer.open { transform: translateX(0); }
  .risk-drawer-hd { display: flex; align-items: center; gap: 12px; padding: 15px 20px;
    border-bottom: 1px solid #eef0f3; flex: 0 0 auto; }
  .risk-drawer-hd .t { font-size: 16px; font-weight: 700; color: #1a3a5f; }
  .risk-drawer-hd .s { font-size: 12px; color: #8a94a6; margin-top: 2px; }
  .risk-drawer-hd .x { margin-left: auto; border: 0; background: #f2f4f7; color: #54637a;
    width: 30px; height: 30px; border-radius: 8px; font-size: 15px; cursor: pointer; line-height: 1; }
  .risk-drawer-hd .x:hover { background: #e6e9ef; }
  .risk-drawer-bd { padding: 12px 20px 24px; overflow: auto; flex: 1 1 auto; }
  .risk-drawer-bd .data-table { margin-top: 6px; font-size: 12px; }
  .risk-drawer-ft { padding: 10px 20px; border-top: 1px solid #eef0f3;
    font-size: 12px; color: #8a94a6; flex: 0 0 auto; }
"""

DOM = """
<!-- ============ 第 9 项：预警小区明细抽屉 ============ -->
<div class="risk-drawer-mask" id="riskDrawerMask" hidden></div>
<aside class="risk-drawer" id="riskDrawer" role="dialog" aria-modal="true"
       aria-labelledby="riskDrawerTitle" aria-hidden="true">
  <div class="risk-drawer-hd">
    <div>
      <div class="t" id="riskDrawerTitle">预警小区清单</div>
      <div class="s" id="riskDrawerSub"></div>
    </div>
    <button class="x" id="riskDrawerClose" type="button" aria-label="关闭">&#10005;</button>
  </div>
  <div class="risk-drawer-bd" id="riskDrawerBody"></div>
  <div class="risk-drawer-ft">口径：纳统小区 · 2026年1-8月 · 100 分起扣（分越低风险越高）</div>
</aside>
<script id="riskDrawerData" type="application/json">__DATA__</script>
<script>
(function () {
  var DATA = JSON.parse(document.getElementById('riskDrawerData').textContent);
  var COLOR = { '红色': '#f5222d', '橙色': '#fa8c16', '黄色': '#faad14', '蓝色': '#1890ff' };
  var drawer = document.getElementById('riskDrawer');
  var mask = document.getElementById('riskDrawerMask');
  var body = document.getElementById('riskDrawerBody');
  var titleEl = document.getElementById('riskDrawerTitle');
  var subEl = document.getElementById('riskDrawerSub');
  var closeBtn = document.getElementById('riskDrawerClose');
  var lastFocus = null;
  var hideTimer = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function pct(v) {
    if (v === null || v === undefined) return '—';
    return (v > 0 ? '+' : '') + Number(v).toFixed(1) + '%';
  }

  function render(level) {
    var arr = DATA[level] || [];
    var c = COLOR[level] || '#333';
    titleEl.textContent = level + '预警小区清单';
    subEl.textContent = '共 ' + arr.length + ' 个小区 · 按风险得分升序（分越低风险越高）';
    var h = '<table class="data-table"><thead><tr>'
      + '<th>#</th><th>小区名称</th><th>街道</th><th>风险<br>得分</th>'
      + '<th>投诉<br>总量</th><th>同比<br>增长率</th><th>重复<br>投诉率</th><th>主要问题</th>'
      + '</tr></thead><tbody>';
    for (var i = 0; i < arr.length; i++) {
      var d = arr[i];
      var g = d.g, gc = (g > 0 ? '#f5222d' : (g < 0 ? '#00a854' : '#8a94a6'));
      h += '<tr><td>' + (i + 1) + '</td>'
        + '<td style="text-align:left;font-weight:700;">' + esc(d.n) + '</td>'
        + '<td>' + esc(d.s) + '</td>'
        + '<td style="font-weight:700;color:' + c + ';">' + d.sc + '</td>'
        + '<td>' + d.t + '</td>'
        + '<td style="color:' + gc + ';font-weight:600;">' + pct(g) + '</td>'
        + '<td>' + (d.r == null ? '—' : Number(d.r).toFixed(1) + '%') + '</td>'
        + '<td>' + esc(d.c) + '</td></tr>';
    }
    h += '</tbody></table>';
    body.innerHTML = h;
    body.scrollTop = 0;
  }

  function open(level) {
    render(level);
    lastFocus = document.activeElement;
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    mask.hidden = false;
    drawer.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    void drawer.offsetWidth;          // 强制回流：保证 CSS 过渡从初始态开始（且状态同步生效）
    mask.classList.add('open');
    drawer.classList.add('open');
    closeBtn.focus();
  }

  function close() {
    mask.classList.remove('open');
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    hideTimer = setTimeout(function () { mask.hidden = true; }, 240);
    if (lastFocus && lastFocus.focus) { lastFocus.focus(); }
  }

  Array.prototype.forEach.call(document.querySelectorAll('.stat-card[data-level]'), function (card) {
    var lv = card.getAttribute('data-level');
    card.addEventListener('click', function () { open(lv); });
    card.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
        e.preventDefault(); open(lv);
      }
    });
  });
  closeBtn.addEventListener('click', close);
  mask.addEventListener('click', close);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && drawer.classList.contains('open')) { close(); }
  });
})();
</script>
"""


def build_payload(risk):
    """按等级分组的小区清单（精简字段名以压缩内嵌体积）。"""
    buckets = {lv: [] for lv in LEVELS}
    for c in risk["all_communities"]:
        lv = c.get("risk_level")
        if lv not in buckets:
            continue
        buckets[lv].append({
            "n": c.get("community"),
            "s": c.get("street"),
            "sc": c.get("total_score"),
            "t": c.get("total"),
            "g": c.get("growth_rate"),
            "r": c.get("repeat_rate"),
            "c": c.get("top_category"),
        })
    for lv in LEVELS:
        buckets[lv].sort(key=lambda x: (x["sc"] if x["sc"] is not None else 9e9))
    return buckets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    risk = json.load(open(RISK, encoding="utf-8"))
    payload = build_payload(risk)
    meta = {lv: len(v) for lv, v in payload.items()}
    print("按等级清单：" + "｜".join(f"{k} {v}" for k, v in meta.items()))
    assert meta["红色"] + meta["橙色"] + meta["黄色"] + meta["蓝色"] == len(risk["all_communities"]), \
        "等级分组合计与参评数不符"

    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    print(f"内嵌数据：{len(data_json):,} 字符")

    html = open(REPORT, encoding="utf-8").read()
    orig = len(html)
    done = []

    # ① 等级卡片可点击
    for lv in LEVELS:
        cls = LEVEL_CLASS[lv]
        pat = re.compile(r'<div class="stat-card %s"(?![^>]*data-level)' % cls)
        new, k = pat.subn(
            lambda m, l=lv, c=cls: (f'<div class="stat-card {c}" data-level="{l}" '
                                    f'role="button" tabindex="0" '
                                    f'title="点击查看{l}预警小区清单"'), html, count=1)
        if k:
            html = new
            done.append(f"card-{lv}")
        else:
            done.append(f"card-{lv}(已标记或未找到)")
        # 提示文案（幂等：新文案已存在则跳过，避免重复插入）
        lab = {"红色": "红色预警", "橙色": "橙色预警", "黄色": "黄色预警", "蓝色": "蓝色预警"}[lv]
        hint_old = f'<div class="label">{lab}</div>'
        hint_new = hint_old + '<div class="drill-hint">查看小区清单</div>'
        if hint_new not in html:
            html = html.replace(hint_old, hint_new, 1)

    # ② CSS 注入
    if ".risk-drawer" not in html:
        html = html.replace("</style>", CSS + "</style>", 1)
        done.append("css")
    else:
        # 已注入过：整体替换旧 CSS 块，保证样式可迭代更新
        html = re.sub(r"\n  /\* =+ 第 9 项：预警小区明细抽屉 =+ \*/[\s\S]*?(?=\n</style>)",
                      CSS.rstrip("\n"), html, count=1)
        done.append("css(刷新)")

    # ③ DOM + 数据 + JS 注入（整体替换，保证可迭代更新）
    block = DOM.replace("__DATA__", data_json)
    if 'id="riskDrawer"' in html:
        html = re.sub(r"\n<!-- =+ 第 9 项：预警小区明细抽屉 =+ -->[\s\S]*?(?=\n</body>)",
                      block.rstrip("\n"), html, count=1)
        done.append("dom(刷新)")
    else:
        html = html.replace("</body>", block + "</body>", 1)
        done.append("dom")

    print("完成：" + "、".join(done))
    print(f"{orig:,} → {len(html):,} 字符")

    if args.dry_run:
        print("[dry-run] 未写回 HTML")
    else:
        with open(REPORT, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✔ 已更新 {REPORT}")


if __name__ == "__main__":
    main()
