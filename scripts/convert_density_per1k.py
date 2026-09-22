# -*- coding: utf-8 -*-
"""
《物业投诉根因分析报告.html》密度口径统一：每百户 → 每千户
=============================================================

规则（用户确认）：投诉密度 = 每一千户的投诉数量（件/千户）。

处理方式：
  1. 表格：定位表头含「每百户」的列，该列所有数值 ×10
  2. SVG 街道密度地图：13 个街道数值 ×10；分级图例阈值 ×10；注释文字
  3. 柱状图：标题含「每百户投诉量」的区块内 bar-val ×10
  4. 正文段落：绝对数值 ×10（倍数、百分比**不变**）
  5. 文案：每百户 → 每千户；件/百户 → 件/千户

注意：比例类表述（2.4倍、5.1倍、低14.7%、-23.2%）不受口径影响，保持不变。

用法：
    python scripts/convert_density_per1k.py             # 执行转换
    python scripts/convert_density_per1k.py --dry-run   # 只打印改动预览
"""
import argparse
import re
import sys

ROOT = "/Users/macbookpro/Desktop/8-24 徐汇课题一期"
REPORT = f"{ROOT}/物业投诉根因分析报告.html"


def fmt10(val: float) -> str:
    """数值 ×10 后的格式化：整数不带小数点，否则最多 2 位并去掉尾零。"""
    x = round(val * 10, 2)
    if abs(x - int(x)) < 1e-9:
        return str(int(x))
    return f"{x:.2f}".rstrip("0").rstrip(".")


NUM_RE = re.compile(r"(\d+(?:\.\d+)?)")


def scale_cell(text: str, log: list) -> str:
    """把单元格文本里的数值 ×10（保留单位等其余字符）。"""
    def rep(m):
        new = fmt10(float(m.group(1)))
        log.append(f"{m.group(1)} → {new}")
        return new
    return NUM_RE.sub(rep, text)


# ─────────────────────────── 1. 表格列 ───────────────────────────

def convert_tables(s: str, log: list) -> str:
    out, cursor = [], 0
    for m in re.finditer(r"<table[^>]*>.*?</table>", s, re.S):
        table = m.group(0)
        rows = re.findall(r"<tr>(.*?)</tr>", table, re.S)
        if len(rows) < 2:
            continue
        ths = [re.sub(r"<[^>]+>", "", x).strip()
               for x in re.findall(r"<th[^>]*>(.*?)</th>", rows[0], re.S)]
        idx = [i for i, x in enumerate(ths) if "每百户" in x]
        if not idx:
            continue
        new_rows = [rows[0]]
        for r in rows[1:]:
            tds = re.findall(r"(<td[^>]*>)(.*?)(</td>)", r, re.S)
            if not tds:
                new_rows.append(r)
                continue
            parts = []
            for i, (op, body, cl) in enumerate(tds):
                if i in idx:
                    plain = re.sub(r"<[^>]+>", "", body).strip()
                    if NUM_RE.search(plain):
                        new_plain = scale_cell(plain, log)
                        # 只替换纯文本部分（保留可能包裹的 <strong> 等标签）
                        body_new = body.replace(plain, new_plain, 1)
                        parts.append(op + body_new + cl)
                        continue
                parts.append(op + body + cl)
            new_rows.append("<tr>" + "".join(parts) + "</tr>")
        new_table = re.sub(r"<tr>.*?</tr>", lambda _: new_rows.pop(0), table, count=len(rows), flags=re.S)
        out.append(s[cursor:m.start()])
        out.append(new_table)
        cursor = m.end()
        log.append(f"✔ 表格 @{m.start()} 列{idx}「{ths[idx[0]]}」已换算")
    out.append(s[cursor:])
    return "".join(out)


# ─────────────────────────── 2. SVG 地图 ───────────────────────────

def convert_svg_map(s: str, log: list) -> str:
    i = s.find("每百户投诉量分布图")
    if i < 0:
        return s
    j = s.find("</svg>", i)
    seg = s[i:j]
    orig = seg

    # 13 个街道数值：形如 >19.1件< 或 >16.7件 ↓<
    seg = re.sub(r"(>)([\d.]+)(件)( ↓)?(<)",
                 lambda m: m.group(1) + fmt10(float(m.group(2))) + m.group(3)
                            + (m.group(4) or "") + m.group(5), seg)

    # 分级图例阈值
    legend = [
        ("极高 (≥16件)", "极高 (≥160件)"),
        ("高 (13-16件)", "高 (130-160件)"),
        ("中高 (11-13件)", "中高 (110-130件)"),
        ("中 (10-11件)", "中 (100-110件)"),
        ("中低 (9-10件)", "中低 (90-100件)"),
        ("低 (&lt;9件)", "低 (&lt;90件)"),
    ]
    for old, new in legend:
        if old in seg:
            seg = seg.replace(old, new)

    # 注释文字里的数值
    for old, new in [("每百户最高(19.1)", "每千户最高(191)"),
                     ("每百户仅11.4", "每千户仅114")]:
        if old in seg:
            seg = seg.replace(old, new)

    if seg != orig:
        log.append("✔ SVG 街道密度地图：13 个街道数值 + 6 档图例阈值 + 2 处注释 已换算")
    return s[:i] + seg + s[j:]


# ─────────────────────────── 3. 柱状图 ───────────────────────────

def convert_bars(s: str, log: list) -> str:
    for m in re.finditer(r"每百户投诉量（件/百户）：|每百户投诉量对比（柱状图）：", s):
        start = m.end()
        nxt = re.search(r'<div class="highlight"|<p style="margin:12px 0 6px', s[start:start + 2000])
        end = start + (nxt.start() if nxt else 1200)
        seg = s[start:end]
        new = re.sub(r'(class="bar-val">)([\d.]+)(件</span>)',
                     lambda x: x.group(1) + fmt10(float(x.group(2))) + x.group(3), seg)
        if new != seg:
            vals = re.findall(r'class="bar-val">([\d.]+)件', seg)
            log.append(f"✔ 柱状图 @{m.start()} {len(vals)} 条 bar-val 已换算: {vals}")
        s = s[:start] + new + s[end:]
    return s


# ─────────────────────────── 4. 正文段落 ───────────────────────────

# 仅替换绝对数值；倍数（2.4倍/5.1倍）与百分比（低14.7%/-23.2%）保持原样
PROSE_PAIRS = [
    ("1元以下最高（22.25件），3-5元最低（11.80件）",
     "1元以下最高（222.5件），3-5元最低（118.0件）"),
    ("每百户15.61件高于2-3元（12.33件）",
     "每千户156.1件高于2-3元（123.3件）"),
    ("无电梯小区每百户投诉17.60件为最高，20台以上小区仅13.01件为最低",
     "无电梯小区每千户投诉176.0件为最高，20台以上小区仅130.1件为最低"),
    ("每百户投诉量反而低14.7%（14.68 vs 17.21）",
     "每千户投诉量反而低14.7%（146.8 vs 172.1）"),
    ("湖南路（19.1件）仍是龙华（9.0件）的2.1倍",
     "湖南路（191件）仍是龙华（90件）的2.1倍"),
    ("每百户投诉量从小型小区16.6件降至超大型小区10.8件",
     "每千户投诉量从小型小区166件降至超大型小区108件"),
    ("40年以上小区每百户投诉16.4件，直管公房投诉最高但改善也最快",
     "40年以上小区每千户投诉164件，直管公房投诉最高但改善也最快"),
    ("小型小区每百户投诉量（16.6件）是超大型小区的1.5倍",
     "小型小区每千户投诉量（166件）是超大型小区的1.5倍"),
    ("（40年以上小区每百户投诉16.4件，是10年以内新小区的2.4倍）",
     "（40年以上小区每千户投诉164件，是10年以内新小区的2.4倍）"),
]


def convert_prose(s: str, log: list) -> str:
    for old, new in PROSE_PAIRS:
        if old in s:
            s = s.replace(old, new)
            log.append(f"✔ 正文: {old[:34]}… → {new[:34]}…")
        else:
            log.append(f"⚠ 正文未命中: {old[:40]}…")
    return s


# ─────────────────────────── 5. 文案 ───────────────────────────

def convert_wording(s: str, log: list) -> str:
    n1 = s.count("每百户")
    n2 = s.count("件/百户")
    s = s.replace("每百户", "每千户").replace("件/百户", "件/千户")
    log.append(f"✔ 文案替换：每百户→每千户 {n1} 处；件/百户→件/千户 {n2} 处")
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    s = open(REPORT, encoding="utf-8").read()
    log = []

    s = convert_tables(s, log)
    s = convert_svg_map(s, log)
    s = convert_bars(s, log)
    s = convert_prose(s, log)
    s = convert_wording(s, log)

    left = s.count("每百户") + s.count("件/百户")
    for line in log:
        print(line)
    print()
    print(f"残留「每百户/件/百户」: {left}")
    print(f"新增「每千户」: {s.count('每千户')}  「件/千户」: {s.count('件/千户')}")

    if args.dry_run:
        print("\n[dry-run] 未写入文件")
        return
    if left:
        print("\n⚠ 仍有残留，未写入。请先处理。")
        sys.exit(1)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"\n✔ 已写入 {REPORT}")


if __name__ == "__main__":
    main()
