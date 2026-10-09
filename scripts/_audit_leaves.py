#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审计残留：跑真实转换链路，导出仍被当作「清单式文本叶子」的类名统计与祖先链。"""
import collections
import json
import os
import sys

ROOT = '/Users/macbookpro/Desktop/8-24 徐汇课题一期'
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
os.chdir(ROOT)
from html2docx import convert_report, load_figmap, new_document  # noqa

MANIFEST = json.load(open('assets/docx_figs/manifest.json', encoding='utf-8'))
RENDERED = os.path.join(ROOT, '_rendered')
REPORTS = [f[:-5] for f in sorted(os.listdir(RENDERED)) if f.endswith('.html')]

total = collections.Counter()
per = {}
samples = {}
for stem in REPORTS:
    fp = os.path.join(RENDERED, stem + '.html')
    doc = new_document()
    st = {}
    convert_report(doc, fp, load_figmap(MANIFEST, stem), base=1, fig_prefix='X', stats=st)
    lv = st.get('leaves', {})
    per[stem] = lv
    for k, v in lv.items():
        total[k] += v
    for k, d in st.get('leaf_samples', {}).items():
        for ch, (n, txt) in d.items():
            samples.setdefault(k, []).append((stem, txt, '%s   [x%d]' % (ch, n)))

verbose = '--v' in sys.argv
only = None
if '--only' in sys.argv:
    only = sys.argv[sys.argv.index('--only') + 1]

rows = [(k, v) for k, v in total.most_common() if (not only or only in k)]
print('%-34s %5s' % ('leaf-class', 'count'))
print('-' * 44)
for k, v in rows:
    print('%-34s %5d' % (k, v))
if verbose:
    for k, v in rows:
        print('\n### %s (%d)' % (k, v))
        for stem, txt, ch in samples.get(k, []):
            print('  [%s] %s' % (stem, ch))
            print('      %s' % txt)
print('\n合计 %d 类 / %d 处' % (len(total), sum(total.values())))
