#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""13 个街镇专项分析 → 每镇一份独立 Word（项目根目录独立文件夹）。

拆分依据：《街镇专项分析报告》中 13 个街镇面板（panel-0 ~ panel-12）。
每份 Word 内容 = 该镇完整画像 + 附《全区位次参照》（该镇在全区总量/密度两表中的
对应行 + 全区对比图 + 贡献度图），保证单独拿出来也是一份自洽的街镇报告。

数据/资源来源：
    街镇专项分析报告.html                页面结构（优先 _rendered/ 渲染版）
    assets/docx_figs/街镇专项分析报告/   各镇 5 张图表 PNG（trend/yoy/quarter/catdelta/catdonut）
    词云图/<镇>.png                      各镇诉求主题词云

产出：
    街镇专项分析报告（13镇分册）/<镇>街道12345物业投诉专项分析报告.docx

用法：
    PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/gen_street_docx.py
    ... scripts/gen_street_docx.py --only 长桥        # 只生成一个镇，便于调试
"""
import argparse
import json
import os
import sys

from bs4 import BeautifulSoup

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPTS)
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2docx import convert_report, new_document  # noqa: E402

STEM = '街镇专项分析报告'
SRC_RENDERED = os.path.join(ROOT, '_rendered', STEM + '.html')
SRC = os.path.join(ROOT, STEM + '.html')
OUTDIR = os.path.join(ROOT, '街镇专项分析报告（13镇分册）')
BUILD = os.path.join(ROOT, '_build', 'street_docx')
MANIFEST = os.path.join(ROOT, 'assets', 'docx_figs', 'manifest.json')

# 附录要附的全区级图（容器 id）
APPENDIX_FIGS = ['ov-compare', 'ov-contribution']

# 图片说明（写进容器 data-title，转换器据此在 Word 里生成居中图注）
FIG_TITLE = {
    '-trend': '月度投诉量趋势（2024—2026年）',
    '-yoy': '月度投诉量与同比变化',
    '-quarter': '同期季度对比',
    '-catdelta': '十四类问题同比增减',
    '-catdonut': '投诉类别结构',
    '-wordcloud': '诉求主题词云（案件级去重，Top24）',
    'ov-compare': '全区 13 个街镇投诉量与同比对比',
    'ov-contribution': '13 个街镇对全区投诉量下降的贡献度排行',
}

# 页码内的锚点修正：原页「（见第四节）」在本分册中对应附录
NOTE_FIX = [('（见第四节）', '（见附录）')]


def doc_name(street: str) -> str:
    """华泾镇 保留「镇」，其余补「街道」（与《年度分析报告/街道》命名一致）。"""
    return street if street.endswith('镇') else street + '街道'


def load_source():
    fp = SRC_RENDERED if os.path.exists(SRC_RENDERED) else SRC
    if not os.path.exists(fp):
        raise SystemExit('找不到源报告：%s' % STEM)
    return fp, BeautifulSoup(open(fp, encoding='utf-8').read(), 'lxml')


def build_rank_blocks(soup):
    """从全区总表两张表里，抽出「表头行 + 该镇行」，供各分册附录使用。

    返回 {(表id, 街镇名): (表头 tr 的 html, 该镇行 tr 的 html, 列数)}
    """
    out = {}
    for tid, title in (('rank-total', '全区 13 个街镇投诉总量排名（该镇所在行）'),
                       ('rank-density', '全区 13 个街镇投诉密度排名（该镇所在行）')):
        tbl = soup.select_one('#%s table' % tid)
        if tbl is None:
            continue
        trs = tbl.find_all('tr', recursive=False) or tbl.find_all('tr')
        if not trs:
            continue
        head = trs[0]
        ncol = len(head.find_all(['th', 'td']))
        for tr in trs[1:]:
            cells = tr.find_all(['th', 'td'])
            if len(cells) < 2:
                continue
            name = cells[1].get_text(strip=True)
            out[(tid, name)] = (head, tr, ncol, title)
    return out


def fig_title(cid: str) -> str:
    """容器 id → 图片说明。"""
    for suf, txt in FIG_TITLE.items():
        if suf.startswith('ov-'):
            if cid == suf:
                return txt
        elif cid.endswith(suf):
            return txt
    return ''


def style_panel(panel):
    """面板内的小节标题（.sub-title）提升为三级标题；图表容器补 data-title 作图注。"""
    for el in panel.find_all('div', class_='sub-title'):
        h = soup_new_tag('h3')
        h.string = el.get_text(' ', strip=True)
        el.replace_with(h)
    for el in panel.find_all('div'):
        cid = el.get('id') or ''
        if cid and 'chart-box' in (el.get('class') or []):
            t = fig_title(cid)
            if t:
                el['data-title'] = t
    return panel


def soup_new_tag(name):
    return BeautifulSoup('', 'lxml').new_tag(name)


def panel_html(panel_soup, rank_map, street):
    """把街镇面板 + 附录拼成一份独立文档的 body 片段。"""
    parts = [str(panel_soup)]

    blocks = []
    for tid in ('rank-total', 'rank-density'):
        got = rank_map.get((tid, street))
        if not got:
            continue
        head, row, ncol, title = got
        blocks.append(
            '<table class="data-table">'
            '<tr><th colspan="%d">%s</th></tr>%s%s</table>' % (ncol, title, head, row))
    if blocks:
        figs = ''.join('<div id="%s" class="chart-box tall" data-title="%s"></div>'
                       % (f, fig_title(f)) for f in APPENDIX_FIGS)
        parts.append(
            '<div class="section">'
            '<h2>附　全区位次参照</h2>'
            '<div class="section-desc">下表为该街镇在《街镇专项分析报告》全区总表中的对应行，'
            '供横向对照；两图分别为 13 个街镇投诉量与同比对比、以及对全区投诉量下降的贡献度排行。'
            '全区口径：2026 年 1-8 月投诉 13,726 件，同比 -13.1%。</div>'
            + ''.join(blocks) + figs +
            '</div>')
    return ''.join(parts)


def per_street_html(soup, street, idx, panel_soup, rank_map, note_html):
    """拼一份街镇分册的临时 HTML（仅结构与类名，转换器不读 CSS）。"""
    name = doc_name(street)
    body = panel_html(style_panel(panel_soup), rank_map, street)
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>%s12345物业投诉专项分析报告</title></head>
<body>
<div class="header">
  <div class="subtitle">数据周期：2024年1月 — 2026年8月 ｜ 同比口径：2026年1-8月 vs 2025年1-8月 ｜ 本册范围：%s</div>
  <div class="meta">徐汇区物业课题一期 · 街镇专项分析（分册） · 口径：12345 热线物业类投诉全量</div>
</div>
<div class="container">
%s
%s
</div>
</body>
</html>""" % (name, name, note_html, body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None, help='只生成指定街镇（如 长桥）')
    args = ap.parse_args()

    fp, soup = load_source()
    print('源：%s' % os.path.relpath(fp, ROOT))

    tabs = [b.get_text(strip=True) for b in soup.select('#street-tabs .tab-btn')]
    panels = soup.select('div.tab-panel')
    if len(tabs) != len(panels):
        raise SystemExit('标签数(%d)与面板数(%d)不一致' % (len(tabs), len(panels)))

    note_el = soup.select_one('.note-box')
    note_html = str(note_el) if note_el else ''
    for a, b in NOTE_FIX:
        note_html = note_html.replace(a, b)

    manifest = json.load(open(MANIFEST, encoding='utf-8'))
    rank_map = build_rank_blocks(soup)

    os.makedirs(OUTDIR, exist_ok=True)
    os.makedirs(BUILD, exist_ok=True)

    made = []
    for idx, (street, panel) in enumerate(zip(tabs, panels)):
        if args.only and street != args.only:
            continue
        name = doc_name(street)

        figmap = {}
        for f in manifest.get(STEM, []):
            if f.get('scope') == 'street' and f.get('street') == street:
                figmap[f['id']] = os.path.join(ROOT, f['file'])
            elif f.get('id') in APPENDIX_FIGS:
                figmap[f['id']] = os.path.join(ROOT, f['file'])
        wc = os.path.join(ROOT, '词云图', street + '.png')
        if os.path.exists(wc):
            figmap['c%d-wordcloud' % idx] = wc

        tmp = os.path.join(BUILD, '%02d_%s.html' % (idx, street))
        with open(tmp, 'w', encoding='utf-8') as fh:
            fh.write(per_street_html(soup, street, idx, panel, rank_map, note_html))

        doc = new_document()
        doc.add_heading('%s12345物业投诉专项分析报告' % name, level=1)
        stats = {}
        used = convert_report(doc, tmp, figmap, base=1, fig_prefix=None, stats=stats)

        outp = os.path.join(OUTDIR, '%s12345物业投诉专项分析报告.docx' % name)
        doc.save(outp)
        made.append((name, outp, len(used), stats.get('tables', 0),
                     os.path.getsize(outp) / 1024))
        print('  [%2d] %-10s 图 %-2d 表 %-3d %6.0f KB'
              % (idx, name, len(used), stats.get('tables', 0), os.path.getsize(outp) / 1024))

    print('\n共生成 %d 份 → %s' % (len(made), os.path.relpath(OUTDIR, ROOT)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
