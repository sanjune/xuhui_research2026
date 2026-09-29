# -*- coding: utf-8 -*-
"""2026 年 1-8 月投诉去重汇总（给报告页引用的单一数字源）
=========================================================

背景
----
历史上同一套"去重"数字在不同页面并存过四代口径：

    9,239 / 3,746 / 40.5%   —— 最早一版（《投诉去重识别方法论说明》）
    9,387 / 4,217 / 44.9%   —— 上半年版（h1_dedup_summary.json、1-6月清单）
    4,753 / 34.6%           —— 8 月并入后的旧 dedup_monthly_all.json
    4,908 / 35.8%           —— 现行口径（S2 补充系统标记「重复来电」后重算）

各页各写各的，导致「同一指标、多个取值」。本脚本按月调用
`scripts/dedup_monthly.py` 的四个策略函数（唯一判定口径源），把 1-8 月
聚合成一份汇总 JSON，报告页一律引用它，不再手写数字。

输出
----
    scripts/dedup_18_summary.json

用法
----
    PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 \
        scripts/build_dedup_18_summary.py [--months 1-8]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dedup_monthly as D  # noqa: E402  唯一判定口径源

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "scripts", "dedup_18_summary.json")

# 补充停用词：`dedup_monthly.STOPWORDS` 只服务于 TF-IDF 向量化，颗粒较粗，
# 直接拿来出「高频关键词」表会把「要求/管理/物业/回复/信息/答复/补充」这类
# 公文与工单模板词排到最前面，需再剔一层（与 build_street_dataset 的
# STOP_BOILERPLATE 同源思路）。
STOP_EXTRA = set("""
要求 管理 物业 回复 信息 表示 答复 补充 要点 业主 小区 市民 反映 诉求 处理
情况 问题 投诉 求助 举报 关于 目前 已经 一直 未 我们 他们 希望 建议 核实
联系 确认 是否 后续 单位 收到 感谢 满意 承办 工作人员 部门 予以 尽快 经
街道 居委会 居委 同志 先生 女士 来电 反映人 诉求人 徐汇区 上海 号楼 室
至今 现场 查看 检查 排查 落实 跟进 反馈 沟通 通知 告知 协调 督促 整改 整治
取缔 加强 及时 相关 有关 进行 存在 出现 发生 认为 应该 可以 能否 如何 事项
保密 重新 催单 催办 交办 居民 需要 实际 内容 无需 派发 办结 编号 最近 派单
""".split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--months", default="1-8", help="如 1-8")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    a, b = args.months.split("-")
    months = list(range(int(a), int(b) + 1))

    monthly, dup_communities, all_comms_s4 = [], set(), set()
    cat_cnt = {}
    com_cnt = {}
    dup_texts = []
    strategy = dict(exact_orders=0, exact_groups=0, urge_orders=0,
                    high_freq_orders=0, high_freq_groups=0,
                    similar_pairs=0, similar_orders=0)
    tot = dup = high = mid = 0

    for m in months:
        d = D.load_month(args.year, m)
        total = len(d)
        s1, s1g = D.strategy1_exact(d)
        s2 = D.strategy2_keyword(d)
        s3, s3_groups, _freq, s3_f4 = D.strategy3_frequency(d)
        s4, s4_pairs, s4_comms, _sim = D.strategy4_similarity(d)

        union = s1 | s2 | s3 | s4
        hi = s1 | s2 | s3_f4
        mi = union - hi

        # 去重清单涉及的小区（跨月按小区名去重）
        if len(union):
            sub = d.loc[sorted(union)]
            names = sub["community_name"].dropna().astype(str)
            dup_communities |= set(n for n in names if n and n != "无")
            for c in sub["category_14"].dropna().astype(str):
                if c and c != "无":
                    cat_cnt[c] = cat_cnt.get(c, 0) + 1
            for c in names:
                if c and c != "无":
                    com_cnt[c] = com_cnt.get(c, 0) + 1
            dup_texts.extend(D._head_text(t) for t in sub["content"].tolist())
        all_comms_s4 |= {c for c in s4_comms if isinstance(c, str) and c}

        strategy["exact_orders"] += len(s1)
        strategy["exact_groups"] += s1g
        strategy["urge_orders"] += len(s2)
        strategy["high_freq_orders"] += len(s3)
        strategy["high_freq_groups"] += len(s3_groups)
        strategy["similar_pairs"] += len(s4_pairs)
        strategy["similar_orders"] += len(s4)

        tot += total
        dup += len(union)
        high += len(hi)
        mid += len(mi)

        monthly.append({
            "month": f"{args.year}年{m}月", "total": total,
            "repeat": len(union), "rate": round(len(union) / total * 100, 1) if total else 0.0,
            "exact": len(s1), "exact_groups": s1g,
            "urge": len(s2),
            "high_freq": len(s3), "high_freq_groups": len(s3_groups),
            "similar": len(s4_pairs), "similar_communities": len(s4_comms),
            "priority_high": len(hi), "priority_medium": len(mi), "priority_low": 0,
        })
        print(f"[{args.year}-{m}] 总量 {total} | 重复 {len(union)} | 高 {len(hi)} / 中 {len(mi)}")

    # 类别分布 / 热点小区 / 高频关键词（供《投诉去重识别方法论说明》等引用）
    cats = [{"category": k, "count": v, "share": round(v / dup * 100, 1) if dup else 0.0}
            for k, v in sorted(cat_cnt.items(), key=lambda kv: -kv[1])]
    top_com = [{"rank": i, "community": k, "count": v}
               for i, (k, v) in enumerate(
                   sorted(com_cnt.items(), key=lambda kv: (-kv[1], str(kv[0])))[:10], 1)]

    kw = {}
    try:
        import jieba
        for t in dup_texts:
            for w in jieba.lcut(t or ""):
                w = w.strip()
                if len(w) > 1 and w not in D.STOPWORDS and w not in STOP_EXTRA and not w.isdigit():
                    kw[w] = kw.get(w, 0) + 1
    except ImportError:
        pass
    keywords = [{"rank": i, "word": k, "count": v}
                for i, (k, v) in enumerate(
                    sorted(kw.items(), key=lambda kv: -kv[1])[:10], 1)]

    out = {
        "period": f"{args.year}年{a}-{b}月（{b} 个月合计）",
        "months": months,
        "total_orders": tot,
        "total_repeats": dup,
        "overall_rate": round(dup / tot * 100, 1) if tot else 0.0,
        "communities_involved": len(dup_communities),
        "strategy_totals": strategy,
        "priority_distribution": {"高": high, "中": mid, "低": 0},
        "similar_communities_total": len(all_comms_s4),
        "categories": cats,
        "top_communities": top_com,
        "keywords": keywords,
        "monthly": monthly,
        "source": "scripts/dedup_monthly.py（S1-S4 唯一判定口径源）",
    }
    print(f"\n合计 {tot} 条 / 重复 {dup} 条（{out['overall_rate']}%）"
          f" | 高 {high} 中 {mid} | 涉及小区 {len(dup_communities)}")
    for k, v in strategy.items():
        print(f"  {k} = {v}")

    if args.dry_run:
        return
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 已写入 {OUT}")


if __name__ == "__main__":
    main()
