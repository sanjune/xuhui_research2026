#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出报告 HTML 中的 ECharts 图表为高清 PNG，供 Word 成果汇编嵌入。

用法：
  PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/export_echarts_figs.py [--only 名称片段]
  PYTHONPATH=... /usr/bin/python3 scripts/export_echarts_figs.py --street

产物：
  assets/docx_figs/<报告名>/<序号>_<容器id>.png   （pixelRatio=2，白底）
  assets/docx_figs/manifest.json                  （报告 → 图表清单，供转换器按序插图）

实现：无头 Chrome + CDP（Runtime.evaluate 调 echarts.getDataURL）。
      街镇报告为 13 镇共用一套容器、点击标签页才渲染，故走 --street 模式逐镇切换导出。
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, 'assets', 'docx_figs')
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
PORT = 9334

REPORTS = [
    '12345投诉量下降数据报告.html',
    '治理效果追踪分析报告.html',
    '高风险小区预警清单.html',
    '徐汇区1-8月工单综合分析与目标测算.html',
    '数据质量优化专项报告.html',
    '重点问题专题分析报告（5份）.html',
]
STREET_REPORT = '街镇专项分析报告.html'

LIST_JS = r"""
(function(){
  var r=[];
  var all=document.querySelectorAll('div,section,article');
  for(var k=0;k<all.length;k++){
    try{ if(window.echarts && echarts.getInstanceByDom(all[k])) r.push(all[k].id||('idx'+k)); }catch(e){}
  }
  return JSON.stringify(r);
})()
"""

PNG_JS = r"""
(function(i){
  var ds=[];
  var all=document.querySelectorAll('div,section,article');
  for(var k=0;k<all.length;k++){
    try{ if(window.echarts && echarts.getInstanceByDom(all[k])) ds.push(all[k]); }catch(e){}
  }
  if(i>=ds.length) return JSON.stringify({ok:false});
  var d=ds[i], inst=echarts.getInstanceByDom(d);
  try{
    return JSON.stringify({ok:true, id:(d.id||('idx'+i)),
      url: inst.getDataURL({type:'png', pixelRatio:2, backgroundColor:'#ffffff'})});
  }catch(e){ return JSON.stringify({ok:false, err:String(e)}); }
})(%d)
"""

CLICK_JS = r"""
(function(n){
  var b=document.querySelector('.tab-btn[data-tab="'+n+'"]');
  if(!b) return JSON.stringify({ok:false});
  b.click();
  return JSON.stringify({ok:true, label:(b.textContent||'').trim()});
})(%d)
"""

PANEL_LIST_JS = r"""
(function(n){
  var p=document.getElementById('panel-'+n);
  if(!p) return JSON.stringify([]);
  var r=[];
  p.querySelectorAll('.chart-box[id]').forEach(function(el){
    r.push({id:el.id, has: !!(window.echarts && echarts.getInstanceByDom(el))});
  });
  return JSON.stringify(r);
})(%d)
"""

BYID_PNG_JS = r"""
(function(id){
  var el=document.getElementById(id);
  if(!el) return JSON.stringify({ok:false,err:'no-el'});
  if(!window.echarts) return JSON.stringify({ok:false,err:'no-echarts'});
  var inst=echarts.getInstanceByDom(el);
  if(!inst) return JSON.stringify({ok:false,err:'no-inst'});
  try{ return JSON.stringify({ok:true,id:id,
    url:inst.getDataURL({type:'png',pixelRatio:2,backgroundColor:'#ffffff'})}); }
  catch(e){ return JSON.stringify({ok:false,err:String(e)}); }
})('%s')
"""


def start_chrome(prof):
    p = subprocess.Popen(
        [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox', '--disable-extensions',
         '--disable-background-networking', '--disable-sync', '--no-first-run',
         '--hide-scrollbars', '--remote-allow-origins=*', '--window-size=1440,1200',
         '--remote-debugging-port=%d' % PORT, '--user-data-dir=%s' % prof, 'about:blank'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(160):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=1).read()
            return p
        except Exception:
            time.sleep(0.5)
    p.kill()
    raise RuntimeError('chrome 未就绪')


def new_tab(url):
    t = 'http://127.0.0.1:%d/json/new?%s' % (PORT, urllib.parse.quote(url, safe=''))
    try:
        return json.loads(urllib.request.urlopen(urllib.request.Request(t, method='PUT'), timeout=10).read())
    except Exception:
        return json.loads(urllib.request.urlopen(urllib.request.Request(t), timeout=10).read())


def close_tab(tid):
    try:
        urllib.request.urlopen('http://127.0.0.1:%d/json/close/%s' % (PORT, tid), timeout=5).read()
    except Exception:
        pass


def evaluate(ws, expr, mid):
    ws.send(json.dumps({'id': mid, 'method': 'Runtime.evaluate',
                        'params': {'expression': expr, 'returnByValue': True, 'awaitPromise': True}}))
    for _ in range(6000):
        msg = json.loads(ws.recv())
        if msg.get('id') == mid:
            return msg
    return None


def jval(msg, default=None):
    try:
        return json.loads(msg['result']['result']['value'])
    except Exception:
        return default


def wait_ready(ws, tries=30):
    """等待 echarts 加载且至少一个 canvas 渲染完成。"""
    for i in range(tries):
        v = jval(evaluate(ws, "JSON.stringify({e:(typeof window.echarts!=='undefined'),"
                             "n:(window.echarts?document.querySelectorAll('canvas').length:-1)})", 900 + i), {})
        if v.get('e') and v.get('n', 0) > 0:
            time.sleep(2.0)
            return v['n']
        time.sleep(1.0)
    return 0


def save_png(outdir, index, cid, label, val):
    if not val or not val.get('ok'):
        print('    [x] %s 失败 %s' % (cid, (val or {}).get('err', '')))
        return None
    raw = base64.b64decode(val['url'].split(',', 1)[1])
    safe = ''.join(c if (c.isalnum() or c in '-_') else '_' for c in cid)
    name = '%02d_%s%s.png' % (index, (label + '__') if label else '', safe)
    fp = os.path.join(outdir, name)
    with open(fp, 'wb') as f:
        f.write(raw)
    print('    [v] %-22s %6.1f KB  %s' % (cid, len(raw) / 1024.0, name))
    return {'order': index, 'id': cid, 'label': label, 'file': os.path.relpath(fp, ROOT), 'bytes': len(raw)}


def export_simple(ws, stem):
    outdir = os.path.join(OUTDIR, stem)
    os.makedirs(outdir, exist_ok=True)
    ids = jval(evaluate(ws, LIST_JS, 800), [])
    out = []
    for i, cid in enumerate(ids):
        val = jval(evaluate(ws, PNG_JS % i, 1000 + i))
        r = save_png(outdir, i, cid, '', val)
        if r:
            out.append(r)
    return out


def export_streets(ws):
    stem = os.path.splitext(STREET_REPORT)[0]
    outdir = os.path.join(OUTDIR, stem)
    os.makedirs(outdir, exist_ok=True)
    out = []

    # 全区级图表（切到第 0 个街镇面板前先取）
    ids = jval(evaluate(ws, LIST_JS, 700), [])
    for cid in ids:
        if cid.startswith('ov-'):
            val = jval(evaluate(ws, BYID_PNG_JS % cid, 710))
            r = save_png(outdir, 900, cid, '全区', val)
            if r:
                r['scope'] = 'overview'
                out.append(r)

    for n in range(13):
        clk = jval(evaluate(ws, CLICK_JS % n, 2000 + n), {})
        label = (clk or {}).get('label', '') or ('镇%d' % n)
        time.sleep(2.5)
        figs = jval(evaluate(ws, PANEL_LIST_JS % n, 2100 + n), [])
        got = 0
        for f in figs:
            if f['id'].endswith('wordcloud'):
                continue  # 词云用已有高清 PNG，避免重复
            val = jval(evaluate(ws, BYID_PNG_JS % f['id'], 2200 + n * 10 + got))
            r = save_png(outdir, n, f['id'], label, val)
            if r:
                r['scope'] = 'street'
                r['street'] = label
                out.append(r)
                got += 1
        print('  [%2d] %s → %d 张' % (n, label, got))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--street', action='store_true', help='导出街镇报告 13 镇图表')
    args = ap.parse_args()

    mpath = os.path.join(OUTDIR, 'manifest.json')
    manifest = {}
    if os.path.exists(mpath):
        with open(mpath, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

    os.makedirs(OUTDIR, exist_ok=True)
    from websocket import create_connection

    if args.street:
        url = 'file://' + urllib.parse.quote(os.path.join(ROOT, STREET_REPORT), safe='/')
        prof = '/tmp/cr_st_%d' % int(time.time() * 1000)
        proc = start_chrome(prof)
        print('Chrome 启动 profile=%s' % prof)
        try:
            tab = new_tab(url)
            ws = create_connection(tab['webSocketDebuggerUrl'], timeout=180)
            n = wait_ready(ws)
            print('== %s (canvas=%d)' % (STREET_REPORT, n))
            figs = export_streets(ws)
            manifest[os.path.splitext(STREET_REPORT)[0]] = figs
            print('    共 %d 张' % len(figs))
            ws.close(); close_tab(tab['id'])
        finally:
            proc.kill()
            with open(mpath, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=1)
            print('manifest → %s' % mpath)
        return 0

    targets = [f for f in REPORTS if (not args.only or args.only in f)]
    prof = '/tmp/cr_fig_%d' % int(time.time() * 1000)
    proc = start_chrome(prof)
    print('Chrome 启动 profile=%s' % prof)
    try:
        for fname in targets:
            stem = os.path.splitext(fname)[0]
            url = 'file://' + urllib.parse.quote(os.path.join(ROOT, fname), safe='/')
            tab = new_tab(url)
            ws = create_connection(tab['webSocketDebuggerUrl'], timeout=120)
            n = wait_ready(ws)
            print('== %s (canvas=%d)' % (fname, n))
            if n > 0:
                figs = export_simple(ws, stem)
                manifest[stem] = figs
                print('    共 %d 张' % len(figs))
            else:
                print('    跳过：无已渲染图表')
            ws.close(); close_tab(tab['id'])
    finally:
        proc.kill()
        with open(mpath, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        print('manifest → %s' % mpath)
    return 0


if __name__ == '__main__':
    sys.exit(main())
