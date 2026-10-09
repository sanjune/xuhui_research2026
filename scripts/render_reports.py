#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把报告 HTML 渲染成「完整 DOM」静态快照。

背景：部分报告的表格数据由页面 JS 在运行时填充（tbody 源码为空），
例如 12345 报告的十四类问题表、1-8 月综合测算的街镇排名/目标档位表。
直接用源码转换会丢掉这些行。本脚本用无头 Chrome 加载并 --dump-dom，
把渲染后的 DOM 落盘到 _rendered/，供 html2docx 转换。

用法：
  PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/render_reports.py
  ... scripts/render_reports.py --only 12345投诉量下降数据报告
  ... scripts/render_reports.py --check        # 只体检不重渲染
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, '_rendered')

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

# 需要渲染的报告（汇编实际收录的 13 份）
REPORTS = [
    '课题成果总览',
    '多源数据清洗与关联分析报告',
    '数据质量优化专项报告',
    '投诉去重识别方法论说明',
    '12345投诉量下降数据报告',
    '街镇专项分析报告',
    '徐汇区1-8月工单综合分析与目标测算',
    '高风险小区预警清单',
    '物业投诉根因分析报告',
    '治理效果追踪分析报告',
    '底部抬升小区热线数据分析报告',
    '重点问题专题分析报告（5份）',
    '数据分析月报合集',
]

# 必须渲染出数据行的表（源码 tbody 为空）
EXPECT_ROWS = {
    '12345投诉量下降数据报告': [('category-tbody', 14)],
}


def render(stem, budget=20000, tries=2):
    src = os.path.join(ROOT, stem + '.html')
    if not os.path.exists(src):
        return None, '源文件不存在'
    out = os.path.join(OUTDIR, stem + '.html')
    last = ''
    for k in range(tries):
        prof = tempfile.mkdtemp(prefix='cr_render_')      # 每次全新 profile，避免复用挂死
        cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
               '--disable-extensions', '--disable-background-networking',
               '--no-first-run', '--no-default-browser-check', '--hide-scrollbars',
               '--user-data-dir=' + prof,
               '--virtual-time-budget=%d' % budget,
               '--run-all-compositor-stages-before-draw',
               '--dump-dom', 'file://' + src]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=180)
            dom = r.stdout.decode('utf-8', 'ignore')
            if len(dom) > 2000 and '<html' in dom.lower():
                with open(out, 'w', encoding='utf-8') as f:
                    f.write(dom)
                shutil.rmtree(prof, ignore_errors=True)
                return out, None
            last = 'rc=%s 输出 %d 字节' % (r.returncode, len(dom))
        except subprocess.TimeoutExpired:
            last = '超时'
        finally:
            shutil.rmtree(prof, ignore_errors=True)
        time.sleep(1)
    return None, last


def check(stem):
    """渲染后体检：空 tbody 是否已填、表格数、图表容器数。"""
    from bs4 import BeautifulSoup
    problems = []
    for name in ['rendered', 'src']:
        fp = os.path.join(OUTDIR, stem + '.html') if name == 'rendered' \
            else os.path.join(ROOT, stem + '.html')
        if not os.path.exists(fp):
            continue
        s = BeautifulSoup(open(fp, encoding='utf-8').read(), 'lxml')
        empties = []
        for t in s.find_all('table'):
            tb = t.find('tbody')
            if tb is not None and len(tb.find_all('tr')) == 0 and tb.get('id'):
                empties.append(tb.get('id'))
        problems.append((name, len(s.find_all('table')), empties))
    return problems


def verify(stem):
    """断言 EXPECT_ROWS 中的表已渲染出足够行。"""
    if stem not in EXPECT_ROWS:
        return True, ''
    from bs4 import BeautifulSoup
    fp = os.path.join(OUTDIR, stem + '.html')
    if not os.path.exists(fp):
        return False, '未渲染'
    s = BeautifulSoup(open(fp, encoding='utf-8').read(), 'lxml')
    msg = []
    ok = True
    for tid, least in EXPECT_ROWS[stem]:
        el = s.find('tbody', id=tid)
        n = len(el.find_all('tr')) if el is not None else 0
        msg.append('%s=%d行(≥%d)' % (tid, n, least))
        if n < least:
            ok = False
    return ok, ' '.join(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None, help='只处理指定报告（名，不含 .html）')
    ap.add_argument('--check', action='store_true', help='只体检不渲染')
    ap.add_argument('--budget', type=int, default=20000)
    args = ap.parse_args()

    if not os.path.exists(CHROME):
        print('✗ 找不到 Chrome：%s' % CHROME)
        return 2
    os.makedirs(OUTDIR, exist_ok=True)

    stems = [s for s in REPORTS if args.only is None or args.only in s]
    if not stems:
        print('✗ 没有匹配的报告')
        return 2

    if args.check:
        for st in stems:
            for name, ntbl, empties in check(st):
                print('  %-34s %-9s 表=%d 空tbody=%s' % (st, name, ntbl, empties or '无'))
            ok, m = verify(st)
            if m:
                print('      → %s %s' % ('✓' if ok else '✗', m))
        return 0

    bad = 0
    for st in stems:
        t0 = time.time()
        fp, err = render(st, budget=args.budget)
        if err:
            print('  ✗ %-34s %s' % (st, err))
            bad += 1
            continue
        ok, m = verify(st)
        print('  %s %-34s %6.1fs %7.1f KB  %s'
              % ('✓' if ok else '✗', st, time.time() - t0,
                 os.path.getsize(fp) / 1024, m))
        if not ok:
            bad += 1
    print('\n完成：%d 份，失败 %d 份 → %s' % (len(stems), bad, OUTDIR))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
