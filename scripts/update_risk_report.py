# -*- coding: utf-8 -*-
"""更新《高风险小区预警清单.html》为「纳统小区（2026 更新版）」口径
====================================================================

项目组 2026-09-28 决策：风险评估报告仅统计《纳统小区 (2026 更新版).xls》名单内的
小区，不在名单中的小区不做统计；统计单元＝纳统小区（别名/曾用名已归并）；
投诉数据按热线数据表口径统计。

数据来源
--------
· 第一~四、六、七章与图表：`scripts/risk_scores.json`（由 risk_scoring.py 生成，
  口径 `--scope aggregate --with-aug`：纳统聚合 + 2026年1-8月）
· 第五章「2026年近期预警」：`data/merged_cleaned.pkl` 全量口径（不剔十四类），
  同样收窄到纳统名单并按纳统小区聚合 —— 与原报告该章口径一致（已逐项核对复现）

用法
----
    python3 scripts/update_risk_report.py [--dry-run]
"""
import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import nato_match as NM  # noqa: E402

RISK = os.path.join(ROOT, "scripts", "risk_scores.json")
PKL = os.path.join(ROOT, "data", "merged_cleaned.pkl")
REPORT = os.path.join(ROOT, "高风险小区预警清单.html")

RED, GREEN, GREY = "#f5222d", "#00a854", "#666"

_ap = argparse.ArgumentParser()
_ap.add_argument("--dry-run", action="store_true", help="只计算与打印，不改 HTML")
ARGS = _ap.parse_args()


# ─────────────────────────────────────────────────────────────
# 一、主模型（risk_scores.json）
# ─────────────────────────────────────────────────────────────
def build_main_blocks(risk):
    ac = risk["all_communities"]
    lv = {}
    for c in ac:
        lv[c["risk_level"]] = lv.get(c["risk_level"], 0) + 1
    n = len(ac)
    r, o, y, b = lv.get("红色", 0), lv.get("橙色", 0), lv.get("黄色", 0), lv.get("蓝色", 0)

    st = {}
    for c in ac:
        d = st.setdefault(c["street"], {"n": 0, "红": 0, "橙": 0, "黄": 0, "蓝": 0})
        d["n"] += 1
        if c["risk_level"] in ("红色", "橙色", "黄色", "蓝色"):
            d[c["risk_level"][0]] += 1

    rows_st = []
    for s, d in sorted(st.items(), key=lambda x: -x[1]["n"]):
        pct = d["红"] / d["n"] * 100 if d["n"] else 0
        hot = ' style="color:#f5222d;font-weight:600;"' if pct >= 35 else ""
        c_red = f'<span class="badge red">{d["红"]}</span>' if d["红"] else "0"
        c_org = f'<span class="badge orange">{d["橙"]}</span>' if d["橙"] else "0"
        rows_st.append(
            f'        <tr><td style="text-align:left;font-weight:600;">{s}</td>'
            f'<td>{d["n"]}</td><td>{c_red}</td><td>{c_org}</td>'
            f'<td>{d["黄"]}</td><td>{d["蓝"]}</td>'
            f'<td{hot}>{pct:.1f}%</td></tr>')

    rows_t = []
    for i, c in enumerate(ac[:30], 1):
        g = c["growth_rate"]
        gc = RED if g > 0 else GREEN
        rows_t.append(
            f'        <tr><td>{i}</td>'
            f'<td style="text-align:left;font-weight:700;">{c["community"]}</td>'
            f'<td>{c["street"]}</td>'
            f'<td style="font-weight:700;color:#f5222d;">{c["total_score"]}</td>'
            f'<td>{c["total"]}</td>'
            f'<td style="color:{gc};font-weight:600;">{g:+.1f}%</td>'
            f'<td>{c["repeat_rate"]}%</td>'
            f'<td>{c["top_category"]}</td>'
            f'<td>{c["company"]}</td>'
            f'<td><span class="badge red">红</span></td></tr>')

    ranked = sorted(st.items(), key=lambda x: -(x[1]["红"] / x[1]["n"] if x[1]["n"] else 0))
    return {
        "n": n, "r": r, "o": o, "y": y, "b": b,
        "street_table": "\n".join(rows_st),
        "top_table": "\n".join(rows_t),
        "hot_street": ranked[0][0], "hot_pct": ranked[0][1]["红"] / ranked[0][1]["n"] * 100,
        "2nd_street": ranked[1][0], "2nd_pct": ranked[1][1]["红"] / ranked[1][1]["n"] * 100,
    }


# ─────────────────────────────────────────────────────────────
# 二、第五章（merged_cleaned 全量口径 + 纳统范围）
# ─────────────────────────────────────────────────────────────
def load_ch5():
    p = pd.read_pickle(PKL)
    p["cm"] = p["community_name"].fillna("").astype(str).str.strip()
    p = p[~p["cm"].isin(["", "无", "nan", "None"])].copy()
    st = p.groupby("cm")["street"].agg(lambda s: s.mode().iloc[0] if len(s.mode()) else "")
    mp = NM.build_map(sorted(st.index), streets=st.to_dict())
    ok = set(mp.loc[mp["matched"], "hotline_name"])
    p = p[p["cm"].isin(ok)]
    p = NM.aggregate_key(p, col="cm", mp=mp)
    p = p[p["nato_community"] != ""]

    # 底部抬升标签（来自小区档案）
    bl = set()
    try:
        cl = pd.read_pickle(os.path.join(ROOT, "data", "community_linked_data.pkl"))
        if "is_bottom_lift" in cl.columns:
            bl = set(cl.loc[cl["is_bottom_lift"].astype(str).isin(["1", "1.0", "True", "是"]),
                           "community_name"])
    except Exception:
        pass

    rows = []
    for name, g in p.groupby("nato_community"):
        n24 = int((g["year"] == 2024).sum())
        n25 = int(((g["year"] == 2025) & (g["month"] <= 8)).sum())
        n26 = int(((g["year"] == 2026) & (g["month"] <= 8)).sum())
        mode = g["street"].mode()
        rows.append({"community": name,
                     "street": mode.iloc[0] if len(mode) else "",
                     "n2026": n26, "n2025": n25, "n2024": n24,
                     "yoy": round((n26 - n25) / n25 * 100, 1) if n25 else None,
                     "tag": "底部抬升" if name in bl else ""})
    return pd.DataFrame(rows)


def _trend(yoy):
    if yoy is None:
        return "新增"
    if yoy > 100:
        return "急剧恶化"
    if yoy > 10:
        return "恶化"
    if yoy < -30:
        return "大幅改善"
    if yoy < -10:
        return "改善"
    return "基本稳定"


def build_ch5_blocks(df):
    # 5.1 2026年1-8月投诉量 Top30
    t1 = df.sort_values("n2026", ascending=False).head(30).reset_index(drop=True)
    rows1 = []
    for i, r in t1.iterrows():
        yoy = r["yoy"]
        if yoy is None:
            yc, ytxt = GREY, "—"
        else:
            yc = RED if yoy > 0 else GREEN
            ytxt = f"{yoy:+.1f}%"
        bg = "#fff3e0" if (yoy or 0) > 10 else ("#e8f5e9" if (yoy or 0) < -10 else "#fff")
        rows1.append(
            f'      <tr style="background:{bg};"><td>{i+1}</td>'
            f'<td style="text-align:left;font-weight:600;">{r["community"]}</td>'
            f'<td>{r["street"]}</td><td><strong>{r["n2026"]}</strong></td>'
            f'<td>{r["n2025"]}</td><td>{r["n2024"]}</td>'
            f'<td style="color:{yc};font-weight:700;">{ytxt}</td>'
            f'<td>{r["tag"]}</td><td>{_trend(yoy)}</td></tr>')

    # 5.2 同比恶化 Top10（2025 同期 ≥10 件，抑制小基数）
    cs = df[df["n2025"] >= 10].copy()
    cs["yoy"] = cs["yoy"].fillna(0)
    t2 = cs.sort_values("yoy", ascending=False).head(10)
    rows2 = []
    for i, (_, r) in enumerate(t2.iterrows(), 1):
        lv = "红色" if r["yoy"] >= 100 else "橙色"
        bg = "#ffebee" if lv == "红色" else "#fff3e0"
        rows2.append(
            f'      <tr style="background:{bg};"><td>{i}</td>'
            f'<td style="text-align:left;font-weight:600;">{r["community"]}</td>'
            f'<td>{r["street"]}</td><td>{r["n2026"]}件</td><td>{r["n2025"]}件</td>'
            f'<td style="color:#ff4d4f;font-weight:700;">{r["yoy"]:+.1f}%</td>'
            f'<td>{lv}</td></tr>')

    worse = cs[cs["n2025"] >= 20].sort_values("yoy", ascending=False).head(10)
    better = df[df["n2025"] >= 20].sort_values("yoy").head(5)
    return {
        "top30_table": "\n".join(rows1),
        "worse10_table": "\n".join(rows2),
        "li_worse": "\n".join(f'          <li>{r["community"]}({r["street"]}) {r["yoy"]:+.1f}%</li>'
                              for _, r in worse.iterrows()),
        "li_better": "\n".join(f'          <li>{r["community"]}({r["street"]}) {r["yoy"]:+.1f}%</li>'
                               for _, r in better.iterrows()),
        "n_worse": len(worse), "n_better": len(better),
        # 5.2 注与督导建议所需
        "w2_streets": "、".join(dict.fromkeys(t2["street"].tolist()[:4])),
        "top2": [(r["community"], r["yoy"], r["n2026"]) for _, r in t2.head(2).iterrows()],
        "best": (better.iloc[0]["community"], better.iloc[0]["yoy"]) if len(better) else ("", 0),
    }


def main():
    print("=" * 70)
    print("更新《高风险小区预警清单.html》→ 纳统小区（2026 更新版）口径")
    print("=" * 70)

    risk = json.load(open(RISK, encoding="utf-8"))
    M = build_main_blocks(risk)
    print(f"主模型：{M['n']} 个参评（红{M['r']}/橙{M['o']}/黄{M['y']}/蓝{M['b']}）")
    print(f"  红色占比最高：{M['hot_street']} {M['hot_pct']:.1f}%；次高 {M['2nd_street']} {M['2nd_pct']:.1f}%")

    df5 = load_ch5()
    C5 = build_ch5_blocks(df5)
    print(f"第五章（全量口径，纳统聚合）：{len(df5)} 个小区")

    s = open(REPORT, encoding="utf-8").read()
    orig = len(s)
    miss = []

    def rep(old, new, label):
        nonlocal s
        if old in s:
            s = s.replace(old, new, 1)
            return 1
        miss.append(label)
        return 0

    def resub(pat, new, label, count=1, flags=0):
        """new 可为字符串或 callable(match)->str"""
        nonlocal s
        s2, k = __import__("re").subn(pat, new, s, count=count, flags=flags)
        if k:
            s = s2
        else:
            miss.append(label)
        return k

    ok = 0
    # 1) 副标题（100 分起扣）
    ok += resub(r'五维风险评分模型(（[^）]*）)? · \d+个(?:纳统)?小区参评 · 红橙黄蓝四级预警',
                f'五维风险评分模型（100分起扣）· {M["n"]}个纳统小区参评 · 红橙黄蓝四级预警', "subtitle")
    # 2) 第一章正文（口径补充说明已就位，此处只同步参评数）
    ok += resub(r'(对全区)\d+(个投诉量≥10件的<b>纳统小区</b>进行系统性风险评估)',
                lambda m: m.group(1) + str(M["n"]) + m.group(2), "ch1")
    # 3) 等级卡 + 参评卡（正则允许卡片带 data-level 等附加属性，兼容第 9 项抽屉改造）
    for lab, val in (("红色预警", M["r"]), ("橙色预警", M["o"]),
                     ("黄色预警", M["y"]), ("蓝色预警", M["b"])):
        ok += resub(r'(<div class="stat-card \w+"[^>]*><div class="num">)\d+(</div><div class="label">'
                    + lab + r')',
                    lambda m, v=val: m.group(1) + str(v) + m.group(2), f"card-{lab}")
    ok += resub(r'(<div class="num" style="color:#333;">)\d+(</div><div class="label">参评小区)',
                lambda m: m.group(1) + str(M["n"]) + m.group(2), "card-参评")
    # 4) 下载链接
    ok += resub(r'下载完整清单（\d+条 Excel）',
                f'下载完整清单（{M["n"]}条 Excel）', "excel-link")
    # 5) 第三章概述
    ok += resub(r'<p>红色预警\d+个（[\d.]+%），橙色预警\d+个（[\d.]+%），两者合计占比[\d.]+%。[\s\S]*?</p>',
                f'<p>红色预警{M["r"]}个（{M["r"]/M["n"]*100:.1f}%），橙色预警{M["o"]}个'
                f'（{M["o"]/M["n"]*100:.1f}%），两者合计占比{(M["r"]+M["o"])/M["n"]*100:.1f}%。'
                f'说明全区超过八成的小区存在一定程度的风险，需要关注。'
                f'红色预警占比近三成，数量较多，建议按风险评分排序，优先处置Top50。</p>', "ch3")
    # 6) 街道表
    ok += resub(r'(<th>红色占比</th>\s*</tr>\s*</thead>\s*<tbody>)[\s\S]*?(</tbody>)',
                lambda m: m.group(1) + "\n" + M["street_table"] + "\n      " + m.group(2), "street-table")
    # 7) 红色占比最高/次高街道（幂等：值随口径自动更新）
    #    ⚠️ 前缀必须排除标签字符：原先用 `\S+?`，而 `\S` 会匹配 `<` `>` `"` `=`，
    #    导致「<p data-page-node-id="…">华泾红色预警占比…」整段被当作前缀吞掉，
    #    只替换成「华泾红色预警占比…」—— 结果 `<p` 丢掉了 `>`，该句在页面上完全不可见。
    #    改为 `[^\s<>"=/]+?` 后只吃词本身，不碰标签与属性。
    ok += resub(r'[^\s<>"=/]+?红色预警占比[\d.]+%（全区最高），[^\s<>"=/]+?街道[\d.]+%',
                f'{M["hot_street"]}红色预警占比{M["hot_pct"]:.1f}%（全区最高），'
                f'{M["2nd_street"]}街道{M["2nd_pct"]:.1f}%', "hot-2nd", count=0)
    # 8) Top30 说明（100 分起扣制：红色为最低分档 ≤30）
    ok += resub(r'数据基于[^。]*?红色预警（[^）]{0,10}）\s*\d+个。',
                f'数据基于{M["n"]}个参评纳统小区（2026年1-8月口径），'
                f'其中红色预警（≤30分）{M["r"]}个。', "top30-note")
    # 9) Top30 表
    ok += resub(r'(<th>主要问题</th><th>物业</th><th>预警</th>\s*</tr>\s*</thead>\s*<tbody>)[\s\S]*?(</tbody>)',
                lambda m: m.group(1) + "\n" + M["top_table"] + "\n      " + m.group(2), "top30-table")
    # 10) 第七章 & 页脚
    ok += resub(r'(更新)\d+(个纳统小区的风险等级)',
                lambda m: m.group(1) + str(M["n"]) + m.group(2), "ch7")
    ok += resub(r'完整\d+条预警清单见附件Excel文件',
                f'完整{M["n"]}条预警清单见附件Excel文件', "footer")
    # 11) 饼图
    _vals = [M["r"], M["o"], M["y"], M["b"]]
    _names = ["红色", "橙色", "黄色", "蓝色"]

    def _pie(m):
        body = m.group(0)
        for i, v in enumerate(_vals):
            body = __import__("re").sub(
                r"value: \d+, name: '" + _names[i],
                f"value: {v}, name: '{_names[i]}", body, count=1)
        return body
    ok += resub(r'data: \[\s*\{ value: \d+, name: \'红色[\s\S]*?\n    \],', _pie, "pie")
    # 12) 雷达图（出现 2 处：series.name 与 legend.data）
    ok += resub(r'全区\d+个小区均值', f'全区{M["n"]}个小区均值', "radar", count=0)
    # 13) 第五章口径声明
    ok += resub(r'对\d+个参评纳统小区进行近期风险评估',
                f'对{M["n"]}个参评纳统小区进行近期风险评估', "ch5-note")
    # 14) 5.1 表
    ok += resub(r'(<th>2026\(1-8月\)</th><th>2025\(1-8月\)</th><th>2024年</th><th>同比</th>'
                r'<th>标签</th><th>态势</th></tr>)[\s\S]*?(</table>)',
                lambda m: m.group(1) + "\n" + C5["top30_table"] + "\n    " + m.group(2), "ch5.1-table")
    # 15) 5.2 表
    ok += resub(r'(<th>2026\(1-8月\)</th><th>2025\(1-8月\)</th><th>同比</th><th>预警级别</th></tr>)[\s\S]*?(</table>)',
                lambda m: m.group(1) + "\n" + C5["worse10_table"] + "\n    " + m.group(2), "ch5.2-table")
    # 16) 5.3 小结
    ok += resub(r'(🔴 近期恶化重点小区（)\d+(个）</div>\s*<ul[^>]*>)[\s\S]*?(</ul>)',
                lambda m: m.group(1) + str(C5["n_worse"]) + m.group(2) + "\n"
                          + C5["li_worse"] + "\n        " + m.group(3), "headline-worse")
    ok += resub(r'(🟢 近期改善最佳小区（)\d+(个）</div>\s*<ul[^>]*>)[\s\S]*?(</ul>)',
                lambda m: m.group(1) + str(C5["n_better"]) + m.group(2) + "\n"
                          + C5["li_better"] + "\n        " + m.group(3), "headline-better")
    # 17) 5.2 脚注 + 督导建议（替换其中的旧小区与旧增幅）
    ok += resub(r'注：同比恶化Top10集中在[^<]*，与街道级恶化分析一致。',
                f'注：同比恶化Top10集中在{M["2nd_street"]}等街道（{C5["w2_streets"]}），'
                f'与街道级恶化分析一致。', "ch5.2-note")
    _t2 = C5.get("top2") or []
    if len(_t2) >= 2:
        _best = C5.get("best") or ("", 0)
        ok += resub(
            r'<strong>📌 督导建议：</strong>[\s\S]*?</div>',
            f'<strong>📌 督导建议：</strong>将近期恶化Top10小区纳入专项督导名单，特别是'
            f'<strong>{_t2[0][0]}（{_t2[0][1]:+.1f}%，绝对量{_t2[0][2]}件）和'
            f'{_t2[1][0]}（{_t2[1][1]:+.1f}%，绝对量{_t2[1][2]}件）</strong>，'
            f'绝对量大且恶化严重，应作为第一优先级。'
            f'同时建议总结{_best[0]}（{_best[1]:+.1f}%）的治理经验进行推广。</div>',
            "ch5.3-advice")
    # 18) 5.1 顶部「近期高风险预警」提示（统计 Top30 中同比正增长的个数）
    _t30 = df5.sort_values("n2026", ascending=False).head(30)
    _nup = int((_t30["yoy"].fillna(0) > 0).sum())
    # 清理历史版本遗留的重复前缀（"2026年1-8月投诉量Top30中，"可能被叠加多次）
    ok += resub(r'(?:2026年1-8月投诉量Top30中，){2,}',
                '2026年1-8月投诉量Top30中，', "headline-dedup")
    ok += resub(r'有\d+个(?:小区逆势恶化（同比正增长）|纳统小区同比正增长)，其中[\s\S]*?'
                r'恶化最严重，需立即启动专项督导。',
                f'有{_nup}个纳统小区同比正增长，其中'
                f'{"、".join(f"{c}（{y:+.1f}%）" for c, y, _ in _t2[:3])}恶化最严重，'
                f'需立即启动专项督导。', "ch5-headline")

    # ─── 19) 第 6 项整改：评分体系改为「100 分起扣」（展示分越低风险越高） ───
    ok += resub(r'模型从投诉总量、增长率、重复率、集中度、波动度五个维度对小区进行评分，'
                r'总分\s*100\s*分，分数越高代表风险越大。',
                '模型从投诉总量、增长率、重复率、集中度、波动度五个维度对小区进行评分。'
                '采用<b>100 分起扣</b>：满分 100 分，各维度按风险程度<b>扣分</b>'
                '（扣分额＝该维度风险程度 × 权重），<b>得分越低代表风险越高</b>'
                '（红色预警为最低分档），避免"高分即高风险"的反直觉。', "model-intro")
    ok += resub(r'对数缩放，投诉总量越大得分越高。',
                '对数缩放，投诉总量越大扣分越多。', "dim1")
    ok += resub(r'2026年1-8月 vs 2025年同期对比。正增长=问题在恶化=高风险。',
                '2026年1-8月 vs 2025年同期对比。正增长＝问题在恶化，扣分越多。', "dim2")
    ok += resub(r'同小区同类投诉≥3次的占比。反映问题长期未解决的积压程度。',
                '同小区同类投诉≥3次的占比，占比越高扣分越多。反映问题长期未解决的积压程度。', "dim3")
    ok += resub(r'主要问题类别占比越高风险越大。',
                '主要问题类别占比越高扣分越多。', "dim4")
    ok += resub(r'月度投诉量标准差/均值。波动越大=问题不稳定=潜在爆发风险。',
                '月度投诉量标准差/均值。波动越大扣分越多，反映问题不稳定、存在潜在爆发风险。', "dim5")
    # 评分区间表（红橙黄蓝 → 低分档为高风险）
    ok += resub(r'(<th>风险等级</th><th>评分区间</th>[\s\S]*?<tbody>)[\s\S]*?(</tbody>)',
                lambda m: m.group(1) + """
        <tr><td><span class="badge red">红色</span></td><td><b>≤30分</b></td><td>紧急处置，街道牵头制定"一小区一方案"</td><td>15个工作日内</td></tr>
        <tr><td><span class="badge orange">橙色</span></td><td>31-45分</td><td>重点关注，纳入月度督办清单</td><td>30个工作日内</td></tr>
        <tr><td><span class="badge yellow">黄色</span></td><td>46-60分</td><td>常规关注，季度复查</td><td>季度</td></tr>
        <tr><td><span class="badge blue">蓝色</span></td><td>61-75分</td><td>一般跟踪，半年复查</td><td>半年</td></tr>
      """ + m.group(2), "level-table")
    ok += resub(r'建议按风险评分排序，优先处置Top50。',
                '建议按风险得分升序（分越低风险越高）排序，优先处置 Top50。', "rank-note")
    ok += resub(r'以下\d+个小区风险评分最高，建议优先制定',
                '以下 30 个小区风险得分最低（扣分最多），建议优先制定', "top30-intro")
    ok += resub(r'<th>总分</th>', '<th>风险得分</th>', "th-total")
    ok += resub(r'将风险评分下降幅度纳入物业企业考核。',
                '将风险改善幅度（风险得分回升、预警等级下调）纳入物业企业考核。', "advice5")

    print(f"\n替换命中 {ok} 处；{orig:,} → {len(s):,} 字符")
    if miss:
        print(f"  ⚠️ 未命中 {len(miss)} 处：{miss}")

    if ARGS.dry_run:
        print("[dry-run] 未写回 HTML")
    else:
        with open(REPORT, "w", encoding="utf-8") as f:
            f.write(s)
        print(f"✔ 已更新 {REPORT}")


if __name__ == "__main__":
    main()
