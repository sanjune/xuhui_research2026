#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交前隐私扫描（提交前质量门）。
对「本轮将入库的文件」做手机号 / 18 位身份证 / 邮箱扫描。

Office 文件（docx/xlsx）是 zip，直接正则搜二进制无效 → 解压 *.xml 后再匹配。
"""
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PATS = {
    '手机号': re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)'),
    '身份证': re.compile(r'(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])'
                     r'(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)'),
    '邮箱': re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
}

OFFICE = ('.docx', '.xlsx', '.doc', '.xls', '.pptx')
TEXT = ('.py', '.html', '.json', '.md', '.txt', '.js', '.css', '.csv', '.yml', '.yaml')


def scan_text(p):
    try:
        s = open(p, encoding='utf-8', errors='ignore').read()
    except OSError:
        return []
    return match_all(s, p)


def scan_office(p):
    """解压 Office 包内的 xml/rels，再逐个匹配。"""
    hits = []
    try:
        z = zipfile.ZipFile(p)
    except Exception:
        return []
    with z:
        for n in z.namelist():
            if not (n.endswith('.xml') or n.endswith('.rels')):
                continue
            try:
                s = z.read(n).decode('utf-8', 'ignore')
            except Exception:
                continue
            for k, v in match_all(s, '%s!%s' % (p, n)).items():
                hits.append((k, v))
    return hits


def match_all(s, where):
    out = {}
    for name, pat in PATS.items():
        got = pat.findall(s)
        if got:
            uniq = sorted(set(got))
            out[name] = (where, uniq)
    return out


def collect():
    """取 git 视角下「已跟踪且改动 / 未跟踪」的文件，排除 .gitignore 命中的。"""
    r = subprocess.run(['git', 'status', '--porcelain', '-uall'],
                       cwd=ROOT, capture_output=True, text=True)
    files = []
    for line in r.stdout.splitlines():
        st, path = line[:2], line[3:]
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1].encode().decode('unicode_escape').encode(
                'latin1').decode('utf-8')
        if st.strip() == 'D':
            continue
        p = os.path.join(ROOT, path)
        if os.path.isfile(p):
            files.append(path)
    return files


def main():
    files = collect()
    print('=== 提交前隐私扫描：%d 个文件 ===' % len(files))
    bad = 0
    for rel in files:
        p = os.path.join(ROOT, rel)
        ext = os.path.splitext(rel)[1].lower()
        if ext in OFFICE:
            hits = scan_office(p)
        elif ext in TEXT:
            hits = [(k, v) for k, v in scan_text(p).items()]
        else:
            continue
        for k, v in hits:
            where, uniq = v if isinstance(v, tuple) else (rel, v)
            bad += 1
            print('  [%s] %s' % (k, rel))
            print('        %s' % uniq[:5])
    if bad:
        print('\n结论：发现 %d 处命中，请人工判定后决定是否提交。' % bad)
    else:
        print('\n结论：✅ 零命中（手机号 / 身份证 / 邮箱）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
