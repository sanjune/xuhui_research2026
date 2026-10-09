#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""课题成果总览.html 分类计数同步（唯一口径源）

页面每个分类头右侧写有「N项已完成 · 含M项附件」。这两个数字一律由本脚本按
卡片实际结构重算后回写，**禁止手填** —— 手填曾导致 core / analysis 两处
附件数写反（core 实为 2 项却写 1，analysis 实为 1 项却写 2）。

口径：
  已完成 N = 该分类 .cat-section 内「不含 pending 类」的 .card 数量
  附件   M = 该分类 .card-attach 区块下 <a> 的数量（页面「附 件」区实际可点的下载链接）
  待推进 K = 该分类内含 pending 类的 .card 数量

尾部描述规则：
  有附件   → 「含M项附件」
  有待推进 → 「K项待推进」（可与附件并存，用 · 连接）
  两者皆无 → 沿用原文尾部（如「1项预留」，语义为该编号未发布，非卡片数）

用法：
  python3 scripts/sync_overview_counts.py          # 校正并回写（幂等）
  python3 scripts/sync_overview_counts.py --check  # 只校验；不一致时退出码 1
"""
import argparse
import pathlib
import re
import sys

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "课题成果总览.html"
COUNT_RE = re.compile(r'(<div class="cat-count">)([^<]*)(</div>)')


def measure(soup):
    """按 DOM 实际结构测量每个分类的 已完成 / 待推进 / 附件 数量。"""
    rows = []
    for sec in soup.select('.cat-section'):
        cards = sec.select('.card')
        done = [c for c in cards if 'pending' not in (c.get('class') or [])]
        pend = [c for c in cards if 'pending' in (c.get('class') or [])]
        att = sec.select('.card-attach a')
        node = sec.select_one('.cat-count')
        rows.append({
            'sid': sec.get('id', '') or '(无 id)',
            'text': node.get_text(strip=True) if node else '',
            'done': len(done),
            'pend': len(pend),
            'attach': len(att),
        })
    return rows


def expected(row):
    """计算该分类应有的计数文本。"""
    parts = [f"{row['done']}项已完成"]
    if row['attach']:
        parts.append(f"含{row['attach']}项附件")
    if row['pend']:
        parts.append(f"{row['pend']}项待推进")
    if not row['attach'] and not row['pend']:
        # 无附件、无待推进卡 → 沿用原文尾部（「预留」类手填语义）
        tail = row['text'].split('·', 1)[1].strip() if '·' in row['text'] else ''
        assert '预留' in tail or tail == '', (
            f"[{row['sid']}] 分类既无附件也无待推进卡，但原文尾部为「{tail}」，无法自动判定，请人工确认")
        if tail:
            parts.append(tail)
    return " · ".join(parts)


def main():
    ap = argparse.ArgumentParser(description="课题成果总览分类计数同步")
    ap.add_argument('--check', action='store_true', help='只校验，不回写')
    args = ap.parse_args()

    if not PAGE.exists():
        print(f"❌ 未找到 {PAGE}")
        return 2

    html = PAGE.read_text(encoding='utf-8')
    rows = measure(BeautifulSoup(html, 'html.parser'))
    want = [expected(r) for r in rows]

    matches = list(COUNT_RE.finditer(html))
    assert len(matches) == len(rows), \
        f"页面 cat-count 节点 {len(matches)} 处 ≠ 分类 {len(rows)} 处，结构异常"

    out, cursor, changed = [], 0, []
    for m, row, w in zip(matches, rows, want):
        cur = m.group(2).strip()
        out.append(html[cursor:m.start(2)])
        out.append(w)
        cursor = m.end(2)
        if cur != w:
            changed.append((row, cur, w))
    out.append(html[cursor:])

    print(f"扫描 {PAGE.name}：{len(rows)} 个分类")
    for row, cur, w in changed:
        print(f"  · [{row['sid']}] 「{cur}」 → 「{w}」"
              f"（卡片 {row['done'] + row['pend']}｜已完成 {row['done']}"
              f"｜附件 {row['attach']}｜待推进 {row['pend']}）")

    if not changed:
        print("  · 全部分类计数与卡片结构一致 ✅")
        return 0
    if args.check:
        print(f"❌ 共 {len(changed)} 处不一致（未回写）")
        return 1

    PAGE.write_text(''.join(out), encoding='utf-8')
    print(f"✅ 已回写 {PAGE.name}（{len(changed)} 处）")
    return 0


if __name__ == '__main__':
    sys.exit(main())
