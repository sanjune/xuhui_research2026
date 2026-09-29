# -*- coding: utf-8 -*-
"""
2026年 投诉去重分析（四重策略）— 月度可复现脚本
================================================

依据《投诉去重识别方法论说明》实现四重识别策略，对指定月份做去重分析，
输出与 scripts/dedup_monthly_all.json 同构的月度结果，并合并写入该文件。

用法：
    python scripts/dedup_monthly.py --month 8            # 计算 2026年8月并合并
    python scripts/dedup_monthly.py --month 8 --dry-run  # 只打印，不写文件

四重策略（判定口径）：
    策略一 S1  完全重复     同小区 + 内容完全一致（去首尾空白），组内 ≥2 条
    策略二 S2  催办/重发     ① 内容命中「催单 / 催办 / 重新交办 / 相同事项」；
                          ② 命中「反复 + 来电/催/投诉/反映/举报/交办」这类催办搭配
                             （「反复」单独出现多为普通描述，见 S2_AGAIN_RE 注释）；
                          ③ 本单正文段命中系统标记「重复来电」
                             （须先剥离引用块，见 strategy2_keyword 注释）
    策略三 S3  同小区同类高频  同小区 + 同十四类，条数 ≥3
    策略四 S4  文本相似     同小区内 jieba 分词 → TF-IDF → 余弦相似度 ≥0.6
                          且受理时间间隔 ≤90 天

    合并去重：四策略工单编号取并集
    优先级分级（依据历史各月数值反推，偏差 ±4% 以内）：
        高优先级 = S1 ∪ S2 ∪ S3中「频次≥4」组的超额工单（明确重复或高频）
        中优先级 = 其余（频次=3 的统计推断 / 仅文本相似）

    组类策略（S1/S3）的「条数」= 组内工单数 − 组数，即重复超额数（每组保留 1 条原件）。

注意：2026年1-7月的数值沿用此前已发布的结果（口径未变，保持汇报口径连续），
      本脚本用于从 8 月起逐月扩展。如整年重算，需在项目组确认后统一替换。

⚠️ 2026-09-24 口径修正（S2 收紧）：
   旧 S2_KEYWORDS 含裸词「反复」，会把「杜绝反复积水」「现象反复发生」「反复转运」
   这类普通描述误判为催办重发。现改为：
     · 删除裸词「反复」
     · 新增同义催办标记「催办」（原表只有「催单」，漏了「催办」）
     · 保留「反复 + 来电/催/投诉/反映/举报/交办」这类催办搭配兜底
   影响（9 月复核表 1516 条）：重复 608 → 600，高 511 → 503。
   影响（2026 年 8 月，主库）：重复 796 → 785，S2 213 → 197。
   ⚠️ 1-7 月为历史沿用值，**未按新规则追溯重算**，如需统一须项目组确认后整年重算。

⚠️ 2026-09-24 口径修正（S2 补充 · 系统标记）：
   新增第 ③ 支判据：本单正文段命中系统自动标记「重复来电」。
   「重复来电」是话务平台直接打在本单上的标签，属最明确的重复信号，
   比关键词推断更可靠；此前仅靠「催单」等词间接命中，会漏掉
   「重复来电，咨询处理进度。【最近办结…】」这类只带标记、不带催办词的工单。
   实现要点：匹配前先剥离系统追加的引用块（QUOTED_BLOCK_RE），
   避免把引用块内转载的历史原文措辞误当成本单标记（见 strategy2_keyword 注释）。
   影响（9 月复核表 1516 条）：重复 600 → 609，高 500 → 517，S2 271 → 295。
   影响（2026 年 8 月，主库）：重复 785 → 795，S2 197 → 226。
   影响（2026 年 1-8 月，主库逐月合计）：重复 4802（35.0%）→ 4908（35.8%），净增 106 条。
     分月增量：1月 +0 / 2月 +8 / 3月 +15 / 4月 +18 / 5月 +20 / 6月 +14 / 7月 +21 / 8月 +10。
   ⚠️ 1-7 月仍为历史沿用值，未追溯重算；dedup_monthly_all.json、
      《1-8月去重建议清单.html》、街镇专项分析报告中的相关数字仍是旧口径，
      如需与脚本口径统一，须项目组确认后整年重算。
"""
import argparse
import json
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKL = os.path.join(ROOT, "data", "merged_cleaned.pkl")
OUT_JSON = os.path.join(ROOT, "scripts", "dedup_monthly_all.json")

S2_KEYWORDS = ["催单", "催办", "重新交办", "相同事项"]

# 「反复」不能单独作为催办信号：实践中大量出现的是普通描述用语
# （杜绝反复积水／现象反复发生／问题反复／反复转运／反复沟通／反复疯长…），
# 会把它误判成"催办重发"。仅当「反复」与投诉动作搭配（同句、间隔 ≤6 字）时才计入。
# 例：反复来电／反复催单／反复投诉／反复反映／反复举报／反复交办。
# 注：真正的催办多数已由「催单」「催办」直接命中，此处只作兜底。
S2_AGAIN_RE = re.compile(
    r"反复[^。；;！？\n]{0,6}(?:来电|催|投诉|反映|举报|交办|派单|补单)")

# ── 系统自动标记（2026-09-24 新增）─────────────────────────────
# 「重复来电」是话务平台直接打在本单上的标记，属最明确的重复信号，
# 比任何关键词推断都可靠，故纳入 S2。（「多次来电」经抽查是市民叙述用语，
# 如"之后多次来电询问但未获回复"，不是系统标记，不纳入。）
S2_SYS_MARKS = ["重复来电"]
S2_SYS_RE = re.compile("|".join(S2_SYS_MARKS))

# 系统追加的引用块：「【最近派发的工单编号：X，工单内容：<原文全文>】」
# 实际写法有十余种变体（最近派发/最近办结/最近办结地/最近发的/最近派发工单编号/
# 最近办结工单号/最近办结工单：…），故：
#   1) 引导语放宽为「最近 + ≤8 汉字 + 工单(编)(号)」，「编」「号」均可缺省；
#   2) 另立一支，覆盖「【重新交办，关联工单X】」这类无「最近」前缀的写法。
# 用非捕获组，避免 pandas 的「pattern has match groups」告警。
# 本正则是全项目唯一口径源（dedup_review_external / export_dedup_review_list 均从此处引用）。
QUOTED_BLOCK_RE = re.compile(
    r"(?:【\s*)?最近[\u4e00-\u9fa5]{0,8}?工单(?:编)?号?[：:][\s\S]*?(?:】|$)"
    r"|【[^【】]{0,24}?工单(?:编)?号?[：:]?\s*\d{14}[\s\S]*?(?:】|$)")

# 正文里引用的工单编号（统一按「工单(编)(号) + 14 位数字」抓取）
# 注意两点（2026-09-24 修正，与 QUOTED_BLOCK_RE 同属唯一口径源）：
#   1) 「编」「号」都改为可选 —— 「关联工单2026…」「最近办结工单：2026…」原写法抓不到；
#   2) 两侧加数字边界，避免把 18 位身份证号（如 3101081965******36）的前 14 位误判为工单编号。
ORDER_REF_RE = re.compile(r"工单(?:编)?号?[：:]?\s*(?<!\d)(\d{14})(?!\d)")


def _head_text(text: str) -> str:
    """只留本单正文段：剥离系统追加的引用块。"""
    return QUOTED_BLOCK_RE.sub("", text or "").strip()


S4_THRESHOLD = 0.6
S4_WINDOW_DAYS = 90
FREQ_THRESHOLD = 3      # 同小区同类高频阈值
HF20_MIN_COUNT = 5      # 高频组「高」优先级下限

STOPWORDS = set("的 了 在 是 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好 "
                "自己 这 市民 反映 诉求 请 处理 尽快 相关 部门 该 上述 地址 问题 情况 来电 投诉 "
                "求助 举报 关于 由于 因为 目前 已经 至今 一直 未 我们 他们 小区".split())


# ─────────────────────────── 数据准备 ───────────────────────────

def load_month(year: int, month: int) -> pd.DataFrame:
    df = pd.read_pickle(PKL)
    d = df[(df["year"] == year) & (df["month"] == month)].copy()
    d["content"] = d["content"].fillna("").astype(str).str.strip()
    d["t"] = pd.to_datetime(d["accept_time"], errors="coerce")
    return d


# ─────────────────────────── 四重策略 ───────────────────────────

def strategy1_exact(d: pd.DataFrame):
    """同小区 + 内容完全一致（组内保留最早 1 条为原件）。"""
    s1_orders, groups = set(), 0
    work = d[d["content"] != ""]
    for (_, _c), grp in work.groupby(["community_name", "content"]):
        if len(grp) < 2:
            continue
        groups += 1
        ordered = grp.sort_values("t")
        s1_orders |= set(ordered.index[1:])       # 除最早一条外均为重复
    return s1_orders, groups


def strategy2_keyword(d: pd.DataFrame):
    """催办 / 重发：关键词命中，或「反复 + 投诉动作」搭配命中，或系统标记「重复来电」。

    「反复」单独出现不算（见 S2_AGAIN_RE 注释），避免把
    「杜绝反复积水」「现象反复发生」这类普通描述误判为催办重发。

    「重复来电」须**剥离引用块后**再匹配：该词也常出现在系统追加的引用块内部
    （【最近派发的工单编号：…，工单内容：…重复来电…】），那是转载的历史工单
    原文措辞，不代表本单是重复来电。主库 66,812 条中含该词 1,104 条，
    其中 22 条仅出现在引用块内（2.0%），不剥离会把它们误判为本单标记。
    """
    pattern = "|".join(S2_KEYWORDS)
    hit = (d["content"].str.contains(pattern, regex=True, na=False)
           | d["content"].str.contains(S2_AGAIN_RE, regex=True, na=False))

    content = d["content"].fillna("").astype(str)
    cand = content.str.contains(S2_SYS_RE, regex=True, na=False)
    if cand.any():
        arr = hit.to_numpy()
        for pos in np.flatnonzero(cand.to_numpy()):
            if S2_SYS_RE.search(_head_text(content.iloc[pos])):
                arr[pos] = True
        hit = pd.Series(arr, index=d.index)
    return set(d[hit].index)


def strategy3_frequency(d: pd.DataFrame):
    """同小区 + 同十四类，条数 ≥3（组内保留 1 条，其余为重复）。

    返回 (超额重复工单集, 组键列表, 频次字典, 频次≥4组的超额工单集)
    """
    s3_orders, s3_f4, group_keys, freq = set(), set(), [], {}
    for (com, cat), grp in d.groupby(["community_name", "category_14"]):
        n = len(grp)
        if n < FREQ_THRESHOLD:
            continue
        freq[(com, cat)] = n
        group_keys.append((com, cat, n))
        extras = set(grp.sort_values("t").index[1:])
        s3_orders |= extras
        if n >= 4:
            s3_f4 |= extras
    return s3_orders, group_keys, freq, s3_f4


def _fallback_tokens(text: str):
    """无 jieba 时的回退分词：按标点切分，中文串取二元组。"""
    chunks = re.split(r"[^\u4e00-\u9fa5A-Za-z0-9]+", text)
    toks = []
    for ch in chunks:
        if not ch:
            continue
        if re.fullmatch(r"[A-Za-z0-9]+", ch):
            toks.append(ch.lower())
        elif len(ch) <= 2:
            toks.append(ch)
        else:
            toks.extend(ch[i:i + 2] for i in range(len(ch) - 1))
    return toks


def _tokenize(text: str):
    try:
        import jieba
    except ImportError:
        return [w for w in _fallback_tokens(text) if w not in STOPWORDS]
    return [w for w in jieba.lcut(text) if w.strip() and w not in STOPWORDS and len(w) > 1]


def _tfidf_cosine(docs):
    """TF-IDF + 余弦相似度。

    优先用 scikit-learn；若环境无 sklearn，则用等价的 numpy 实现
    （词频 TF 取 1+log(tf)，IDF 取 log((1+n)/(1+df))+1，向量 L2 归一化后点积）。
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vec = TfidfVectorizer(token_pattern=r"(?u)\S+").fit_transform(docs)
        from sklearn.metrics.pairwise import cosine_similarity
        return cosine_similarity(vec)
    except ImportError:
        vocab, rows = {}, []
        tokenized = [d.split() for d in docs]
        for toks in tokenized:
            for t in set(toks):
                vocab.setdefault(t, len(vocab))
        n_doc, n_voc = len(tokenized), len(vocab)
        counts = np.zeros((n_doc, n_voc))
        for i, toks in enumerate(tokenized):
            for t in toks:
                counts[i, vocab[t]] += 1
        df = (counts > 0).sum(axis=0)
        idf = np.log((1 + n_doc) / (1 + df)) + 1
        tf = np.where(counts > 0, 1 + np.log(np.maximum(counts, 1)), 0.0)
        mat = tf * idf
        norm = np.linalg.norm(mat, axis=1, keepdims=True)
        mat = mat / np.where(norm == 0, 1, norm)
        return mat @ mat.T


def strategy4_similarity(d: pd.DataFrame):
    """同小区内 TF-IDF 余弦相似度 ≥0.6 且时间间隔 ≤90 天。"""
    s4_orders, pairs, comms = set(), [], set()
    order_sim = {}
    for com, grp in d[d["content"] != ""].groupby("community_name"):
        if len(grp) < 2:
            continue
        grp = grp.sort_values("t")
        docs = [" ".join(_tokenize(c)) for c in grp["content"]]
        docs = [x if x.strip() else "-" for x in docs]
        try:
            sim = _tfidf_cosine(docs)
        except ValueError:
            continue
        idx = list(grp.index)
        times = list(grp["t"])
        hit_com = False
        for i in range(len(idx)):
            for j in range(i + 1, len(idx)):
                if sim[i, j] < S4_THRESHOLD:
                    continue
                ti, tj = times[i], times[j]
                if pd.notna(ti) and pd.notna(tj) and abs((tj - ti).days) > S4_WINDOW_DAYS:
                    continue
                s4_orders.add(idx[j])              # 较晚的一条计为重复
                hit_com = True
                order_sim[idx[j]] = max(order_sim.get(idx[j], 0.0), float(sim[i, j]))
                pairs.append({
                    "community": com if isinstance(com, str) else None,
                    "a": grp.loc[idx[i], "content"],
                    "b": grp.loc[idx[j], "content"],
                    "sim": round(float(sim[i, j]), 3),
                    # 行索引标签：供清单侧把「相似对」还原成「重复组」用（不影响任何计数口径）
                    "ai": idx[i], "bi": idx[j],
                })
        if hit_com:
            comms.add(com)
    pairs.sort(key=lambda x: -x["sim"])
    return s4_orders, pairs, comms, order_sim


# ─────────────────────────── 汇总 ───────────────────────────

def _dist(d: pd.DataFrame, dup_idx, col: str, pct_base: int):
    sub = d.loc[sorted(dup_idx)]
    out = []
    for k, v in sub.groupby(col).size().sort_values(ascending=False).items():
        out.append({"cat" if col == "category_14" else "street": k,
                    "cnt": int(v), "pct": round(v / pct_base * 100, 1)})
    return out


def _clip(text: str, n: int = 40):
    """截断为 n 字（与既有 JSON 一致，不加省略号；省略号由页面渲染时补）"""
    return text[:n]


def analyze(year: int, month: int) -> dict:
    d = load_month(year, month)
    total = len(d)

    s1, s1g = strategy1_exact(d)
    s2 = strategy2_keyword(d)
    s3, s3_groups, freq, s3_f4 = strategy3_frequency(d)
    s4, s4_pairs, s4_comms, order_sim = strategy4_similarity(d)

    union = s1 | s2 | s3 | s4
    high = s1 | s2 | s3_f4          # 明确重复（完全一致/催办）或高频组（≥4次）
    mid = union - high

    # 高频热点小区 Top20（同小区同类 ≥3）
    prop_map = d.groupby(["community_name", "category_14"])["property_company"].agg(
        lambda x: x.dropna().iloc[0] if len(x.dropna()) else "")
    street_map = d.groupby(["community_name", "category_14"])["street"].agg(
        lambda x: x.dropna().iloc[0] if len(x.dropna()) else "")
    hf = sorted(freq.items(), key=lambda kv: (-kv[1], str(kv[0][0])))
    hf20 = []
    for rank, ((com, cat), cnt) in enumerate(hf[:20], 1):
        hf20.append({
            "rank": rank, "community": com, "street": street_map.get((com, cat), ""),
            "category": cat, "count": int(cnt),
            "property": prop_map.get((com, cat), ""),
            "priority": "高" if cnt >= HF20_MIN_COUNT else "中",
        })

    # 去重建议清单 Top15：S3 组中频次=4 的组内工单，不足则以频次=3 补齐
    list15, picked = [], 0
    for want in (4, 3):
        for (com, cat), cnt in sorted(freq.items(), key=lambda kv: (-kv[1], str(kv[0][0]))):
            if cnt != want:
                continue
            grp = d[(d["community_name"] == com) & (d["category_14"] == cat)]
            for oid in grp.sort_values("t").index[1:]:
                if picked >= 15:
                    break
                row = d.loc[oid]
                in_s4 = oid in s4
                strat = "S3+S4" if in_s4 else "S3"
                list15.append({
                    "oid": str(row["order_id"]) if pd.notna(row["order_id"]) else "",
                    "community": com, "street": row["street"], "category": cat,
                    "strategies": strat, "freq": int(cnt),
                    "sim": round(order_sim[oid], 2) if in_s4 else None,
                    "suggestion": "文本相似—核实合并", "priority": "中",
                })
                picked += 1
            if picked >= 15:
                break
        if picked >= 15:
            break

    dup_n = len(union)
    return {
        "total": total,
        "total_dup": dup_n,
        "dup_rate": round(dup_n / total * 100, 1) if total else 0.0,
        "s1_count": len(s1), "s1_groups": s1g,
        "s2_count": len(s2),
        "s3_count": len(s3), "s3_groups": len(s3_groups),
        "s4_count": len(s4_pairs), "s4_pairs": len(s4_pairs), "s4_comms": len(s4_comms),
        "high_count": len(high), "mid_count": len(mid),
        "hf20": hf20,
        "cats": _dist(d, union, "category_14", dup_n),
        "streets": _dist(d, union, "street", dup_n),
        "sim_top5": [{"community": p["community"], "a": _clip(p["a"]), "b": _clip(p["b"]),
                      "sim": p["sim"]} for p in s4_pairs[:5]],
        "list15": list15,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--month", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    res = analyze(args.year, args.month)
    print(json.dumps(res, ensure_ascii=False, indent=2)[:1500], "...\n")
    print(f"[{args.year}-{args.month}] 总量 {res['total']} | 重复 {res['total_dup']} "
          f"({res['dup_rate']}%) | 高 {res['high_count']} / 中 {res['mid_count']} | "
          f"S1 {res['s1_count']}/{res['s1_groups']}组 S2 {res['s2_count']} "
          f"S3 {res['s3_count']}/{res['s3_groups']}组 S4 {res['s4_count']}对/{res['s4_comms']}小区")

    if args.dry_run:
        return
    data = json.load(open(OUT_JSON, encoding="utf-8")) if os.path.exists(OUT_JSON) else {}
    data[str(args.month)] = res
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已写入 {OUT_JSON}（月份键 {args.month}）")


if __name__ == "__main__":
    main()
