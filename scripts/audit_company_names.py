# -*- coding: utf-8 -*-
"""企业名一致性校验（质量门 · 退出码 0=通过）

背景
----
上海中誉物业管理有限公司于 2026 年 8 月更名为**上海中誉城市运营服务有限公司**（同一主体）。
企业名若不归并，同一家企业会在企业排名里被拆成两行、各项计数双双少算
（2026-10-09 实测：街镇报告长桥 124→141、田林 45→56；治理追踪服务态度 6→8）。

本脚本校验三件事：

1. **主数据已归并** —— `data/merged_cleaned.pkl` 的 `property_company` 中，
   该主体只允许有一个取值（= 现用名）；原始填报值另存在 `property_company_raw`。
2. **中游产物未拆分** —— 企业级统计 JSON 中该主体只出现一个键。
3. **交付面写法正确** —— 所有报告 HTML 与交付物 Office 文件中，
   不得再以**旧名**指代该主体；唯一的例外是「更名说明」这类需要并列新旧名的句子
   （按关键词邻近豁免：更名 / 名称变更 / 原名 / 曾用名）。

另附一条通用体检：企业名内不得嵌入空白字符（换行/制表/全角空格）——
底抬名单资产曾把 58 家企业的名字写成「上海龙湖\\n物业服务有限公司」，
渲染出来会多一个空格甚至断行。
"""

import glob
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from company_alias import CURRENT_NAME, LEGACY_NAMES  # noqa: E402

import pandas as pd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

WS = re.compile(r"[\s\u3000\u00a0]")
KEYWORD = re.compile(r"更名|名称变更|原名|曾用名|变更前")

problems = []
notes = []

# 历史留档：更名之前时点产出或明确标注为历史版本的文件，允许保留当时的名称
EXEMPT_FILES = {
    # 更名之前时点（2025 及 2026 上半年）产出的过程成果报告 —— 当时登记即为旧名
    "交付物/月度分析报告",
    "交付物/年度分析报告",
    "交付物/_archive",
    # 明确标注为历史口径的中间快照
    "scripts/dedup_monthly_all_旧口径_20260928.json",
}

# 非交付物、无消费方的历史中间产物（保留原样，不计入问题）
IGNORE_FILES = {
    "scripts/root_cause_full.json",
    "scripts/complaint_trends.json",
    "scripts/h1_dedup_summary.json",
    "scripts/june_dedup_result.json",
    "scripts/dedup_july2026_hf20.json",
    "scripts/bottom_lift_analysis.json",
}


def exempt(rel: str) -> bool:
    return any(rel.startswith(e) for e in EXEMPT_FILES)


def legacy_offences(text: str):
    """返回「未处于更名说明语境中」的旧名出现位置（字符下标）。"""
    out = []
    for name in LEGACY_NAMES:
        for m in re.finditer(re.escape(name), text):
            lo, hi = max(0, m.start() - 40), m.end() + 40
            if KEYWORD.search(text[lo:hi]):
                continue          # 更名说明里并列新旧名，属正确写法
            out.append(m.start())
    return out


# ─── 1) 主数据 ───
pkl = "data/merged_cleaned.pkl"
if os.path.exists(pkl):
    df = pd.read_pickle(pkl)
    pc = df["property_company"].astype(str)
    zh = sorted(pc[pc.str.contains("中誉")].unique())
    if zh != [CURRENT_NAME]:
        problems.append(f"{pkl}：该主体取值应唯一且为现用名，实为 {zh}")
    legacy = sorted(pc[pc.isin(LEGACY_NAMES)].unique())
    if legacy:
        problems.append(f"{pkl}：property_company 仍含旧名 {legacy}")
    if "property_company_raw" not in df.columns:
        problems.append(f"{pkl}：缺少溯源列 property_company_raw")
    else:
        raw_bad = sorted(v for v in df["property_company_raw"].astype(str).unique() if WS.search(v))
        if raw_bad:
            problems.append(f"{pkl}：property_company_raw 含空白字符 {raw_bad[:3]}")
    dirty = sorted(v for v in pc.unique() if WS.search(v))
    if dirty:
        problems.append(f"{pkl}：企业名含空白字符 {dirty[:3]}")
    notes.append(f"主数据：企业名 {pc.nunique()} 个｜该主体 {int((pc == CURRENT_NAME).sum())} 件"
                 f"（原始填报 {df['property_company_raw'].astype(str).str.contains('中誉').sum()} 件）")
else:
    problems.append("找不到 data/merged_cleaned.pkl（跳过主数据校验）")


# ─── 2) 中游产物 ───
LIVE_JSON = ["scripts/street_analysis.json", "scripts/governance_tracking.json",
             "scripts/dedup_monthly_all.json", "scripts/risk_scores.json",
             "scripts/bottom_lift_2026_8m.json"]
for rel in LIVE_JSON:
    if not os.path.exists(rel):
        continue
    s = open(rel, encoding="utf-8").read()
    names = sorted(set(re.findall(r"\"[^\"]*中誉[^\"]*\"", s)))
    if len(names) > 1:
        problems.append(f"{rel}：该主体被拆成 {len(names)} 个键 → {names[:4]}")
    for n in names:
        if WS.search(n):
            problems.append(f"{rel}：企业名含空白字符 {n!r}")
    if names:
        notes.append(f"{rel}：该主体键 {names}")


# ─── 3) 交付面（HTML + 交付物 Office）───
targets = []
for rel in sorted(glob.glob("*.html")):
    targets.append(rel)
for root, _dirs, files in os.walk("交付物"):
    for f in files:
        if f.lower().endswith((".docx", ".xlsx")) and not f.startswith("~"):
            targets.append(os.path.join(root, f).replace(os.sep, "/"))

hits = 0
for rel in targets:
    if exempt(rel):
        continue
    try:
        if rel.endswith(".html"):
            text = open(rel, encoding="utf-8").read()
        else:
            with zipfile.ZipFile(rel) as z:
                text = "".join(re.sub(r"<[^>]+>", "", z.read(n).decode("utf-8", "ignore"))
                               for n in z.namelist() if n.endswith(".xml"))
    except Exception as e:                                    # pylint: disable=broad-except
        problems.append(f"{rel}：读取失败 {e}")
        continue
    bad = legacy_offences(text)
    if bad:
        hits += len(bad)
        problems.append(f"{rel}：以旧名指代该主体 {len(bad)} 处（非更名说明语境）")
    # 企业名内不得嵌空白（换行/制表/全角空格）
    seps = [t for t in re.findall(r"[^\s\"'<>]{0,12}中誉[^\s\"'<>]{0,14}", text)
            if "中誉" in t]
    seen = set()
    for t in seps:
        if any(c in t for c in ("\n", "\r", "\t", "\u3000", "\xa0")) and t not in seen:
            seen.add(t)
            problems.append(f"{rel}：该主体名中嵌有空白字符 {t!r}")

notes.append(f"交付面扫描 {len(targets)} 个文件（跳过历史留档 "
             f"{len([t for t in targets if exempt(t)])} 个），旧名指代 {hits} 处")

# ─── 4) 中间产物一般检查（非交付物，仅提示）───
for rel in sorted(glob.glob("scripts/*.json")):
    if rel.replace(os.sep, "/") == "scripts/dedup_monthly_all_旧口径_20260928.json":
        continue
    s = open(rel, encoding="utf-8").read()
    if rel in IGNORE_FILES:
        continue
    if any(n in s for n in LEGACY_NAMES):
        problems.append(f"{rel}：仍含旧名（若非历史快照需重跑其生成脚本）")


print("=" * 64)
print("企业名一致性校验")
print("=" * 64)
for n in notes:
    print("  ·", n)
print()
if problems:
    print(f"❌ 发现 {len(problems)} 项问题：")
    for p in problems:
        print("   -", p)
    sys.exit(1)
print(f"✅ 全部通过（交付面旧名指代 0 处；主数据与中游产物均为单一主体）")
sys.exit(0)
