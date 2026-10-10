#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update_rootcause_groups.py — 用 993 口径 · 2026年1-8月 重算值回填
《物业投诉根因分析报告》三 / 四 / 五 节的分组表与结论

回填范围（幂等可重复执行）
--------------------------
  3.2 收费模式、3.3 物业公司投诉Top10、
  4.1 电梯（整节：标题/正文/2 张表/2 组柱状图/双维发现）、
  4.1b 电梯投诉内容分析中的小区数（738 → 737）、
  4.2 车位配比（整节）、4.3 修缮（整节）、
  5.1 业委会（表 + 发现）

数据源
------
  scripts/root_cause_2026_data_v2.json    ← recalc_rootcause_2026.py（第七节口径，权威）
  scripts/root_cause_groups_2026.json     ← recalc_rootcause_groups.py（本章其余分组）

⚠️ 不覆盖 3.1 物业费（关联库无「收费标准」字段，无可复现数据源，维持原样并在表下加注）
⚠️ 5.2 底部抬升表与「发现」段由 `update_rootcause_report_2026.py` 托管，本脚本不碰

用法
----
    PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/update_rootcause_groups.py [--dry]
"""
from __future__ import annotations

import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "物业投诉根因分析报告.html")
V2 = os.path.join(ROOT, "scripts", "root_cause_2026_data_v2.json")
GRP = os.path.join(ROOT, "scripts", "root_cause_groups_2026.json")

HEAD = ("<th>分组</th><th>小区数</th><th>2026年1-8月均值</th>"
        "<th>每千户(2026年1-8月)</th><th>2026同比</th><th>对比</th>")


# ─────────────────────────────────────────────────────────────
def cls(v):
    return "trend-down" if v < 0 else "trend-up"


def cell(v):
    return f'<td class="{cls(v)}">{v:+.1f}%</td>'


def row(label, s, extra=""):
    return (f"      <tr><td>{label}</td><td>{s['count']}</td><td>{s['avg_2026']:.1f}件</td>"
            f"<td>{s['per1k_2026']:.1f}件</td>{cell(s['yoy'])}{extra}</tr>\n")


def table(header_extra, rows, head=HEAD):
    return ('    <table>\n      <tbody>' + head + "\n" + "".join(rows)
            + "    </tbody></table>\n")


# ─────────────────────────────────────────────────────────────
def build_fee_mode(g):
    rows = []
    b = g["包干制"]
    rows.append(row("包干制", b, "<td>基准</td>"))
    for k, lab in (("酬金制", "酬金制"), ("其他/未标注", "其他/未标注")):
        s = g[k]
        d = (b["avg_2026"] - s["avg_2026"]) / b["avg_2026"] * 100
        rows.append(row(lab, s, f'<td>总量低{d:.1f}%</td>'))
    head = ("<th>收费模式</th><th>小区数</th><th>2026年1-8月均值</th>"
            "<th>每千户(2026年1-8月)</th><th>2026同比</th><th>对比</th>")
    return table(None, rows, head=head)


def build_company(rows10):
    out = []
    for i, r in enumerate(rows10, 1):
        out.append(f"      <tr><td>{i}</td><td>{r['name']}</td><td>{r['count']}</td>"
                   f"<td>{r['total_2026']:,}</td><td>{r['avg_2026']:.1f}件</td>"
                   f"<td>{r['per1k_2026']:.1f}件</td>{cell(r['yoy'])}</tr>\n")
    return ('    <table>\n      <tbody><th>排名</th><th>物业公司</th><th>管理小区</th>'
            '<th>2026年1-8月投诉量</th><th>小区均投诉</th><th>每千户投诉</th><th>2026同比</th>\n'
            + "".join(out) + "    </tbody></table>\n")


# ─────────────────────────────────────────────────────────────
def build_elevator(v2):
    d = v2["elevator_detail"]
    two = v2["elevator"]
    ne, ye = two["无电梯"], two["有电梯"]
    e20 = d["20台以上"]
    e1120 = d["11-20台"]
    times = e20["avg_2026"] / ne["avg_2026"]
    gap = (e1120["per1k_2026"] - ne["per1k_2026"]) / ne["per1k_2026"] * 100

    L = []
    L.append('<div class="sub-title" id="sub-11">4.1 电梯：投诉总量与电梯数量正相关，'
             '每千户投诉强度同步上升</div>\n')
    L.append('    <p class="desc">从投诉总量看，电梯越多的小区投诉越多（因规模更大）；'
             '从每千户投诉强度看，同样呈上升趋势——电梯体量越大，'
             '设备类与协同类诉求越密集。</p>\n\n')

    rows = [row("无电梯", ne), row("有电梯", ye)]
    L.append('    <table>\n      <tbody><th>电梯状况</th><th>小区数</th>'
             '<th>2026年1-8月均值</th><th>每千户(2026年1-8月)</th><th>2026同比</th>\n'
             + "".join(rows) + "    </tbody></table>\n\n")

    L.append('    <p style="margin:12px 0 6px;font-weight:600;color:#1565c0;">按电梯台数分段：</p>\n\n')
    order = ["无电梯", "1-5台", "6-10台", "11-20台", "20台以上"]
    L.append('    <table>\n      <tbody><th>电梯台数</th><th>小区数</th>'
             '<th>2026年1-8月均值</th><th>每千户(2026年1-8月)</th><th>2026同比</th>\n'
             + "".join(row(k, d[k]) for k in order) + "    </tbody></table>\n\n")

    # 柱状图（按最大值归一）
    def bars(title, key, grad=None):
        mx = max(d[k][key] for k in order)
        out = [f'    <p style="margin:12px 0 6px;font-weight:600;color:#1565c0;">{title}</p>\n',
               '    <div style="margin:8px 0;">\n']
        for k in order:
            v = d[k][key]
            w = max(4, round(v / mx * 100))
            if grad:
                g2 = "#" if False else ""
                style = f'background:linear-gradient(90deg,{grad});'
            else:
                style = ''
            out.append(f'      <div class="bar-row"><div class="bar-label">{k}</div>'
                       f'<div class="bar-bg"><div class="bar-fill" style="{style}width:{w}%;">'
                       f'<span class="bar-val">{v:.1f}件</span></div></div></div>\n')
        out.append('    </div>\n\n')
        return "".join(out)

    L.append(bars("投诉总量对比（柱状图）：", "avg_2026"))
    L.append(bars("每千户投诉量对比（柱状图）：", "per1k_2026",
                  grad="#ef5350,#c62828"))
    L.append('    <div class="highlight">\n')
    L.append('      <strong>双维发现：</strong><br>\n')
    L.append(f'      <strong>① 总量维度：</strong>电梯越多投诉总量越高——20台以上小区 2026年1-8月均值 '
             f'{e20["avg_2026"]:.1f} 件，是无电梯小区（{ne["avg_2026"]:.1f} 件）的 {times:.1f} 倍，'
             f'因为电梯多的小区通常规模更大（户数更多）。<br>\n')
    L.append(f'      <strong>② 每千户维度：</strong>结论一致——无电梯小区每千户投诉 '
             f'{ne["per1k_2026"]:.1f} 件最低，11-20台小区 {e1120["per1k_2026"]:.1f} 件最高'
             f'（高 {gap:.1f}%），说明电梯体量越大、单位户数的投诉强度越高。<br>\n')
    L.append(f'      <strong>③ 趋势维度：</strong>五组 2026 年 1-8 月同比均为下降，'
             f'其中 6-10 台降幅最大（{d["6-10台"]["yoy"]:+.1f}%），'
             f'无电梯降幅最小（{ne["yoy"]:+.1f}%），低层老旧小区改善相对滞后。<br>\n')
    L.append('    </div>\n\n    ')
    return "".join(L)


def build_parking(g):
    p = g
    L = ['<div class="sub-title" id="sub-13">4.2 车位配比：车位越充足，投诉越少</div>\n']
    L.append('    <p class="desc">车位配比（车位数/户数）与投诉量呈明显负相关——'
             '车位越充足，投诉越少。</p>\n\n')
    order = ["严重不足(<0.3)", "不足(0.3-0.5)", "基本平衡(0.5-0.8)", "充足(>0.8)"]
    rows = []
    base = p[order[0]]
    rows.append(row(order[0], base, "<td>基准</td>"))
    for k in order[1:]:
        s = p[k]
        d = (base["avg_2026"] - s["avg_2026"]) / base["avg_2026"] * 100
        rows.append(row(k, s, f'<td>总量低{d:.1f}%</td>'))
    L.append('    <table>\n      <tbody><th>车位配比</th><th>小区数</th>'
             '<th>2026年1-8月均值</th><th>每千户(2026年1-8月)</th><th>2026同比</th>'
             '<th>对比基准</th>\n' + "".join(rows) + "    </tbody></table>\n")
    L.append(f'    <p style="margin:6px 0;font-size:12px;color:#888;">'
             f'注：充足组每千户偏高因样本量小（{p[order[3]]["count"]}个）且含部分小型特殊小区，'
             f'总量维度更有参考价值。</p>\n\n')
    ratio = p[order[3]]["avg_2026"] / base["avg_2026"] * 100
    L.append('    <div class="highlight green">\n')
    L.append(f'      <strong>发现：</strong>车位充足小区的投诉量仅为严重不足小区的 '
             f'{ratio:.1f}%（{p[order[3]]["avg_2026"]:.1f} 件 vs {base["avg_2026"]:.1f} 件）。'
             f'停车是物业投诉的第一大类别，车位供给直接决定了停车管理的难度和投诉量。'
             f'增加车位供给是降低投诉的最有效硬件手段之一。\n')
    L.append('    </div>\n\n    ')
    return "".join(L)


def build_repair(v2, g):
    r = v2["repair"]
    no, yes = r["无修缮"], r["有修缮"]
    det = g["repair_detail"]
    up = (yes["avg_2026"] - no["avg_2026"]) / no["avg_2026"] * 100
    L = ['<div class="sub-title" id="sub-14">4.3 修缮项目："投诉越多的小区修得越多，'
         '但修缮确实有效"</div>\n\n']
    L.append('    <table>\n      <tbody><th>修缮状况</th><th>小区数</th>'
             '<th>2026年1-8月均值</th><th>每千户(2026年1-8月)</th><th>2026同比</th>\n'
             + row("无修缮项目", no) + row("有修缮项目", yes) + "    </tbody></table>\n\n")

    order = ["无修缮", "1个项目", "2个项目及以上"]
    mx = max(abs(det[k]["yoy"]) for k in order)
    L.append('    <div style="margin:14px 0;">\n')
    for k in order:
        v = det[k]["yoy"]
        w = max(4, round(abs(v) / mx * 100))
        fill = "" if k == "无修缮" else " tertiary"
        L.append(f'      <div class="bar-row"><div class="bar-label">{k}</div>'
                 f'<div class="bar-bg"><div class="bar-fill{fill}" style="width:{w}%;">'
                 f'<span class="bar-val">{v:+.1f}%</span></div></div></div>\n')
    L.append('    </div>\n\n')

    L.append('    <div class="highlight green">\n')
    L.append(f'      <strong>发现：</strong>有修缮项目的小区投诉量（{yes["avg_2026"]:.1f}件）'
             f'远高于无修缮小区（{no["avg_2026"]:.1f}件，高 {up:.1f}%）——这是"逆向选择"：'
             f'问题越多的小区越容易获得修缮资源。但关键在于：有修缮的小区 2026 年 1-8 月同比 '
             f'{yes["yoy"]:+.1f}%，降幅明显大于无修缮小区（{no["yoy"]:+.1f}%）。'
             f'修缮项目数越多，改善效果越明显（2 个项目及以上的小区同比下降 '
             f'{abs(det["2个项目及以上"]["yoy"]):.1f}%）。'
             f'<strong>修缮投入是治理房屋维修类投诉的根本手段。</strong>\n')
    L.append('    </div>\n\n')
    return "".join(L)


def build_committee(g):
    y, n = g["有业委会"], g["无业主大会"]
    d = (n["avg_2026"] - y["avg_2026"]) / n["avg_2026"] * 100
    L = ['<div class="sub-title" id="sub-16">5.1 业委会：有业委会的小区投诉更低</div>\n\n']
    rows = (row("无业主大会", n, "<td>基准</td>")
            + row("有业委会", y, f'<td>总量低{d:.1f}%</td>'))
    L.append('    <table>\n      <tbody><th>业委会状态</th><th>小区数</th>'
             '<th>2026年1-8月均值</th><th>每千户(2026年1-8月)</th><th>2026同比</th>'
             '<th>差异</th>\n' + rows + "    </tbody></table>\n\n")
    L.append('    <div class="highlight green">\n')
    L.append(f'      <strong>发现：</strong>有业委会的小区投诉量比无业主大会小区低 {d:.1f}%'
             f'（{y["avg_2026"]:.1f} 件 vs {n["avg_2026"]:.1f} 件），且同比方向相反'
             f'（{y["yoy"]:+.1f}% vs {n["yoy"]:+.1f}%）。业委会作为业主自治组织，'
             f'能够有效协调业主与物业的关系，减少矛盾激化。'
             f'推进业委会组建是降低投诉的重要治理手段。\n')
    L.append('    </div>\n\n    ')
    return "".join(L)


def build_hardware(v2):
    """二、硬件因素分析：2.1 小区规模 / 2.2 房龄 / 2.3 房屋性质（统一 v2 口径）。"""
    L = []
    # 2.1 规模
    sc = v2["scale"]
    mic, sup = sc["微型(<200户)"], sc["超大型(>2000)"]
    d = (mic["per1k_2026"] - sup["per1k_2026"]) / mic["per1k_2026"] * 100
    L.append('<div class="sub-title" id="sub-3">2.1 小区规模：体量越大投诉越多，但效率越高</div>\n')
    L.append('    <p class="desc">小区规模（户数）是影响投诉量的最强因素，相关系数达<strong>0.782</strong>。'
             '但归一化为"每千户投诉量"后，呈现明显的<strong>规模经济效应</strong>。</p>\n\n')
    L.append('    <table>\n      <tbody><th>小区规模</th><th>小区数</th><th>2026年1-8月均值</th>'
             '<th>每千户(2026年1-8月)</th><th>2026同比</th>\n')
    for k in ["微型(<200户)", "小型(200-500)", "中型(500-1000)", "大型(1000-2000)", "超大型(>2000)"]:
        L.append(row(k, sc[k]))
    L.append("    </tbody></table>\n\n")
    L.append('    <div class="highlight green">\n')
    L.append(f'      <strong>发现：</strong>超大型小区（>2000户）每千户投诉量比微型小区（<200户）低 '
             f'{d:.1f}%。原因在于：① 大小区物业资源更充足，管理团队更专业；'
             f'② 规模效应摊薄管理成本；③ 业主自治基础更好。'
             f'微型小区（<200户）是治理洼地，需重点关注。\n')
    L.append('    </div>\n\n')

    # 2.2 房龄
    ag = v2["age"]
    y10, y40 = ag["10年以内"], ag["40年以上"]
    times = y40["per1k_2026"] / y10["per1k_2026"]
    L.append('<div class="sub-title" id="sub-4">2.2 房龄：40年以上老小区投诉强度最高</div>\n')
    L.append('    <p class="desc">房龄与投诉量不呈简单线性关系，但按每千户投诉量归一化后，'
             '<strong>房龄越大投诉强度越高</strong>的趋势明显。</p>\n\n')
    L.append('    <table>\n      <tbody><th>房龄段</th><th>小区数</th><th>2026年1-8月均值</th>'
             '<th>每千户(2026年1-8月)</th><th>2026同比</th>\n')
    for k in ["10年以内", "10-20年", "20-30年", "30-40年", "40年以上"]:
        L.append(row(k, ag[k]))
    L.append("    </tbody></table>\n")
    L.append(f'    <p style="font-size:11px; color:#999;">*10年以内小区仅 {y10["count"]} 个，'
             f'样本量小，同比波动较大，参考性有限</p>\n\n')
    L.append('    <div class="highlight">\n')
    L.append(f'      <strong>发现：</strong>40年以上老小区每千户投诉量是10年以内新小区的 '
             f'{times:.1f} 倍。老旧小区设施老化、维修资金不足、物业管理难度大是根本原因。'
             f'五档房龄在 2026 年 1-8 月同比均为下降，其中 40 年以上降幅 {y40["yoy"]:+.1f}%，'
             f'低于 10 年以内（{y10["yoy"]:+.1f}%），说明老旧小区改善节奏相对偏慢。\n')
    L.append('    </div>\n\n')

    # 2.3 房屋性质
    na = v2["nature"]
    feats = {"直管公房": "投诉强度最高且逆势上升", "售后房": "每千户投诉偏高",
             "商品房": "基数低、降幅居中", "混合": "产权复杂治理难"}
    L.append('<div class="sub-title" id="sub-5">2.3 房屋性质：直管公房投诉强度最大</div>\n\n')
    L.append('    <table>\n      <tbody><th>房屋性质</th><th>小区数</th><th>2026年1-8月均值</th>'
             '<th>每千户(2026年1-8月)</th><th>2026同比</th><th>特征</th>\n')
    for k in ["直管公房", "混合", "商品房", "售后房"]:
        s = na[k]
        L.append(f"      <tr><td>{k}</td><td>{s['count']}</td><td>{s['avg_2026']:.1f}件</td>"
                 f"<td>{s['per1k_2026']:.1f}件</td>{cell(s['yoy'])}"
                 f"<td>{feats[k]}</td></tr>\n")
    L.append("    </tbody></table>\n\n")
    L.append('    <div class="highlight green">\n')
    L.append(f'      <strong>发现：</strong>直管公房投诉强度最高（{na["直管公房"]["avg_2026"]:.1f}件/小区、'
             f'每千户 {na["直管公房"]["per1k_2026"]:.1f} 件），且 2026 年 1-8 月同比 '
             f'{na["直管公房"]["yoy"]:+.1f}%，是四类房屋性质中唯一上升者，需重点关注。'
             f'混合类小区同期降幅最大（{na["混合"]["yoy"]:+.1f}%）；商品房每千户投诉最低'
             f'（{na["商品房"]["per1k_2026"]:.1f} 件）。\n')
    L.append('    </div>\n\n')
    return "".join(L)


# ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    v2 = json.load(open(V2, encoding="utf-8"))
    gj = json.load(open(GRP, encoding="utf-8"))
    s = open(REPORT, encoding="utf-8").read()
    orig = len(s)
    miss = []

    def sub(pat, new, label, count=1, flags=re.S):
        nonlocal s
        s2, k = re.subn(pat, new, s, count=count, flags=flags)
        if k:
            s = s2
        else:
            miss.append(label)
        return k

    # 0) 二、硬件因素（2.1 规模 / 2.2 房龄 / 2.3 性质）
    SEC3 = '  </div>\n\n  <!-- ===== 三、物业因素 ===== -->'
    sub(r'<div class="sub-title" id="sub-3">[\s\S]*?\n  </div>\n\n  <!-- ===== 三、物业因素 ===== -->',
        build_hardware(v2) + SEC3, "二、硬件因素")
    # 1) 3.2 收费模式表
    sub(r'    <table>\n      <tbody><th>收费模式</th>[\s\S]*?</tbody></table>\n',
        build_fee_mode(gj["fee_mode"]), "3.2 收费模式")
    # 2) 3.3 公司 Top10
    sub(r'    <table>\n      <tbody><th>排名</th><th>物业公司</th>[\s\S]*?</tbody></table>\n',
        build_company(gj["company_top10"]), "3.3 公司Top10")
    # 3) 4.1 电梯整节
    sub(r'<div class="sub-title" id="sub-11">[\s\S]*?(?=<div class="sub-title" id="sub-12">)',
        build_elevator(v2), "4.1 电梯")
    # 4) 4.1b 小区数 738 → 737（幂等：737/738 均可匹配）
    sub(r'(<tr><td>无电梯</td><td>)73[78](</td><td>40\.0%)', r'\g<1>737\g<2>', "4.1b 表")
    sub(r'73[78]个无电梯小区', '737个无电梯小区', "4.1b 正文")
    # 5) 4.2 车位
    sub(r'<div class="sub-title" id="sub-13">[\s\S]*?(?=<div class="sub-title" id="sub-14">)',
        build_parking(gj["parking"]), "4.2 车位")
    # 6) 4.3 修缮（显式吃掉本节收尾 </div>，保证幂等）
    SEC5 = '  </div>\n\n  <!-- ===== 五、治理因素 ===== -->'
    sub(r'<div class="sub-title" id="sub-14">[\s\S]*?\n  </div>\n\n  <!-- ===== 五、治理因素 ===== -->',
        build_repair(v2, gj) + SEC5, "4.3 修缮")
    # 7) 5.1 业委会
    sub(r'<div class="sub-title" id="sub-16">[\s\S]*?(?=<div class="sub-title" id="sub-17">)',
        build_committee(gj["committee"]), "5.1 业委会")
    # 8) 5.2 标题倍数
    sub(r'(<div class="sub-title" id="sub-17">)5\.2 底部抬升小区：投诉强度是普通小区的\d\.\d倍',
        r'\g<1>5.2 底部抬升小区：投诉强度是普通小区的2.4倍', "5.2 标题")
    # 9) 3.1 物业费加注（若无）
    note = ('    <p style="margin:10px 0 0;font-size:12px;color:#888;">'
            '注：物业费分段沿用《纳统小区 (2026 更新版)》档案「收费标准」原始口径；'
            '本章其余分组已统一按「纳统小区 993 个名单内 · 2026年1-8月 vs 2025年同期」口径重算。</p>\n')
    if "本章其余分组已统一按" not in s:
        sub(r'(<div class="sub-title" id="sub-8">3\.2 收费模式)',
            note + r'\g<1>', "3.1 加注")

    print(f"回填命中：{'全部' if not miss else '缺 ' + str(miss)}")
    print(f"{orig:,} → {len(s):,} 字符（Δ{len(s)-orig:+,}）")
    if a.dry:
        print("（dry-run，未写盘）")
        return
    open(REPORT, "w", encoding="utf-8").write(s)
    print(f"✔ 已回填 {os.path.basename(REPORT)}")


if __name__ == "__main__":
    main()
