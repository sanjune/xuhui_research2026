#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""词云词表导出 —— 供人工审核「中性词」删除清单。

复用 `build_street_dataset.py` 的**同一套**分词/停用词/案件级归并逻辑
（keywords_of + case_representatives + STOP），只把 TopN 从 24 放大到 CAND_N，
从而同时拿到：
  · 当前词云实际展示的词（前 24 名）
  · 删词后会补位上来的候选词（第 25 名以后）

口径与词云完全一致：2026年1-8月 · 案件级归并（同一诉求只计首单）· 已剥离引用块。

产出：scripts/wordcloud_terms.json
      { "meta": {...}, "streets": {街镇: [{"word","cnt","rank"}]} }

用法：PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/dump_wordcloud_terms.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import build_street_dataset as B  # noqa: E402  唯一词云口径源

CAND_N = 60           # 候选池深度：前 24 = 当前展示，25+ = 补位候选
OUT = os.path.join(SCRIPTS, "wordcloud_terms.json")


def main():
    df = B.load_data()
    main_df = df[df["street"] != "无"].copy()
    rep_ids, _, n_cases, n_merged = B.case_representatives(df)
    print(f"案件级归并：{len(df)} 笔 → {n_cases} 案件（归并 {n_merged} 笔）")

    n26 = B.period(main_df, B.YEAR_NOW, 1, B.MONTH_NOW)
    print(f"2026年1-8月 纳入分词：{len(n26)} 笔")

    streets = {}
    for st in sorted(main_df["street"].unique()):
        s26 = n26[n26["street"] == st]
        kws = B.keywords_of(s26, topn=CAND_N, street=st, rep_ids=rep_ids)
        streets[st] = [{"word": x["word"], "cnt": x["cnt"], "rank": i + 1}
                       for i, x in enumerate(kws)]
        print(f"  {st}: 候选 {len(kws)} 词")

    uniq = {x["word"] for v in streets.values() for x in v}
    payload = {
        "meta": {
            "scope": "2026年1-8月",
            "unit": "案件级（同一诉求的催单/重复来电只计首单）",
            "topn_shown": B.KEYWORD_TOPN,
            "cand_n": CAND_N,
            "streets": len(streets),
            "unique_words": len(uniq),
            "source": "scripts/build_street_dataset.py → keywords_of()",
        },
        "streets": streets,
    }
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n唯一词 {len(uniq)} 个 → {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
