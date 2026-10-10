#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全站数字对账（验收工具 · v1.5 / 2026-10-10）

用途
----
《网页版整改清单（技术方执行版）》第八节「全站数字对账规程」的配套脚本。
整改完成后跑一次，确认**同一指标在全站所有出现位置取值完全相同**。

版本
----
v1.1  首版：16 项基准值 + 反例表 + 结构化冲突检查
v1.2  并入第二批 3 条口径决策：
      · 决策 7 —— 湖南街道投诉密度（2026-10-10 分母口径变更后为 49.0；原 50.7）
      · 决策 8 —— 同比删 2024（新增 6 条反例：三年同图 / 较2024年 / 对比2024年(治理前) /
        2024年为基期 / 对比表头「2024全年」/ 数据数组 cat2024·y24）
      · 决策 9 —— 治理追踪门槛不可简化（COMBOS note 补入敏感性实测）
      ⚠️ 「数据周期声明 2024年1月—2026年8月」与「入榜门槛 min_2024」属**保留项**，
         相关正则均带上下文约束，不使用裸「2024」。
v1.3  并入「风险评估报告改按纳统小区统计」口径变更（2026-09-28）：
      · 基准改为 —— 纳统小区总数 993、参评基数 772、红 254 / 橙 386 / 黄 108 / 蓝 24、
        治理追踪 390；旧值 799 / 236 / 426 / 112 / 394 / 635 进反例
      · 「纳统小区总数」正则加限定词（共/为/计/达 或后接 档案/名单/库），
        避免把「772个纳统小区参评」这类**参评基数**误判为总数
      · 「红色预警数量」正则收紧（数字须紧跟「红色预警[小区]（阈值）」），
        排除 ECharts 图例「Top30红色预警小区均值 / 全区772个小区均值」
      · 新增 `BANNED_NOT_NEAR` 上下文豁免：994 在 community_linked_data.pkl 语境下
        是**正确**的户数档案条数，不再计入反例
v1.4  并入「全站统一到 993」口径变更（2026-09-28）：
      · 关联库 `data/community_linked_data.pkl` 按《纳统小区 (2026 更新版)》**独立重建**
        为 993 行 × 45 字段（`scripts/build_linked_data.py`；旧库备份
        `community_linked_data_20260903_994.pkl`），电梯 / 修缮 / 底部抬升 / 热线四条
        匹配链路全部重跑 —— 故 **994 不再有任何正确用法**
      · `BANNED_NOT_NEAR` **清空**（原为 994 在 pkl 语境下的豁免）；
        反例「纳统档案旧版 994」维持全站零残留口径，仅《版本更新记录》经 _CHANGELOG 豁免
      · 基准项 19 项不变：993 / 968 / 772 / 254 / 386 / 108 / 24 / 390 / 84 / 78
        在 993 口径下逐一复核，均无需调整
      · 实测：反例残留 270 处（**994 类已清零**）、关键词-数值冲突 0 处
v1.5  并入「街镇密度分母统一 + 第 9 章时间过滤修正」口径变更（2026-10-10）：
      · 密度分母由「只计本期有投诉小区」（全区 507,982 户）改为**全部纳统小区**
        （全区 **518,389 户**）→ 湖南街道密度 50.7 → **49.0**；推翻整改清单原第 2-C 项
      · 第 9 章《1-8月工单综合分析与目标测算》街镇口径 13,627 → **13,719**
        （原为 `<= '2026-08-31'` 漏掉 8/31 带时点 92 条所致），与第 8 章街镇报告一致
      · 新增 BASE / COMBOS 项「密度分母（全区户数）」= 518,389；
        「湖南街道投诉密度」BASE/COMBOS 改 49.0，BANNED 新增 50 / 50.7 / 48.9 三种旧写法

用法
----
    cd 项目根目录
    python3 scripts/audit_consistency.py             # 扫根目录 HTML（默认）
    python3 scripts/audit_consistency.py --docx      # 额外扫 过程成果文档/*.docx
    python3 scripts/audit_consistency.py --no-write  # 只打印，不落盘报告
    python3 scripts/audit_consistency.py --detail    # 打印全部明细（默认只打前 25 条）

退出码
------
    0 = 通过（无反例残留、无关键词-数值冲突）
    1 = 不通过（存在不一致，详见报告）

两类检查
--------
① 反例残留（BANNED）    —— 已知的旧口径数字 / 旧表述，要求全站零命中；
② 关键词-数值冲突（COMBOS）—— 「指标关键词 + 邻近数字」自动提取，与基准值比对，
   用于发现**未预料的**第二种取值（例如漏改的 82 个底部抬升小区）。

设计取舍（避免误报）
--------------------
· 关键词与数字的间隔 ≤5 个非数字字符（正常表述「参评小区 799 个」间隔为 1）；
· 取值至少 2 位，自动排除 19xx / 20xx 年份；
· 自动排除「10 个维度」「849 户」「2,354 件」这类带非计数单位的数字；
· 「智能体」类反例按文件汇总（整页下架，无需逐处列）。

基准值集中在 BASE / BANNED / COMBOS 三张表；项目组若调整口径，
先改本脚本的表，再同步《整改清单》第八节，保证两处口径一致。
本脚本**只读扫描**，不修改任何报告。
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 整改清单自身含反例词表（用于说明），参与扫描会自我命中，故排除
EXCLUDE_FILES = {"网页版整改清单（技术方执行版）.html"}
EXCLUDE_SUFFIX = (".bak", "~")

DOCX_DIRS = ["过程成果文档", "文档", "报告", "成果文档"]


# ============================================================
# 一、基准值（信息性分布统计 + 冲突判定的对照系）
# ============================================================
BASE = OrderedDict([
    ("2026年1-8月投诉总量", ("13,726", r"(?<![\d,])13,?726(?![\d,])")),
    ("1-8月判定重复工单", ("4,908", r"(?<![\d,])4,?908(?![\d,])")),
    ("1-8月整体去重率", ("35.8%", r"35\.8\s*%")),
    ("时间口径「1-8月」", ("1-8月", r"1\s*[-—至~]\s*8\s*月")),
    # 2026-09-28 口径变更：风险评估报告改按《纳统小区 (2026 更新版)》统计
    ("纳统小区总数", ("993", r"(?<!\d)993(?!\d)")),
    ("有热线记录小区", ("968", r"(?<!\d)968(?!\d)")),
    ("底部抬升重点小区", ("84", r"(?<!\d)84(?!\d)")),
    ("底部抬升可匹配小区", ("78", r"(?<!\d)78(?!\d)")),
    ("高风险预警参评基数", ("772", r"(?<!\d)772(?!\d)")),
    ("红色预警", ("254", r"(?<!\d)254(?!\d)")),
    ("橙色预警", ("386", r"(?<!\d)386(?!\d)")),
    ("黄色预警", ("108", r"(?<!\d)108(?!\d)")),
    ("蓝色预警", ("24 个", r"(?<!\d)24\s*个")),
    ("治理追踪小区数", ("390", r"(?<!\d)390(?!\d)")),
    ("全区投诉降幅", ("-13.1%", r"13\.1\s*%")),
    ("底部抬升小区降幅", ("-16.9%", r"16\.9\s*%")),
    ("华泾红色预警占比", ("47.6%", r"47\.6\s*%")),
    # 2026-10-10 口径变更：密度分母统一为**全部纳统小区**户数（旧口径「只计本期有
    # 投诉小区」全区 507,982 户已废弃）→ 湖南街道密度由 50.7 变为 49.0
    ("密度分母（全区户数）", ("518,389", r"(?<![\d,])518,?389(?![\d,])")),
    ("湖南街道投诉密度", ("49.0", r"(?<!\d)49\.0(?!\d)")),
])


# ============================================================
# 二、反例残留（label, 正则, 应改为, 是否按文件汇总）
# ============================================================
BANNED = [
    ("旧时间口径「1-6月」", r"1\s*[-—至~]\s*6\s*月",
     "已定统一为「2026年1-8月」", False),
    ("旧时间口径「上半年」", r"(?:202\d\s*年\s*)?上半年(?:数据|统计|分析|投诉|工单|口径)",
     "已定统一为「2026年1-8月」", False),
    ("旧去重分子 9,239", r"(?<![\d,])9,?239(?![\d,])", "已定统一为 4,908", False),
    ("旧去重分子 3,746", r"(?<![\d,])3,?746(?![\d,])", "已定统一为 4,908", False),
    ("旧去重分子 9,387", r"(?<![\d,])9,?387(?![\d,])", "已定统一为 4,908", False),
    ("旧去重分子 4,217", r"(?<![\d,])4,?217(?![\d,])", "已定统一为 4,908", False),
    ("旧去重分子 4,753", r"(?<![\d,])4,?753(?![\d,])", "已定统一为 4,908", False),
    ("旧去重率 40.5%", r"40\.5\s*%", "已定统一为 35.8%", False),
    ("旧去重率 44.9%", r"44\.9\s*%", "已定统一为 35.8%", False),
    ("旧去重率 34.6%", r"(?:去重率|重复(?:投诉)?(?:率|占比))[^0-9]{0,8}34\.6\s*%|34\.6\s*%[^。；\n]{0,10}(?:的?重复|去重)",
     "已定统一为 35.8%（注意：同比增幅 34.6% 属正常，不在本项）", False),
    ("预警旧基数 620", r"(?<!\d)620\s*个", "已定统一为 772 个", False),
    ("预警旧基数 628", r"(?<!\d)628\s*个", "已定统一为 772 个", False),
    # 2026-09-28 口径变更后的旧值（风险评估类报告改按《纳统小区 (2026 更新版)》统计）
    ("预警旧参评基数 799", r"(?<!\d)799\s*(?:个|条)",
     "已改为 772（仅纳统名单内 + 按纳统小区聚合 + 2026年1-8月）", False),
    ("旧红色预警数 236", r"红色预警[^。；\n]{0,8}(?<!\d)236\s*个",
     "已改为 254（≥60分）", False),
    ("旧橙色预警数 426", r"橙色预警[^。；\n]{0,8}(?<!\d)426\s*个",
     "已改为 386", False),
    ("旧治理追踪数 394", r"(?<!\d)394\s*个",
     "已改为 390（仅纳统名单内 + 按纳统小区聚合）", False),
    ("纳统档案旧版 994", r"(?<![\d,])994(?![\d,.]|ms)",
     "全站已统一为 993（《纳统小区 (2026 更新版)》）；994 是旧版关联库条数，"
     "含 community_linked_data.pkl 语境在内均须改 993", False),
    ("红色阈值写错「≥80分」", r"[≥>=]{1,2}\s*80\s*分", "红色阈值应为 ≥60 分", False),
    ("底部抬升旧值 23 个",
     r"底部抬升[^。，；\n]{0,12}?(?<!\d)23\s*个|(?<!\d)23\s*个[^。，；\n]{0,10}?底部抬升",
     "已定统一为 84 个", False),
    ("华泾占比错值 0.0%", r"华泾[^。；\n]{0,24}?(?<![\d.])0\.0\s*%", "应为 47.6%", False),
    ("华泾占比旧值 57.1%", r"华泾[^。；\n]{0,24}?(?<![\d.])57\.1\s*%",
     "已改为 47.6%（993 口径下华泾红 10/21；57.1% 系旧口径 12/21）", False),
    ("治理追踪旧值 635 个", r"(?<!\d)635\s*个",
     "635 为旧口径；治理追踪已改为 390（仅纳统名单内 + 按纳统小区聚合）", False),
    # --- v1.2 新增：决策 8「同比删 2024」；v1.5 更新：决策 7「湖南路密度 49.0」 ---
    # 注意：数据周期声明「2024年1月—2026年8月」与治理追踪入榜门槛 min_2024 属保留项，
    # 故下列正则均带上下文约束，不使用裸「2024」。
    ("同比三年同图「2024 vs 2025」", r"2024\s*vs\s*2025",
     "已定同比只保留 2025 / 2026 两年", False),
    ("同比叙述「较 2024 年」", r"(?:较|与|比|vs)\s*2024\s*年",
     "已定删除以 2024 为基期的同比表述", False),
    ("治理闭环「对比 2024 年」", r"对比\s*2024\s*年",
     "已定改为「2025 年（治理中）→ 2026 年 1-8 月（治理后）」", False),
    ("叙述「2024 年为基期」", r"2024\s*年为基期",
     "已定删除 2024 基期叙述", False),
    ("对比表头「2024 全年」", r"(?<![\d.])2024\s*全年(?!\s*[≥>=＞＜])",
     "已定删除 2024 展示列（治理追踪入榜门槛「2024全年≥5件」属保留项，已用负向断言排除）", False),
    ("展示层「2024 年」引用", r"(?<![\d.])2024\s*年(?!\s*[1-9]\s*月)",
     "已定删除 2024 展示（表头/系列名/卡片）；"
     "数据周期声明「2024年1月—2026年8月」与月份引用属保留项，本项已排除月份形态，"
     "但「2024年9月达到峰值」等月份叙述需人工清理", False),
    ("2024 同比数据数组", r"(?:cat2024|data2024|n2024|s2024|d2024|y24)(?!\d)",
     "已定删除 2024 同比数据数组", False),
    ("湖南路密度旧值（50 / 50.7 / 48.9）", r"湖南[^。；\n]{0,16}?(?<![\d.])(?:48\.9|50(?:\.0|\.7)?)\s*件/千户",
     "密度分母已统一为全部纳统小区（518,389 户），湖南路应为 49.0 件/千户", False),
    ("旧密度分母 507,982 户", r"(?<![\d,])507,?982(?![\d,])",
     "已改为全部纳统小区 518,389 户", False),
    ("第 9 章旧街镇口径 13,627", r"(?<![\d,])13,?627(?![\d,])",
     "系「<= 2026-08-31」漏计 8/31 带时点 92 件所得；街镇明细合计应为 13,719 件", False),
    ("智能体入口残留", r"智能体|AI\s*助手|大模型",
     "全站隐藏智能体功能（整页下架即可，按文件汇总）", True),
]

# 反例的上下文豁免（按 label 配置）：
# 同一数字在不同事实下可能都正确，用邻近词把它们区分开，避免误报。
#
# 2026-09-28 起**已清空**：原先 994 在 community_linked_data.pkl 语境下是
# 「户数档案的真实条数」（正确表述），故予豁免。自关联库按《纳统小区 (2026 更新版)》
# 重建为 993 行后，**全站不再有任何 994 的正确用法**，994 一律计为反例
# （仅《版本更新记录》的历史条目经 _CHANGELOG 豁免）。
BANNED_NOT_NEAR: dict = {}
# 反例的文件豁免（按 label 配置）
# 《版本更新记录》是**变更日志**，其职责就是记录「旧值 → 新值」，
# 因此凡属「引用旧值」性质的反例（620/628/799/236/426/394/994/635）在该文件中
# 出现属**正确用法**，予以豁免 —— 与《整改清单》因含反例词表而被整体排除同理。
_CHANGELOG = {"版本更新记录.html"}
# 《街镇专项分析报告》天然是**分街镇**口径：每个街镇各有一套子集数值。
# 2026-09-28 实测：凌云路「重复投诉率 34.6%」（310/897）、湖南路「44.9%」（403/897）
# 是**该街镇的真实值**，与旧的全区口径 34.6% / 44.9% 数值巧合，**不是残留**。
# 街镇合计 4,905 / 13,719 = 35.8%，与全区 4,908 / 13,726 = 35.8% 一致，见
# `scripts/street_analysis.json` → `streets[街镇].dup`（由 `build_street_dataset.py` 生成）。
_SC = ["街镇专项分析报告.html"]
BANNED_FILES_EXCLUDE = {
    lbl: _CHANGELOG for lbl in (
        "预警旧基数 620", "预警旧基数 628", "预警旧参评基数 799",
        "旧红色预警数 236", "旧橙色预警数 426", "旧治理追踪数 394",
        "纳统档案旧版 994", "治理追踪旧值 635 个",
        # 2026-10-10 新增：密度分母口径变更，历史条目须保留旧值叙述
        "湖南路密度旧值（50 / 50.7 / 48.9）", "旧密度分母 507,982 户",
        "第 9 章旧街镇口径 13,627",
    )
}
# 去重率反例在街镇报告内一律排除（该文件内出现的百分比均为街镇级子集值）
for _lbl in ("旧去重率 40.5%", "旧去重率 44.9%", "旧去重率 34.6%"):
    BANNED_FILES_EXCLUDE[_lbl] = _CHANGELOG | set(_SC)


# ============================================================
# 三、关键词-数值冲突（结构化取值正则）
#    每条规则：pats 为带 (?P<v>…) 捕获组的正则；命中值若不在 {base} ∪ allow 中即报冲突。
#    files_exclude：该报告天然是「分街镇」口径（每街镇各有一份子集数值），不参与全区对账。
#    说明：这里用专用正则而非「关键词+邻近数字」通用匹配 —— 后者会把
#    「参评小区数 55」「红色预警小区 16」（各街镇子集）误判为冲突。
#    _SC 已在第二节（反例表）前定义，此处不再重复。
# ============================================================

COMBOS = [
    dict(label="纳统小区总数", base="993", allow=[],
         pats=[r"纳统小区\s*(?:总数)?\s*(?:共|为|计|达)\s*(?P<v>\d{3,4})\s*个",
               r"(?<![\d,])(?P<v>\d{3,4})\s*个纳统小区(?:档案|名单|库)"],
         files_exclude=_SC,
         note="993 =《纳统小区 (2026 更新版)》档案条数；968 为其中已有热线记录的小区数。"
              "⚠️「772个纳统小区参评」「更新772个纳统小区」是**参评基数**表述（772 见下一项），"
              "非总数，故第一式要求紧跟「共/为/计/达」，第二式要求后接「档案/名单/库」"),
    dict(label="有热线记录小区", base="968", allow=["993"],
         pats=[r"其中\s*(?P<v>\d{3,4})\s*个有(?:热线)?投诉记录",
               r"有(?:热线)?投诉记录的(?:纳统)?小区[^0-9]{0,4}(?P<v>\d{3,4})"],
         files_exclude=_SC,
         note="968 须与 993 同现并注明口径（覆盖率 97.5%）"),
    dict(label="底部抬升重点小区", base="84", allow=["78", "82", "23"],
         pats=[r"底部抬升(?:重点)?小区\s*(?:共|为|计)?\s*(?<![\d,])(?P<v>\d{1,3})(?![\d.])",
               r"(?<![\d,])(?P<v>\d{1,3})\s*个(?:党建引领)?(?:重点|底部抬升)小区"],
         files_exclude=_SC,
         note="84 为名单总数；78 为可匹配数；23/82 已在反例或核查项中"),
    dict(label="底部抬升可匹配小区", base="78", allow=[],
         pats=[r"匹配成功\s*(?P<v>\d{1,3})\s*个"],
         files_exclude=_SC,
         note="78 仅作投诉量统计的分母"),
    dict(label="高风险预警参评基数", base="772", allow=[],
         pats=[r"对全区\s*(?P<v>\d{2,4})\s*个[^。；\n]{0,14}?(?:进行|开展)[^。；\n]{0,8}?评估",
               r"全区\s*(?:共)?\s*(?P<v>\d{2,4})\s*个[^。；\n]{0,12}?参评小区",
               r"参评小区\s*(?P<v>\d{2,4})\s*个"],
         files_exclude=_SC,
         note="772 = 红 254 + 橙 386 + 黄 108 + 蓝 24"
              "（仅纳统名单内小区，按纳统小区聚合，2026年1-8月）"),
    dict(label="红色预警数量", base="254", allow=["60"],
         pats=[r"红色预警(?:小区)?(?:\s*[（(][^）)]{0,12}[）)])?\s*(?:共|达|为|数量)?\s*"
               r"(?P<v>\d{2,3})\s*个(?!小区)"],
         files_exclude=_SC,
         note="红色预警（≥60分）254 个。正则要求数字紧跟「红色预警[小区]（阈值）」，"
              "以排除 ECharts 图例「Top30红色预警小区均值 / 全区772个小区均值」这类邻近数字"),
    dict(label="治理追踪小区数", base="390", allow=[],
         pats=[r"(?<![\d,])(?P<v>\d{2,4})\s*个小区[^。；\n]{0,10}?追踪",
               r"追踪小区(?:总数|数)?[^0-9]{0,6}(?P<v>\d{2,4})"],
         files_exclude=_SC,
         not_near=["重点小区", "底部抬升", "党建引领"],
         note="门槛：三年合计≥15件 ∧ 2024全年≥5件 ∧ 2025年1-8月≥10件；"
              "实测删 min_2024 → 414、仅留 25h≥10 → 415，故门槛不可简化。"
              "390 为「仅纳统名单内 + 按纳统小区聚合」口径（旧口径 394）"),
    dict(label="密度分母（全区户数）", base="518,389", allow=[],
         pats=[r"全区(?:合计)?\s*(?P<v>[\d,]{6,7})\s*户",
               r"(?P<v>[\d,]{6,7})\s*户[^。；\n]{0,12}?(?:纳统|全量|全部)"],
         files_exclude=[],
         note="密度分母＝**全部** 993 个纳统小区户数，全区合计 518,389 户（工单主数据与 "
              "SQLite 库均无户数字段）。旧口径「只计本期有投诉小区」全区 507,982 户已废弃；"
              "两者差异见反例「旧密度分母 507,982 户」"),
    dict(label="湖南街道投诉密度", base="49.0", allow=[],
         pats=[r"湖南[路街][^。；\n]{0,16}?(?P<v>\d{2}(?:\.\d)?)\s*件/千户"],
         files_exclude=list(_CHANGELOG),
         note="49.0 件/千户（全区最高）；分母为全部纳统小区 18,299 户（897 ÷ 18,299 × 1000）。"
              "旧口径 50.7（分母 17,675 户＝本期有投诉小区）已废弃，进反例。"
              "2026-10-10 起《街镇专项分析报告》与第 9 章同口径，故**不再排除**该文件"),
    dict(label="2026年1-8月投诉总量", base="13,726", allow=[],
         pats=[r"(?:投诉|受理)(?:工单)?总量[^0-9]{0,6}(?P<v>[\d,]{4,6})"],
         files_exclude=_SC,
         note="全站唯一值"),
    dict(label="1-8月判定重复工单", base="4,908", allow=["5,170"],
         pats=[r"判定重复[^0-9]{0,6}(?P<v>[\d,]{4,6})",
               r"重复(?:投诉)?工单(?:总量)?[^0-9]{0,6}(?P<v>[\d,]{4,6})"],
         files_exclude=_SC,
         note="全站唯一值"),
    # 2026-09-29 新增：此前「全区投诉降幅」只在 BASE 里作信息性统计、未进冲突判定，
    # 导致《街镇专项分析报告》把 13 街镇口径的 -12.6% 标成「全区」长期漏检。
    dict(label="全区投诉降幅", base="-13.1%", allow=["-19.9%", "-16.9%"],
         pats=[r"[（(]全区\s*(?P<v>[-−]?\d{1,2}(?:\.\d)?)\s*%[）)]",
               r"全区[^。；，\n]{0,30}?投诉量[^。；\n]{0,30}?同比[^0-9]{0,4}"
               r"(?P<v>[-−]?\d{1,2}(?:\.\d)?)\s*%",
               # KPI 卡的「同比 -13.1%，减少 N 件」（同比与数值同行，与投诉量不在同一行）
               r"同比\s*(?P<v>[-−]1\d(?:\.\d)?)\s*%[^。；\n]{0,6}(?:减少|下降)"],
         files_exclude=_SC,
         note="全区 = 13,726 ÷ 15,798 = -13.1%（分子分母均含「归属为空」工单，"
              "2025 年同期归属为空 109 条）；13 街镇合计口径为 -12.6%，不得标为「全区」。"
              "allow 里的 -19.9% 是全区 2025 全年同比、-16.9% 是底抬小区同比，属其他口径。"
              "⚠ 对账按行匹配，KPI 的「投诉量」与「同比」若被标签分行，仅第三式可覆盖"),
]

# 数字前后自动排除的计量词（后接这些词说明该数字不是小区/工单计数）
UNIT_AFTER = r"(?:户|元|件|台|人|年|月|日|%|㎡|平方米|维|类|个(?:维度|方面|要素|业务|类别))"
YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")


# ============================================================
# 工具函数
# ============================================================
_TAG_RE = re.compile(r"<[^>]{0,400}>")
_SPACE_RE = re.compile(r"[ \t\u3000]+")


def strip_tags(s: str) -> str:
    """剥离 HTML 标签取上下文（保留 script 内数据，避免漏掉图表里的旧值）。"""
    s = _TAG_RE.sub(" ", s)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        s = s.replace(a, b)
    return _SPACE_RE.sub(" ", s)


def load_html_lines() -> dict:
    out = {}
    for p in sorted(ROOT.glob("*.html")):
        if p.name in EXCLUDE_FILES or p.name.endswith(EXCLUDE_SUFFIX):
            continue
        try:
            out[p.name] = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError as e:                                   # pragma: no cover
            print(f"  ! 读取失败 {p.name}: {e}", file=sys.stderr)
    return out


def load_docx_lines() -> dict:
    out = {}
    for d in DOCX_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.docx")):
            if p.name.startswith("~$"):
                continue
            try:
                with zipfile.ZipFile(p) as z:
                    xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
            except Exception:
                continue
            txt = re.sub(r"</w:p>", "\n", xml)
            out[f"{d}/{p.name}"] = strip_tags(txt).splitlines()
    return out


def snippet(line: str, start: int, end: int, width: int = 44) -> str:
    a, b = max(0, start - width), min(len(line), end + width)
    return ("…" if a else "") + line[a:b].strip() + ("…" if b < len(line) else "")


def _num_ok(val: str, tail: str) -> bool:
    """数字是否可视为「计数取值」。tail = 数字之后的若干字符。"""
    digits = val.replace(",", "")
    if len(digits) < 2:                 # 单位数多为「9类数据」之类
        return False
    if YEAR_RE.match(digits):           # 排除年份
        return False
    if re.match(r"\s*" + UNIT_AFTER, tail):
        return False
    return True


def combo_scan(text: str, rule: dict) -> list:
    """按规则的结构化正则提取取值，返回 [(实际值, 命中片段), ...]（已剔除基准值/允许值）。"""
    ok = {str(rule["base"]).replace(",", "")} | {str(a).replace(",", "") for a in rule["allow"]}
    not_near = rule.get("not_near") or ()
    hits, seen = [], set()
    for pat in rule["pats"]:
        for m in re.finditer(pat, text):
            val = m.group("v")
            after = text[m.end(): m.end() + 4]
            if not _num_ok(val, after):          # 排除年份与「849户」类计量
                continue
            if val.replace(",", "") in ok:
                continue
            if not_near and any(w in text[max(0, m.start() - 30): m.end() + 10] for w in not_near):
                continue
            key = (val, m.start() // 12)
            if key in seen:
                continue
            seen.add(key)
            hits.append((val, snippet(text, m.start(), m.end())))
    return hits


# ============================================================
# 主流程
# ============================================================
def run(files: dict, check_banned: bool, check_combo: bool):
    banned_detail, banned_agg = [], defaultdict(Counter)
    combo_hits = []
    base_stat = OrderedDict((k, Counter()) for k in BASE)

    for fname, lines in files.items():
        for ln, raw in enumerate(lines, 1):
            text = strip_tags(raw)
            if not text.strip():
                continue

            if check_banned:
                for label, pat, hint, agg in BANNED:
                    if fname in BANNED_FILES_EXCLUDE.get(label, ()):
                        continue
                    exempt = BANNED_NOT_NEAR.get(label, ())
                    n = 0
                    for m in re.finditer(pat, text):
                        if exempt and any(
                                w in text[max(0, m.start() - 60): m.end() + 30] for w in exempt):
                            continue
                        n += 1
                        if agg:
                            continue
                        banned_detail.append((label, fname, ln,
                                              snippet(text, m.start(), m.end()), hint))
                    if agg and n:
                        banned_agg[label][fname] += n

            if check_combo:
                for rule in COMBOS:
                    if fname in rule["files_exclude"]:     # 分街镇口径报告不参与全区对账
                        continue
                    for val, snip in combo_scan(text, rule):
                        combo_hits.append((rule["label"], rule["base"], val,
                                           fname, ln, snip))

            for label, (bval, bpat) in BASE.items():
                c = len(re.findall(bpat, text))
                if c:
                    base_stat[label][fname] += c

    return banned_detail, banned_agg, combo_hits, base_stat


def total_banned(banned_detail, banned_agg) -> int:
    return len(banned_detail) + sum(sum(c.values()) for c in banned_agg.values())


def build_report(files, banned_detail, banned_agg, combo_hits, base_stat, extra_docx) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    nb = total_banned(banned_detail, banned_agg)
    ok = nb == 0 and not combo_hits
    L, A = [], None
    L.append("# 徐汇项目 · 全站数字对账报告\n")
    L.append(f"- 生成时间：{now}")
    L.append(f"- 扫描范围：{len(files)} 个文件（根目录 HTML{'+ 过程成果文档 docx' if extra_docx else ''}）")
    L.append("- 脚本：`scripts/audit_consistency.py`")
    L.append(f"- **对账结论：{'✅ 通过' if ok else '❌ 不通过'}**\n")
    if ok:
        L.append("> 全部基准指标取值唯一，反例零命中。\n")
    else:
        L.append(f"> 反例残留 **{nb}** 处；关键词-数值冲突 **{len(combo_hits)}** 处。")
        L.append("> 修改后请重跑本脚本，直至两类均为 0。\n")

    # 一、反例残留
    L.append("---\n")
    L.append(f"## 一、反例残留（必须零命中） — {nb} 处\n")
    if nb == 0:
        L.append("✅ 零命中。\n")
    else:
        by = Counter(h[0] for h in banned_detail)
        for lbl, c in banned_agg.items():
            by[lbl] += sum(c.values())
        hints = {h[0]: h[4] for h in banned_detail}
        for lbl, c in banned_agg.items():
            hints.setdefault(lbl, "全站隐藏智能体功能（按文件汇总）")
        L.append("| 反例 | 处数 | 应改为 |")
        L.append("|---|---|---|")
        for k, v in by.most_common():
            L.append(f"| {k} | {v} | {hints.get(k, '')} |")
        L.append("")
        if banned_agg:
            L.append("### 1.1 按文件汇总（整页下架类）\n")
            L.append("| 反例 | 文件 | 命中数 |")
            L.append("|---|---|---|")
            for lbl, c in banned_agg.items():
                for f, n in c.most_common():
                    L.append(f"| {lbl} | {f} | {n} |")
            L.append("")
        if banned_detail:
            L.append("### 1.2 逐处明细\n")
            L.append("| 反例 | 文件 | 行 | 片段 |")
            L.append("|---|---|---|---|")
            for label, fname, ln, snip, _h in banned_detail[:500]:
                L.append(f"| {label} | {fname} | {ln} | `{snip}` |")
            if len(banned_detail) > 500:
                L.append(f"| … | … | … | 另有 {len(banned_detail)-500} 处 |")
            L.append("")

    # 二、关键词-数值冲突
    L.append("---\n")
    L.append(f"## 二、关键词-数值冲突（同一指标出现第二种取值） — {len(combo_hits)} 处\n")
    if not combo_hits:
        L.append("✅ 未发现冲突。\n")
    else:
        # 按「指标 + 实际值」聚合，便于判断是笔误还是系统性口径差异
        agg = defaultdict(list)
        for label, base, val, fname, ln, snip in combo_hits:
            agg[(label, base, val)].append((fname, ln, snip))
        L.append("| 指标 | 基准值 | 实际值 | 处数 | 涉及文件 |")
        L.append("|---|---|---|---|---|")
        for (label, base, val), items in sorted(agg.items(), key=lambda x: -len(x[1])):
            fs = "、".join(sorted({i[0] for i in items}))
            L.append(f"| {label} | **{base}** | {val} | {len(items)} | {fs} |")
        L.append("")
        L.append("<details><summary>逐处明细</summary>\n")
        L.append("| 指标 | 基准 | 实际 | 文件 | 行 | 片段 |")
        L.append("|---|---|---|---|---|---|")
        for label, base, val, fname, ln, snip in combo_hits[:500]:
            L.append(f"| {label} | {base} | {val} | {fname} | {ln} | `{snip}` |")
        if len(combo_hits) > 500:
            L.append(f"| … | … | … | … | … | 另有 {len(combo_hits)-500} 处 |")
        L.append("\n</details>\n")

    # 三、基准值分布
    L.append("---\n")
    L.append("## 三、基准值分布（信息性；「未出现」不代表错误）\n")
    L.append("| 指标 | 基准值 | 命中文件数 | 命中次数 | 出现文件 |")
    L.append("|---|---|---|---|---|")
    for label, (bval, _p) in BASE.items():
        c = base_stat[label]
        files_txt = "、".join(f"{k}({v})" for k, v in c.most_common()) or "—未出现—"
        L.append(f"| {label} | {bval} | {len(c)} | {sum(c.values())} | {files_txt} |")
    L.append("")

    L.append("---\n")
    L.append("### 通过标准（三项同时满足）\n")
    L.append("1. **唯一性**：每项指标在全站所有出现位置的取值，均等于基准值。")
    L.append("2. **反例零命中**：第一节清单为空。")
    L.append("3. **口径完整性**：凡收窄样本处（968 / 78 / 四级分级）均有「参与统计口径」说明。\n")
    L.append("> 基准表定义在 `scripts/audit_consistency.py` 顶部（`BASE` / `BANNED` / `COMBOS`），")
    L.append("> 与《网页版整改清单（技术方执行版）》第八节同源；调整口径请两处同步。\n")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="全站数字对账（验收工具）")
    ap.add_argument("--docx", action="store_true", help="额外扫描 过程成果文档/*.docx")
    ap.add_argument("--no-write", action="store_true", help="只打印，不写报告文件")
    ap.add_argument("--only-banned", action="store_true", help="只检查反例残留")
    ap.add_argument("--only-combo", action="store_true", help="只检查关键词-数值冲突")
    ap.add_argument("--detail", action="store_true", help="打印全部明细")
    args = ap.parse_args()

    check_banned = not args.only_combo
    check_combo = not args.only_banned
    limit = 10 ** 6 if args.detail else 25

    files = load_html_lines()
    if args.docx:
        files.update(load_docx_lines())

    print(f"扫描 {len(files)} 个文件…")
    banned_detail, banned_agg, combo_hits, base_stat = run(files, check_banned, check_combo)
    nb = total_banned(banned_detail, banned_agg)

    print("\n" + "=" * 64)
    if nb:
        print(f"反例残留：{nb} 处")
        for label, fname, ln, snip, _h in banned_detail[:limit]:
            print(f"  · [{label}] {fname}:{ln}  {snip[:84]}")
        for label, c in banned_agg.items():
            print(f"  · [{label}] 按文件汇总：{'、'.join(f'{f}({n})' for f, n in c.most_common())}")
        if len(banned_detail) > limit:
            print(f"  … 另有 {len(banned_detail)-limit} 处，见报告")
    else:
        print("反例残留：0 处 ✅")

    if combo_hits:
        print(f"\n关键词-数值冲突：{len(combo_hits)} 处")
        agg = Counter((l, b, v) for l, b, v, _f, _n, _s in combo_hits)
        for (label, base, val), c in agg.most_common(limit):
            examples = [f"{f}:{n}" for l, b, v, f, n, _s in combo_hits if (l, b, v) == (label, base, val)][:4]
            print(f"  · [{label}] 基准 {base} ≠ 实际 {val} ×{c}  @ {'、'.join(examples)}")
    else:
        print("\n关键词-数值冲突：0 处 ✅")

    passed = nb == 0 and not combo_hits
    print("=" * 64)
    print("结论：" + ("✅ 通过" if passed else "❌ 不通过（见上方清单）"))
    print("=" * 64)

    if not args.no_write:
        out_dir = ROOT / "scripts" / "audit_reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"数字对账报告_{datetime.now():%Y%m%d_%H%M}.md"
        out.write_text(
            build_report(files, banned_detail, banned_agg, combo_hits, base_stat, args.docx),
            encoding="utf-8")
        print(f"报告已写入：{out.relative_to(ROOT)}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
