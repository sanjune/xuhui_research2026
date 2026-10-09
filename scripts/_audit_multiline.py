#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清单压平审计：找出 Word 里「本该分行、却被挤成一段」的段落。

判定：同一段内出现 ≥2 个列表标记 ——
  · 圈码 ① ② ③ …
  · 阿拉伯序号「1. 」「2. 」
  · 中文序号「（一）」「一、」
正常行文不应在一段里连挂多个编号项。命中即视为「视觉行被压平」。

用法：PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/_audit_multiline.py [docx路径]
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DOCX = os.path.join(
    ROOT, '交付物',
    '徐汇区数据赋能下的住宅小区治理与物业服务质量提升探索项目课题成果汇编.docx')

CIRCLED = r'[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]'
CIRCLED_ORDER = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮'
# 序号后必须不接数字，避免把「17.0%」「26.2%–29.4%」这类小数误判成列表项
NUM_ITEM = r'(?:^|(?<=[\s；;。：]))(\d{1,2})[.、](?!\d)'
CN_ITEM = r'[（(][一二三四五六七八九十]{1,3}[)）]'

# 允许的例外：正文里正常引用序号（如「①②」指代两项指标）不视为压平
MIN_HITS = 2
MIN_HITS_DUN = 3


def _is_seq(nums):
    """序号必须是 1,2,3… 连续递增，才算「列表被压平」。

    否则会误伤「公租房 4、动迁房 1、军产 1 共 6 个小区」这类正常行文。
    """
    return len(nums) >= MIN_HITS and nums == list(range(1, len(nums) + 1))


def _marks(text):
    """返回该段命中的列表标记数与标记类型（序号须连续递增才算）。"""
    types = []
    circ = sorted(CIRCLED_ORDER.index(m) for m in re.findall(CIRCLED, text))
    if len(circ) >= MIN_HITS and circ == list(range(len(circ))):
        types.append('圈码×%d' % len(circ))
    nums = [int(m) for m in re.findall(NUM_ITEM, text)]
    if _is_seq(nums):
        types.append('数字序号×%d' % len(nums))
    cn = re.findall(CN_ITEM, text)
    if len(cn) >= MIN_HITS:
        types.append('括号中文×%d' % len(cn))
    return types


def iter_paras(doc):
    for i, p in enumerate(doc.paragraphs):
        yield ('正文段 %d' % i, p.text)
    for ti, t in enumerate(doc.tables):
        for ri, r in enumerate(t.rows):
            for ci, c in enumerate(r.cells):
                for pi, p in enumerate(c.paragraphs):
                    yield ('表%d r%d c%d p%d' % (ti, ri, ci, pi), p.text)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DOCX
    if not os.path.isfile(path):
        print('✗ 找不到文件：%s' % path)
        return 1
    from docx import Document
    doc = Document(path)

    hits = []
    for loc, text in iter_paras(doc):
        t = (text or '').strip()
        if len(t) < 30:
            continue
        types = _marks(t)
        if types:
            hits.append((loc, t, types))

    print('=' * 72)
    print('清单压平审计 —— %s' % os.path.basename(path))
    print('=' * 72)
    if not hits:
        print('✅ 未发现「多列表项挤成一段」的残留')
        return 0
    print('⚠️  命中 %d 处：\n' % len(hits))
    for loc, t, types in hits:
        print('  [%s] %s' % (loc, ' / '.join(types)))
        print('      %s' % (t[:150] + ('…' if len(t) > 150 else '')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
