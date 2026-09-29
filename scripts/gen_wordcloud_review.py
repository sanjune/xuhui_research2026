#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《词云词表审核清单.html》—— 供人工勾选删除中性词。

读 scripts/wordcloud_terms.json（dump_wordcloud_terms.py 产出），渲染两种视图：
  · 全部词（去重）：190 个候选词按「覆盖街镇数 / 合计词频」排序，点击即标记删除
  · 按街镇：每镇 Top24（当前展示）+ 第 25-60 名（补位候选）

勾选结果支持一键复制为逗号分隔文本，回填到 build_street_dataset.py 的
STOP / STOP_BOILERPLATE 后重跑即可（删词后 Top24 会由候补词自动补位）。

用法：/usr/bin/python3 scripts/gen_wordcloud_review.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "scripts", "wordcloud_terms.json")
OUT = os.path.join(ROOT, "词云词表审核清单.html")

# 疑似「中性 / 泛指 / 流程」词 —— 仅为肉眼提示，非结论，最终以人工判断为准
SUGGEST = [
    "有关", "事宜", "现象", "说法", "提供", "针对", "立即", "彻底",
    "原样", "时间", "家中", "楼上", "位置", "合规", "成立", "规定",
    "住户", "解决方案", "上门", "恢复", "更换", "安装", "拆除", "责令",
    "疏通", "清扫", "修剪", "监控", "包月", "城管", "开发商", "筹备",
]

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>词云词表审核清单 · 徐汇物业课题一期</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; background:#f5f7fa; color:#1f2937;
         font-family:-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif; }
  .hd { background:linear-gradient(135deg,#0d47a1,#1976d2); color:#fff; padding:26px 32px 22px; }
  .hd h1 { margin:0 0 6px; font-size:23px; letter-spacing:.4px; }
  .hd .sub { font-size:13px; opacity:.92; }
  .hd .meta { font-size:12px; opacity:.78; margin-top:8px; }
  .wrap { max-width:1420px; margin:0 auto; padding:0 22px 130px; }
  .tip { margin:18px 0 0; padding:12px 18px; background:#fff8e1; border-left:4px solid #f9a825;
         border-radius:6px; font-size:13px; color:#7a5b00; line-height:1.85; }
  .tip b { color:#5d4400; }
  .bar2 { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin:16px 0 4px; }
  .tabs { display:flex; gap:8px; }
  .tabs button { border:1px solid #d3dce6; background:#fff; color:#334155; padding:7px 16px;
                 border-radius:20px; font-size:13px; cursor:pointer; }
  .tabs button.on { background:#1976d2; border-color:#1976d2; color:#fff; font-weight:600; }
  .tools { margin-left:auto; display:flex; gap:10px; align-items:center; }
  .tools input[type=search] { border:1px solid #d3dce6; border-radius:18px; padding:7px 14px;
                              font-size:13px; width:190px; outline:none; }
  .tools input[type=search]:focus { border-color:#1976d2; }
  .legend { display:flex; flex-wrap:wrap; gap:16px; font-size:12px; color:#64748b; margin:14px 0 12px; }
  .legend i { display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:5px;
              vertical-align:-1px; }
  .sec-title { font-size:15px; font-weight:700; color:#0d47a1; margin:22px 0 12px;
               padding-left:10px; border-left:4px solid #1976d2; }
  .wgrid { display:flex; flex-wrap:wrap; gap:9px; }
  .w { display:inline-flex; flex-direction:column; gap:2px; padding:7px 13px; border-radius:9px;
       border:1px solid #e3e8ef; background:#fafbfc; cursor:pointer; user-select:none;
       transition:all .13s; min-width:96px; }
  .w:hover { border-color:#1976d2; box-shadow:0 2px 8px rgba(25,118,210,.14); }
  .w .wd { font-size:15px; font-weight:600; color:#334155; line-height:1.25; }
  .w .wm { font-size:10.5px; color:#94a3b8; line-height:1.3; white-space:nowrap; }
  .w.show { background:#eaf3ff; border-color:#1976d2; }
  .w.show .wd { color:#0d47a1; }
  .w.show .wm { color:#5b8fd6; }
  .w.sug { border-style:dashed; border-color:#f9a825; background:#fffdf5; }
  .w.del { background:#ffecec; border-color:#f5222d; border-style:solid; }
  .w.del .wd { color:#f5222d; text-decoration:line-through; }
  .w.del .wm { color:#e08a8a; }
  .cards { display:grid; grid-template-columns:repeat(2,1fr); gap:16px; }
  @media (max-width:1080px) { .cards { grid-template-columns:1fr; } }
  .card { background:#fff; border-radius:12px; box-shadow:0 2px 12px rgba(0,0,0,.06); overflow:hidden; }
  .card-head { display:flex; align-items:baseline; gap:10px; padding:12px 16px;
               border-bottom:1px solid #eef1f5; background:#f8fafc; }
  .card-head .nm { font-size:15px; font-weight:700; color:#0d47a1; }
  .card-head .tag { font-size:11px; color:#78909c; background:#eef2f7; padding:2px 9px;
                    border-radius:10px; }
  .card-body { padding:12px 16px 14px; }
  .card-body .lbl { font-size:12px; color:#64748b; margin:2px 0 8px; font-weight:600; }
  .card-body .lbl.pad { margin-top:16px; }
  .cand { margin-top:16px; border-top:1px dashed #e3e8ef; padding-top:12px; }
  .cand summary { font-size:12px; color:#64748b; cursor:pointer; font-weight:600; outline:none; }
  .cand .wgrid { margin-top:10px; }
  .hide { display:none; }
  .footer { text-align:center; font-size:12px; color:#90a4ae; padding:26px 20px 20px; }
  .bar { position:fixed; left:0; right:0; bottom:0; background:#fff; border-top:1px solid #e3e8ef;
         box-shadow:0 -3px 14px rgba(0,0,0,.07); padding:11px 22px; display:flex;
         align-items:center; gap:14px; flex-wrap:wrap; z-index:20; }
  .bar .st { font-size:13px; color:#334155; }
  .bar .st b { color:#f5222d; font-size:16px; }
  .bar input { flex:1; min-width:200px; border:1px solid #d3dce6; border-radius:8px;
               padding:8px 12px; font-size:13px; font-family:ui-monospace,Menlo,monospace;
               color:#334155; background:#f8fafc; outline:none; }
  .bar button { border:none; border-radius:8px; padding:8px 16px; font-size:13px; cursor:pointer; }
  .bar button.pri { background:#1976d2; color:#fff; font-weight:600; }
  .bar button.pri:hover { background:#0d47a1; }
  .bar button.gh { background:#eef2f7; color:#475569; }
  .bar button.gh:hover { background:#e2e8f0; }
</style>
</head>
<body>
<div class="hd">
  <h1>词云词表审核清单（人工删除中性词）</h1>
  <div class="sub">13 个街镇 · 190 个候选词 · 当前展示 Top24 ／ 第 25 名以后为补位候选</div>
  <div class="meta">口径：2026年1-8月 ｜ 案件级归并（同一诉求的催单/重复来电只计首单）｜ 已剥离工单引用块 ｜ 数据源 scripts/wordcloud_terms.json</div>
</div>

<div class="wrap">
  <div class="tip">
    <b>怎么用：</b>点击任意词即标记为「待删除」（再点一次取消）。标记完成后，把底部输入框里的清单复制发我，
    我会写入停用词表并重跑生成脚本 —— <b>删除后 Top24 会由「补位候选」自动顶上</b>，所以黄框里的候选词也值得一并看一眼。<br>
    <b>提示：</b>虚线黄框标出的是系统认为「疑似中性/泛指/流程词」的 32 个词（如「有关/事宜/现象/说法」），
    仅供快速定位，<b>不是结论</b>，是否删除完全由你判断。
  </div>

  <div class="bar2">
    <div class="tabs">
      <button id="tabAll" class="on">全部词（去重）</button>
      <button id="tabStreet">按街镇查看</button>
    </div>
    <div class="tools">
      <input type="search" id="q" placeholder="搜索词…">
      <label style="font-size:13px;color:#475569;display:flex;align-items:center;gap:5px;cursor:pointer">
        <input type="checkbox" id="onlyShow"> 只看当前展示词
      </label>
    </div>
  </div>

  <div id="paneAll">
    <div class="legend">
      <span><i style="background:#eaf3ff;border:1px solid #1976d2"></i>当前展示中（任一街镇 Top24）</span>
      <span><i style="background:#fafbfc;border:1px solid #e3e8ef"></i>补位候选（第 25 名以后）</span>
      <span><i style="background:#fffdf5;border:1px dashed #f9a825"></i>疑似中性词（提示）</span>
      <span><i style="background:#ffecec;border:1px solid #f5222d"></i>已标记待删除</span>
    </div>
    <div class="sec-title" id="allTitle">全部候选词</div>
    <div class="wgrid" id="gridAll"></div>
  </div>

  <div id="paneStreet" class="hide">
    <div class="sec-title">按街镇查看（Top24 展示 + 补位候选）</div>
    <div class="cards" id="gridStreet"></div>
  </div>
</div>

<div class="bar">
  <span class="st">已标记待删除 <b id="nDel">0</b> 个词</span>
  <input id="outText" readonly placeholder="（点击上方词条后，这里会生成可复制的删除清单）">
  <button class="pri" id="btnCopy">复制删除清单</button>
  <button class="gh" id="btnReset">清空标记</button>
</div>

<div class="footer">徐汇区物业课题一期 · 词云词表审核清单 · 生成脚本 scripts/gen_wordcloud_review.py</div>

<script>
var DATA = __DATA__;
var SUGGEST = __SUGGEST__;
var SHOWN = DATA.meta.topn_shown;
var DEL = {};

/* ── 词条索引：word → {streets:[{name,rank,cnt}], total, cover, shown} ── */
var INDEX = {}, ORDER = [];
(function () {
  var m = {};
  for (var st in DATA.streets) {
    DATA.streets[st].forEach(function (it) {
      if (!m[it.word]) m[it.word] = { word: it.word, streets: [], total: 0, shown: false };
      m[it.word].streets.push({ name: st, rank: it.rank, cnt: it.cnt });
      m[it.word].total += it.cnt;
      if (it.rank <= SHOWN) m[it.word].shown = true;
    });
  }
  ORDER = Object.keys(m).sort(function (a, b) {
    var A = m[a], B = m[b];
    if (A.shown !== B.shown) return A.shown ? -1 : 1;      // 展示中的排前
    if (A.streets.length !== B.streets.length) return B.streets.length - A.streets.length;
    return B.total - A.total;
  });
  INDEX = m;
})();
var SUG = {}; SUGGEST.forEach(function (w) { SUG[w] = 1; });

function pct(n) { return n.toLocaleString('en-US'); }

function chip(word) {
  var it = INDEX[word];
  var cls = 'w' + (it.shown ? ' show' : '') + (SUG[word] ? ' sug' : '') + (DEL[word] ? ' del' : '');
  var dist = it.streets.sort(function (a, b) { return a.rank - b.rank; })
    .map(function (s) { return s.name + ' #' + s.rank + '（' + s.cnt + '）'; }).join('；');
  return '<div class="' + cls + '" data-w="' + word + '" title="' + dist + '">'
    + '<span class="wd">' + word + '</span>'
    + '<span class="wm">' + it.streets.length + ' 镇 · ' + pct(it.total) + ' 次 · '
    + (it.shown ? '展示中' : '候补') + '</span></div>';
}

/* ── 全部词视图 ── */
function renderAll() {
  var q = (document.getElementById('q').value || '').trim();
  var onlyShow = document.getElementById('onlyShow').checked;
  var html = '';
  ORDER.forEach(function (w) {
    if (q && w.indexOf(q) < 0) return;
    if (onlyShow && !INDEX[w].shown) return;
    html += chip(w);
  });
  document.getElementById('gridAll').innerHTML = html || '<p style="color:#94a3b8;font-size:13px">没有匹配的词</p>';
}

/* ── 按街镇视图 ── */
function renderStreet() {
  var colors = ['#1a3a5f', '#1890ff', '#13c2c2', '#52c41a', '#fa8c16', '#f5222d', '#7b1fa2', '#0f6e56'];
  var html = '';
  Object.keys(DATA.streets).forEach(function (st) {
    var items = DATA.streets[st];
    var top = items.filter(function (x) { return x.rank <= SHOWN; });
    var cand = items.filter(function (x) { return x.rank > SHOWN; });
    html += '<div class="card"><div class="card-head"><span class="nm">' + st + '</span>'
      + '<span class="tag">展示 Top' + top.length + ' · 候选 ' + cand.length + ' 词</span></div>'
      + '<div class="card-body"><div class="lbl">当前词云展示</div>'
      + '<div class="wgrid">' + top.map(function (x) { return chip(x.word); }).join('') + '</div>';
    if (cand.length) {
      html += '<details class="cand"><summary>补位候选（第 ' + (SHOWN + 1) + '–' + items.length
        + ' 名，删词后自动顶上）</summary><div class="wgrid">'
        + cand.map(function (x) { return chip(x.word); }).join('') + '</div></details>';
    }
    html += '</div></div>';
  });
  document.getElementById('gridStreet').innerHTML = html;
}

/* ── 交互 ── */
function refresh() {
  var n = 0, list = [];
  ORDER.forEach(function (w) { if (DEL[w]) { n++; list.push(w); } });
  document.getElementById('nDel').textContent = n;
  document.getElementById('outText').value = list.join('、');
  document.querySelectorAll('.w').forEach(function (el) {
    var w = el.getAttribute('data-w');
    el.classList.toggle('del', !!DEL[w]);
  });
}

document.addEventListener('click', function (e) {
  var el = e.target.closest && e.target.closest('.w');
  if (!el) return;
  var w = el.getAttribute('data-w');
  if (DEL[w]) delete DEL[w]; else DEL[w] = 1;
  refresh();
});

document.getElementById('q').addEventListener('input', renderAll);
document.getElementById('onlyShow').addEventListener('change', renderAll);
document.getElementById('tabAll').addEventListener('click', function () {
  this.classList.add('on'); document.getElementById('tabStreet').classList.remove('on');
  document.getElementById('paneAll').classList.remove('hide');
  document.getElementById('paneStreet').classList.add('hide');
});
document.getElementById('tabStreet').addEventListener('click', function () {
  this.classList.add('on'); document.getElementById('tabAll').classList.remove('on');
  document.getElementById('paneStreet').classList.remove('hide');
  document.getElementById('paneAll').classList.add('hide');
  renderStreet();
});
document.getElementById('btnCopy').addEventListener('click', function () {
  var v = document.getElementById('outText').value;
  if (!v) { alert('还没有标记任何词'); return; }
  var ta = document.createElement('textarea');
  ta.value = v; document.body.appendChild(ta); ta.select();
  document.execCommand('copy'); document.body.removeChild(ta);
  this.textContent = '已复制 ✓';
  var self = this;
  setTimeout(function () { self.textContent = '复制删除清单'; }, 1600);
});
document.getElementById('btnReset').addEventListener('click', function () {
  DEL = {}; refresh();
});

renderAll();
</script>
</body>
</html>
"""


def main():
    d = json.load(open(SRC, encoding="utf-8"))
    html = (TEMPLATE
            .replace("__DATA__", json.dumps(d, ensure_ascii=False))
            .replace("__SUGGEST__", json.dumps(SUGGEST, ensure_ascii=False)))
    open(OUT, "w", encoding="utf-8").write(html)
    m = d["meta"]
    print(f"街镇 {m['streets']} 个 | 唯一候选词 {m['unique_words']} 个 | 显示 Top{m['topn_shown']}")
    print(f"→ {os.path.basename(OUT)}  {os.path.getsize(OUT) // 1024} KB")


if __name__ == "__main__":
    main()
