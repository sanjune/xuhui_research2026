# -*- coding: utf-8 -*-
"""
街镇维度数据集构建 — 可复现脚本
================================

从 data/merged_cleaned.pkl（66,812 条，2024.01–2026.08）出发，为 13 个街镇各构建
一套「可直接出图」的维度数据集，输出 scripts/street_analysis.json。

口径（必须与既有报告一致）：
  · 对比口径    2026年1-8月  vs  2025年1-8月（同期），不用全年基数
  · 下降贡献率  该镇减少量 ÷ 全区减少量
  · 街镇归属    主数据 street 字段（100% 覆盖），"无" 归属单列不进街镇明细
  · 重复投诉    复用 dedup_monthly.py 的四重策略，按街镇对 2026年1-8月 累计计算
  · 命名映射    主数据「华泾镇」↔ 派生资产「华泾」；外部数据「XX街道」→ 主数据名

用法：
    python scripts/build_street_dataset.py                # 全量构建
    python scripts/build_street_dataset.py --no-dedup     # 跳过去重计算（快速预览）

产出：scripts/street_analysis.json
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKL = os.path.join(ROOT, "data", "merged_cleaned.pkl")
OUT = os.path.join(ROOT, "scripts", "street_analysis.json")
SCRIPTS = os.path.join(ROOT, "scripts")
EXT = os.path.join(ROOT, "徐汇各科室业务数据")

YEAR_NOW, MONTH_NOW = 2026, 8
YEAR_PREV = 2025
YEAR_BASE = 2024

# 主数据街镇名 → 派生资产街镇名（risk_scores / governance_tracking）
DERIVED_ALIAS = {"华泾镇": "华泾"}

CATEGORIES = ["停车管理", "房屋维修", "邻里纠纷", "房屋违规使用", "业主大会/业委会",
              "消防管理", "电梯管理", "环境卫生", "公共设施", "物业收费",
              "物业服务", "违章搭建", "租赁管理", "其他"]


# ─────────────────────────── 工具 ───────────────────────────

def norm_street_external(name) -> str:
    """外部数据街镇名 → 主数据街镇名。如 凌云路街道→凌云路、天平街道→天平路。"""
    if not isinstance(name, str):
        return ""
    s = name.strip().replace("街道", "").replace("镇", "")
    if not s:
        return ""
    mapping = {"天平": "天平路", "斜土": "斜土路", "枫林": "枫林路", "湖南": "湖南路",
               "虹梅": "虹梅路", "凌云": "凌云路", "康健": "康健新村", "康健新村": "康健新村"}
    return mapping.get(s, s)


def pct(part, whole):
    if not whole:
        return 0.0
    return round(part / whole * 100, 1)


def yoy(cur, prev):
    if not prev:
        return None
    return round((cur - prev) / prev * 100, 1)


def load_data() -> pd.DataFrame:
    df = pd.read_pickle(PKL)
    df["content"] = df["content"].fillna("").astype(str).str.strip()
    df["t"] = pd.to_datetime(df["accept_time"], errors="coerce")
    return df


def period(df, year, m1=1, m2=12) -> pd.DataFrame:
    return df[(df["year"] == year) & (df["month"] >= m1) & (df["month"] <= m2)]


# ─────────────────────────── 重复投诉（按街镇） ───────────────────────────

def dedup_for_street(d: pd.DataFrame) -> dict:
    """按街镇计算重复投诉（**逐月独立去重**后汇总，与《去重方法论》《去重建议清单》口径一致）。

    说明：若把 1-8 月合并成池再跑去重，同小区同类≥3 必然命中、文本相似也会跨月误判，
    重复率会虚高到 55-76%；逐月独立去重（每月各留 1 条原件）才与已发布口径
    （2026年重复率 29%→38% 区间）可比。
    """
    sys.path.insert(0, SCRIPTS)
    import importlib.util
    spec = importlib.util.spec_from_file_location("dm", os.path.join(SCRIPTS, "dedup_monthly.py"))
    dm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dm)

    total = len(d)
    agg = {"s1": 0, "s1_groups": 0, "s2": 0, "s3": 0, "s3_groups": 0, "s4": 0, "s4_pairs": 0,
           "dup_count": 0, "high_count": 0, "mid_count": 0}
    monthly = []
    if total == 0:
        return {**agg, "total": 0, "rate": 0.0, "monthly": monthly}

    for m in range(1, MONTH_NOW + 1):
        sub = d[d["month"] == m]
        if len(sub) == 0:
            continue
        s1, s1g = dm.strategy1_exact(sub)
        s2 = dm.strategy2_keyword(sub)
        s3, s3_groups, freq, s3_f4 = dm.strategy3_frequency(sub)
        s4, s4_pairs, s4_comms, order_sim = dm.strategy4_similarity(sub)

        union = s1 | s2 | s3 | s4
        high = s1 | s2 | s3_f4
        agg["s1"] += len(s1); agg["s1_groups"] += s1g
        agg["s2"] += len(s2)
        agg["s3"] += len(s3); agg["s3_groups"] += len(s3_groups)
        agg["s4"] += len(s4); agg["s4_pairs"] += len(s4_pairs)
        agg["dup_count"] += len(union)
        agg["high_count"] += len(high)
        agg["mid_count"] += len(union - high)
        monthly.append({"month": m, "total": int(len(sub)), "dup_count": int(len(union)),
                        "rate": round(len(union) / len(sub) * 100, 1)})

    return {
        "total": int(total),
        "dup_count": int(agg["dup_count"]),
        "rate": round(agg["dup_count"] / total * 100, 1),
        "high_count": int(agg["high_count"]),
        "mid_count": int(agg["mid_count"]),
        "s1": agg["s1"], "s1_groups": agg["s1_groups"],
        "s2": agg["s2"],
        "s3": agg["s3"], "s3_groups": agg["s3_groups"],
        "s4": agg["s4"], "s4_pairs": agg["s4_pairs"],
        "monthly": monthly,
        "method": "逐月独立去重后汇总（同小区内容完全重复 ∪ 催办关键词 ∪ 同小区同类≥3 ∪ 文本相似≥0.6）",
    }


# ─────────────────────────── 外部数据 ───────────────────────────

def load_externals() -> dict:
    """返回 {街镇: {...}}，任一文件缺失时该维度为 None（页面自动隐藏）。"""
    out = {}
    # 电梯（含街道名称）
    try:
        e = pd.read_excel(os.path.join(EXT, "电梯基本信息.xlsx"))
        e["st"] = e["街道名称"].map(norm_street_external)
        for st, g in e.groupby("st"):
            st = norm_street_external(st)
            out.setdefault(st, {})["elevator"] = {
                "total": int(len(g)),
                "done": int((g["电梯加装状态"] == "完工").sum()),
                "building": int((g["电梯加装状态"] == "开工").sum()),
                "communities": int(g["小区名称"].nunique()),
            }
    except Exception as ex:
        print("  · 电梯数据跳过:", ex)
    # 征收（含街道名称）
    try:
        z = pd.read_excel(os.path.join(EXT, "征收.xlsx"))
        z["st"] = z["街道名称"].map(norm_street_external)
        for st, g in z.groupby("st"):
            if not st:
                continue
            out.setdefault(st, {})["expropriation"] = {
                "projects": int(g["征收基地名称"].nunique()),
                "households": int(pd.to_numeric(g["户数"], errors="coerce").fillna(0).sum()),
                "area": int(pd.to_numeric(g["总面积"], errors="coerce").fillna(0).sum()),
            }
    except Exception as ex:
        print("  · 征收数据跳过:", ex)
    # 修缮（按小区名 join 主数据街镇，命中率约 87%）
    try:
        r = pd.read_excel(os.path.join(EXT, "修缮项目.xlsx"))
        df = pd.read_pickle(PKL)
        for col in ["community_name", "street"]:
            df[col] = df[col].astype(str).str.strip()
        cmap = (df[df["community_name"].isin(["", "无", "nan"]) == False]
                .groupby("community_name")["street"].agg(lambda x: x.mode().iloc[0] if len(x.mode()) else ""))
        r["st"] = r["小区名称"].astype(str).str.strip().map(cmap)
        rr = r[r["st"].notna() & (r["st"] != "") & (r["st"] != "nan")]
        for st, g in rr.groupby("st"):
            out.setdefault(st, {})["renovation"] = {
                "projects": int(len(g)),
                "investment": round(float(pd.to_numeric(g["总投资(万元)"], errors="coerce").fillna(0).sum()), 1),
                "area": round(float(pd.to_numeric(g["建筑面积(平方米)"], errors="coerce").fillna(0).sum()), 1),
            }
    except Exception as ex:
        print("  · 修缮数据跳过:", ex)
    return out


# ─────────────────────────── 文本关键词 ───────────────────────────

STOP = set("市民 反映 诉求 要求 投诉 求助 举报 处理 尽快 相关 部门 问题 情况 来电 关于 目前 "
           "已经 一直 未 我们 他们 小区 上述 地址 因为 由于 存在 希望 对此 进行 以及 请 该 后 "
           "称 告知 表示 无法 没有 就是 这个 这样 什么 何时 为何 一直 多次 长期 至今 严重 影响 "
           "物业 管理 回复 信息 保密 工单 核实 需要 联系 确认 是否 建议 后续 单位 收到 同志 您好 "
           "感谢 满意 承办 答复 工作人员 部门 请予 予以 尽快处理 悉 经 已 将 与 处理结果 联系我".split())

# 工单模板字段 / 办理流程用语 / 泛义虚词 —— 非诉求主题，出图前必须剔除
STOP_BOILERPLATE = set("""
无需 内容 最近 编号 办结 派发 要点 给予 作为 导致 但是 一个 自己 现在 不要 该处
对方 重新 行为 使用 合理 正常 明确 同意 安排 协助 帮助 介入 解释 核查 查处 解决 居民
补充 固定 方案 生活 工作 人员 进行 存在 出现 发生 表示 认为 应该 可以 能否 如何 事项
反映 要求 希望 建议 徐汇区 上海 街道 居委会 居委 同志 先生 女士 来电 反映人 诉求人
不是 没有 还是 而且 并且 就是 这些 那些 之后 之前 目前 依然 仍旧 经常 偶尔 有时
现场 查看 检查 排查 落实 跟进 反馈 沟通 联系 通知 告知 处理中 已办 未办
对于 区内 办理 实际 不符 经过 很多 边上 无人 交办 号楼 书面 主任 情况
""".split())
STOP = STOP | STOP_BOILERPLATE

# 高频套话过滤器：出现在超过该比例的工单中，视为模板用语而非诉求主题
BOILERPLATE_DF = 0.35

# 主题词展示数量（词云）
KEYWORD_TOPN = 24


def keywords_of(d: pd.DataFrame, topn=KEYWORD_TOPN, street=None):
    """提取该街镇诉求主题词（供词云展示）。

    只取「诉求：」之后的正文（无则取全文），剔除三类非主题词：
      1) STOP / STOP_BOILERPLATE 中的停用词与工单模板用语（无需/内容/最近/编号/办结…）
      2) 本街镇自身地名（长桥/华泾…），避免地址串扰
      3) 文档频率高于 BOILERPLATE_DF 的高频套话
    """
    texts = []
    for raw in d["content"].tolist():
        s = raw or ""
        for marker in ("诉求：", "诉求:", "诉求是"):
            i = s.find(marker)
            if i >= 0:
                s = s[i + len(marker):]
                break
        texts.append(s)
    joined = " ".join(texts)
    if not joined.strip():
        return []
    # 本街镇自身地名及其简称，避免"长桥""华泾"这类地址词混入主题词
    self_terms = set()
    if street:
        self_terms.add(street)
        for suf in ("镇", "街道", "新村", "路"):
            if street.endswith(suf) and len(street) > len(suf):
                self_terms.add(street[: -len(suf)])
    try:
        import jieba
        jieba.setLogLevel(60)
        per_doc = [[w for w in jieba.lcut(t)
                    if len(w) > 1 and w not in STOP and w not in self_terms and not w.isdigit()]
                   for t in texts]
    except ImportError:
        per_doc = [[w for w in re.findall(r"[\u4e00-\u9fa5]{2,4}", t)
                    if w not in STOP and w not in self_terms]
                   for t in texts]

    n_doc = max(len(per_doc), 1)
    doc_freq, total_cnt = Counter(), Counter()
    for toks in per_doc:
        doc_freq.update(set(toks))
        total_cnt.update(toks)
    out = []
    for w, c in total_cnt.most_common():
        if c < 5:
            break
        if doc_freq[w] / n_doc > BOILERPLATE_DF:
            continue
        out.append({"word": w, "cnt": c})
        if len(out) >= topn:
            break
    return out


# ─────────────────────────── 主流程 ───────────────────────────

def build(do_dedup=True) -> dict:
    df = load_data()
    main = df[df["street"] != "无"].copy()
    streets = sorted(main["street"].unique())

    n26 = period(main, YEAR_NOW, 1, MONTH_NOW)
    n25s = period(main, YEAR_PREV, 1, MONTH_NOW)
    n24s = period(main, YEAR_BASE, 1, MONTH_NOW)
    n25f = period(main, YEAR_PREV)
    n24f = period(main, YEAR_BASE)

    na = df[df["street"] == "无"]
    unassigned = int(len(period(na, YEAR_NOW, 1, MONTH_NOW)))          # 同期口径
    unassigned_all = int(len(na))                                       # 全期（含 2024-2026）

    d26 = int(len(n26))
    d25s = int(len(n25s))
    district = {
        "n2026": d26, "n2025_same": d25s, "n2024_same": int(len(n24s)),
        "n2025_full": int(len(n25f)), "n2024_full": int(len(n24f)),
        "yoy": yoy(d26, d25s),
        "unassigned": unassigned,
        "unassigned_all": unassigned_all,
        "total_all": d26 + unassigned,
        "dup": dedup_for_street(n26) if do_dedup else None,
    }

    # 派生资产
    risk = json.load(open(os.path.join(SCRIPTS, "risk_scores.json"), encoding="utf-8"))
    gov = json.load(open(os.path.join(SCRIPTS, "governance_tracking.json"), encoding="utf-8"))
    blift = json.load(open(os.path.join(SCRIPTS, "bottom_lift_communities.json"), encoding="utf-8"))
    inv = json.load(open(os.path.join(SCRIPTS, "investigation_targets.json"), encoding="utf-8"))

    risk_street = risk.get("street_distribution", {})
    risk_comm = risk.get("all_communities", [])
    gov_street = gov.get("street_effects", {})

    externals = load_externals()

    # 全区类别基线（2026年1-8月）
    dist_cat = n26["category_14"].value_counts()
    dist_cat25 = n25s["category_14"].value_counts()
    dist_company_no = main["property_company"].astype(str).str.strip().isin(["", "无", "nan", "None"]).mean()

    # 下降总量（全区）
    district_decline = max(d25s - d26, 1)

    streets_data, overview = {}, []

    for st in streets:
        s26 = n26[n26["street"] == st]
        s25 = n25s[n25s["street"] == st]
        s24 = n24s[n24s["street"] == st]
        a26, a25, a24 = len(s26), len(s25), len(s24)
        dec = a25 - a26

        # ── 核心指标
        communities = s26["community_name"].astype(str).str.strip()
        comm_valid = communities[~communities.isin(["", "无", "nan"])]
        active_communities = int(comm_valid.nunique())
        core = {
            "n2026": a26, "n2025_same": a25, "n2024_same": a24,
            "n2025_full": int(len(n25f[n25f["street"] == st])),
            "n2024_full": int(len(n24f[n24f["street"] == st])),
            "yoy": yoy(a26, a25),
            "yoy_2025_vs_2024": yoy(a25, a24),
            "share": pct(a26, d26),
            "contribution": pct(dec, district_decline) if dec > 0 else None,
            "decline": int(dec),
            "active_communities": active_communities,
        }

        # ── 月度序列（1-12 月，缺数据为 null）
        labels, y24, y25, y26 = [], [], [], []
        for m in range(1, 13):
            labels.append(f"{m}月")
            def cnt_of(y):
                if y == YEAR_NOW and m > MONTH_NOW:
                    return None
                return int(len(main[(main["year"] == y) & (main["month"] == m) & (main["street"] == st)]))
            y24.append(cnt_of(2024))
            y25.append(cnt_of(2025))
            y26.append(cnt_of(2026))

        yoy_monthly = []
        for m in range(1, MONTH_NOW + 1):
            c26 = int(len(s26[s26["month"] == m]))
            c25 = int(len(s25[s25["month"] == m]))
            yoy_monthly.append({"month": m, "y2026": c26, "y2025": c25, "yoy": yoy(c26, c25)})

        quarterly = []
        for label, ms in [("Q1", (1, 3)), ("Q2", (4, 6)), (f"{MONTH_NOW-1}-{MONTH_NOW}月", (7, MONTH_NOW))]:
            def q(y):
                return int(len(main[(main["year"] == y) & (main["month"] >= ms[0]) &
                                    (main["month"] <= ms[1]) & (main["street"] == st)]))
            quarterly.append({"label": label, "y2024": q(2024), "y2025": q(2025), "y2026": q(2026)})

        # ── 类别结构 + 上升/下降
        c26 = s26["category_14"].value_counts()
        c25 = s25["category_14"].value_counts()
        cats = []
        for cat in sorted(set(list(c26.index) + list(c25.index))):
            n_a, n_b = int(c26.get(cat, 0)), int(c25.get(cat, 0))
            cats.append({"cat": cat, "n2026": n_a, "n2025": n_b, "delta": n_a - n_b,
                         "yoy": yoy(n_a, n_b), "pct": pct(n_a, a26),
                         "district_pct": pct(int(dist_cat.get(cat, 0)), d26),
                         "avg_yoy": yoy(int(dist_cat.get(cat, 0)), int(dist_cat25.get(cat, 0)))})
        cats.sort(key=lambda x: -x["n2026"])
        rising = sorted([c for c in cats if c["delta"] > 0 and c["n2026"] >= 10],
                        key=lambda x: -x["delta"])[:6]
        falling = sorted([c for c in cats if c["delta"] < 0], key=lambda x: x["delta"])[:6]

        # ── 热点小区 Top10
        def top_communities():
            out = []
            g26 = s26.groupby("community_name").size().sort_values(ascending=False)
            for com, cnt in g26.head(10).items():
                com_s = str(com).strip()
                if com_s in ("", "无", "nan"):
                    continue
                sub26 = s26[s26["community_name"] == com]
                sub25 = s25[s25["community_name"] == com]
                cat_top = sub26["category_14"].value_counts()
                # 同小区同类 ≥3 的高频组数
                gc = sub26.groupby("category_14").size()
                out.append({
                    "name": com_s, "n2026": int(cnt), "n2025": int(len(sub25)),
                    "yoy": yoy(int(cnt), int(len(sub25))),
                    "pct": pct(int(cnt), a26),
                    "top_category": str(cat_top.index[0]) if len(cat_top) else "",
                    "top_category_pct": pct(int(cat_top.iloc[0]), int(cnt)) if len(cat_top) else 0.0,
                    "freq_groups": int((gc >= 3).sum()),
                })
            return out
        top_comm = top_communities()
        top5_names = [c["name"] for c in top_comm[:5]]
        top5_cnt = sum(c["n2026"] for c in top_comm[:5])

        # ── 地址级热点
        addr_valid = s26["community_addr"].astype(str).str.strip()
        addr_valid = addr_valid[~addr_valid.isin(["", "无", "nan"])]
        addr_top = addr_valid.value_counts().head(6)

        # ── 物业企业
        comp = s26["property_company"].astype(str).str.strip()
        no_comp = int(comp.isin(["", "无", "nan", "None"]).sum())
        comp_v = comp[~comp.isin(["", "无", "nan", "None"])]
        comp_top = comp_v.value_counts().head(10)
        companies = []
        for name, cnt in comp_top.items():
            companies.append({
                "name": name, "n2026": int(cnt),
                "n2025": int((s25["property_company"].astype(str).str.strip() == name).sum()),
                "yoy": yoy(int(cnt), int((s25["property_company"].astype(str).str.strip() == name).sum())),
                "pct": pct(int(cnt), a26),
                "communities": int(s26[s26["property_company"].astype(str).str.strip() == name]["community_name"].nunique()),
            })
        top3_comp = sum(c["n2026"] for c in companies[:3])

        # ── 渠道 / 工单类型
        src = s26["source"].fillna("未标注").astype(str).replace({"nan": "未标注"}).value_counts()
        sources = [{"name": k, "cnt": int(v), "pct": pct(int(v), a26)} for k, v in src.items()]
        ot = s26["order_type"].value_counts()
        order_types = [{"name": k, "cnt": int(v), "pct": pct(int(v), a26)} for k, v in ot.items()]

        # ── 数据质量
        def miss_rate(col):
            v = s26[col].astype(str).str.strip()
            return pct(int(v.isin(["", "无", "nan", "None"]).sum()), a26)
        quality = {
            "miss_community_pct": miss_rate("community_name"),
            "miss_addr_pct": miss_rate("community_addr"),
            "miss_source_pct": pct(int(s26["source"].isna().sum()), a26),
            "no_company_pct": pct(no_comp, a26),
        }

        # ── 重复投诉
        dup = dedup_for_street(s26) if do_dedup else None

        # ── 风险（派生资产：华泾镇 → 华泾）
        key = DERIVED_ALIAS.get(st, st)
        rd = risk_street.get(key, {})
        risk_comm_st = [c for c in risk_comm if c.get("street") == key]
        risk_comm_st.sort(key=lambda x: -x.get("total_score", 0))
        risk_info = {
            "total": int(rd.get("total", len(risk_comm_st))),
            "red": int(rd.get("红色", 0)), "orange": int(rd.get("橙色", 0)),
            "yellow": int(rd.get("黄色", 0)), "blue": int(rd.get("蓝色", 0)),
            "top": [{"community": c.get("community"), "score": c.get("total_score"),
                     "level": c.get("risk_level"), "total": c.get("total"),
                     "growth_rate": c.get("growth_rate"), "repeat_rate": c.get("repeat_rate"),
                     "top_category": c.get("top_category")} for c in risk_comm_st[:5]],
            "scope_note": "风险评估口径：799 个参评小区（含纳统与热线双源）",
        }

        ge = gov_street.get(key, {})

        def gov_cases(keyname, label):
            out = []
            for c in gov.get(keyname, []) or []:
                if c.get("street") != key:
                    continue
                out.append({"community": c.get("community"), "n2024": c.get("n2024"),
                            "n2025": c.get("n2025"), "n2026_h1": c.get("n2026_h1"),
                            "improvement_2026": c.get("improvement_2026"),
                            "top_category": c.get("top_category"), "kind": label})
            return out

        gov_info = {
            "tracking_total": int(gov.get("total_tracking", 0)),
            "scope_note": "治理成效为 2026 上半年（1-6月）口径；案例取自《治理效果追踪分析报告》Top 榜单",
            "effect_2026": ge.get("effect_2026"),
            "volume_2024": ge.get("2024"), "volume_2025": ge.get("2025"),
            "volume_2025_h1": ge.get("2025_h1"), "volume_2026_h1": ge.get("2026_h1"),
            "cases_success": gov_cases("success_top20", "成功改善"),
            "cases_rebound": gov_cases("rebound_top10", "反弹"),
            "cases_worsening": gov_cases("worsening_top10", "恶化"),
        }

        blift_st = [b for b in blift if b.get("street") == key]
        inv_st = [{"community": k, "addr": v.get("target_addr"), "street": v.get("street"),
                   "n2026": v.get("total_2026"), "n2025": v.get("total_2025"), "n2024": v.get("total_2024")}
                  for k, v in inv.items() if v.get("street") == key]

        street_obj = {
            "name": st,
            "core": core,
            "monthly": {"labels": labels, "y2024": y24, "y2025": y25, "y2026": y26},
            "yoy_monthly": yoy_monthly,
            "quarterly": quarterly,
            "category": cats,
            "rising": rising,
            "falling": falling,
            "top_communities": top_comm,
            "concentration": {
                "top5_share": pct(top5_cnt, a26), "top5_names": top5_names,
                "top3_company_share": pct(top3_comp, a26),
                "company_count": int(s26["property_company"].astype(str).str.strip()
                                     .replace({"无": None}).dropna().nunique()),
            },
            "addresses": [{"addr": k, "n2026": int(v),
                           "n2025": int((s25["community_addr"].astype(str).str.strip() == k).sum()),
                           "top_category": (s26[s26["community_addr"].astype(str).str.strip() == k]
                                            ["category_14"].value_counts().index[0]
                                            if len(s26[s26["community_addr"].astype(str).str.strip() == k]) else "")}
                          for k, v in addr_top.items()],
            "companies": companies,
            "sources": sources,
            "order_types": order_types,
            "quality": quality,
            "dup": dup,
            "risk": risk_info,
            "governance": gov_info,
            "externals": externals.get(st, externals.get(key, {})),
            "bottom_lift": {"count": len(blift_st), "names": [b["name"] for b in blift_st][:10]},
            "investigation": inv_st,
            "keywords": keywords_of(s26, street=st),
        }
        streets_data[st] = street_obj

        overview.append({
            "street": st, "n2026": a26, "n2025_same": a25, "n2024_same": a24,
            "yoy": core["yoy"], "share": core["share"],
            "contribution": core["contribution"],
            "communities": active_communities,
            "dup_rate": dup["rate"] if dup else None,
            "dup_high": dup["high_count"] if dup else None,
            "dup_count": dup["dup_count"] if dup else None,
            "risk_red": risk_info["red"], "risk_orange": risk_info["orange"],
            "risk_total": risk_info["total"],
            "effect_2026": ge.get("effect_2026"),
        })

    # ── 排名
    overview.sort(key=lambda x: -x["n2026"])
    for i, r in enumerate(overview, 1):
        r["rank_total"] = i
    by_yoy = sorted(overview, key=lambda x: (x["yoy"] if x["yoy"] is not None else 999))
    for i, r in enumerate(by_yoy, 1):
        r["rank_yoy"] = i                      # 1 = 降幅最大
    dup_sorted = sorted([r for r in overview if r["dup_rate"] is not None], key=lambda x: x["dup_rate"])
    for i, r in enumerate(dup_sorted, 1):
        r["rank_dup"] = i                      # 1 = 重复率最低
    risk_sorted = sorted(overview, key=lambda x: -(x["risk_red"] or 0))
    for i, r in enumerate(risk_sorted, 1):
        r["rank_risk"] = i
    for r in overview:
        sb = streets_data[r["street"]]
        sb["core"].update({"rank_total": r["rank_total"], "rank_yoy": r["rank_yoy"],
                           "rank_dup": r.get("rank_dup"), "rank_risk": r["rank_risk"]})

    # ── 自动结论
    for r in overview:
        sb = streets_data[r["street"]]
        sb["insights"] = make_insights(sb, r, district, dist_cat, d26)

    meta = {
        "generated": "2026-09-20",
        "period_label": f"{YEAR_NOW}年1-{MONTH_NOW}月",
        "compare_label": f"{YEAR_PREV}年1-{MONTH_NOW}月",
        "street_count": len(streets),
        "notes": [
            f"街镇明细合计 {d26:,} 条 + 归属为空 {unassigned} 条 = 全区 {d26 + unassigned:,} 条",
            "同比统一采用同期口径（1-8月 vs 1-8月），不使用全年基数",
            f"{YEAR_NOW}年 9-12 月数据未产生，图表以空值呈现",
            "重复投诉率：同小区内容完全重复 ∪ 催办关键词 ∪ 同小区同类≥3次 ∪ 文本相似≥0.6，按街镇 1-8 月累计计算",
            "治理成效为 2026 上半年口径；风险评估为 799 个参评小区口径",
        ],
    }
    return {"meta": meta, "district": district, "overview": overview, "streets": streets_data}


def make_insights(sb, row, district, dist_cat, d26):
    """按数据自动生成该街镇 3-6 条要点结论。"""
    out = []
    st = sb["name"]
    c = sb["core"]
    dy = c["yoy"]
    trend_word = "下降" if (dy is not None and dy < 0) else "上升"
    out.append(f"{st}：{row['n2026']:,} 件，居全区第 {c['rank_total']} 位，占全区 {c['share']}%；"
               f"同比 {trend_word} {abs(dy) if dy is not None else 0}%"
               f"（全区 {district['yoy']}%），降幅排名全区第 {c['rank_yoy']} 位。")

    if c["contribution"] and c["contribution"] > 0:
        out.append(f"对全区投诉量下降的贡献率为 {c['contribution']}%（该镇减少 {c['decline']:,} 件）。")

    if sb["rising"]:
        names = "、".join(f"{x['cat']}（+{x['delta']}件）" for x in sb["rising"][:3])
        out.append(f"⚠ 逆势上升类别：{names}，需重点关注。")

    if sb["category"]:
        top = sb["category"][0]
        diff = round(top["pct"] - top["district_pct"], 1)
        cmp_word = "高于" if diff > 0 else "低于"
        out.append(f"首要矛盾为{top['cat']}（{top['n2026']:,} 件，占本镇 {top['pct']}%，"
                   f"{cmp_word}全区 {abs(diff)} 个百分点）。")

    if sb["top_communities"]:
        t = sb["top_communities"][0]
        out.append(f"投诉最集中小区为{t['name']}（{t['n2026']} 件，占本镇 {t['pct']}%，"
                   f"同比 {('+' if (t['yoy'] or 0) > 0 else '')}{t['yoy']}%）；"
                   f"Top5 小区集中度 {sb['concentration']['top5_share']}%。")

    if sb["companies"]:
        t = sb["companies"][0]
        out.append(f"投诉最多物业企业为{t['name']}（{t['n2026']} 件，占本镇 {t['pct']}%，"
                   f"涉及 {t['communities']} 个小区）。")

    rk = sb["risk"]
    if rk["red"] or rk["orange"]:
        out.append(f"风险预警：红色 {rk['red']} 个、橙色 {rk['orange']} 个小区"
                   f"（该镇参评 {rk['total']} 个）。")

    d = sb["dup"]
    if d:
        cmp_txt = ""
        if district.get("dup"):
            diff = round(d["rate"] - district["dup"]["rate"], 1)
            cmp_txt = f"，{'高于' if diff > 0 else '低于'}全区 {abs(diff)} 个百分点"
        out.append(f"重复投诉 {d['dup_count']:,} 件，重复率 {d['rate']}%{cmp_txt}；"
                   f"高优先级 {d['high_count']:,} 件。")

    if sb["governance"]["effect_2026"] is not None:
        e = sb["governance"]["effect_2026"]
        word = "改善" if e > 0 else "恶化"
        out.append(f"治理成效（2026 上半年口径）：{sb['governance']['volume_2026_h1']:,} 件，"
                   f"同比{word} {abs(e)}%。")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-dedup", action="store_true", help="跳过去重计算（快速预览）")
    args = ap.parse_args()

    print("构建街镇维度数据集…")
    data = build(do_dedup=not args.no_dedup)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    ov = data["overview"]
    print(f"\n✔ 完成，输出 {OUT}（{os.path.getsize(OUT)/1024:.1f} KB）")
    print(f"  街镇 {len(ov)} 个 | 全区 {data['district']['n2026']:,} 条 "
          f"| 同比 {data['district']['yoy']}% | 对账 {data['district']['n2026']:,}+"
          f"{data['district']['unassigned']} = {data['district']['total_all']:,}")
    for r in ov:
        print(f"  {r['street']:6s} {r['n2026']:5d} 件  同比 {str(r['yoy']):>6s}%  "
              f"贡献 {str(r['contribution']):>6s}%  重复率 {str(r['dup_rate']):>5s}%")


if __name__ == "__main__":
    main()
