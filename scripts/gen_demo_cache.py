"""
预缓存生成脚本(阶段8)
====================
为7个预设演示问题预生成结果 JSON 和文字总结 TXT,存储到 demo_cache/ 目录。
演示时若实时查询超时或失败,直接返回缓存结果,确保现场稳定。

用法:
    python3 scripts/gen_demo_cache.py
    # 或带 LLM(配置 .env 中 DASHSCOPE_API_KEY 后,文字总结会更智能)
"""
import os
import sys
import time
import json

# 把项目根目录加入 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.query_functions import (
    get_summary, get_trend, get_ranking, get_category_detail,
    get_comparison, get_hotspot, get_repeat,
)
from src.llm_client import llm_client
from src.cache_manager import save_cache, load_cache, CACHE_DIR
from src.main import template_summarize, dispatch_query, classify_intent


# ============================================================
# 7 个预设问题及其对应的直接查询参数(绕过意图分类,直接调用)
# ============================================================
PRESET_QUERIES = [
    # (cache_key, intent, question, query_fn, args, kwargs)
    ("q1_summary", "summary",
     "这个月全区投诉情况怎么样？",
     get_summary, (2026, 7), {}),
    ("q2_trend", "trend",
     "今年的投诉量和去年比降了没有？",
     get_trend, (2026,), {"dimension": "total"}),
    ("q3_ranking", "ranking",
     "本月投诉量最多的5个街道是哪些？",
     get_ranking, (2026, "street"), {"month": 7, "top_n": 5}),
    ("q4_category", "category",
     "停车类投诉主要集中在哪些小区？",
     get_category_detail, ("停车管理", 2026), {"month": 7, "group_by": "community", "top_n": 10}),
    ("q5_comparison", "comparison",
     "徐房集团和城投集团今年表现怎么样？",
     get_comparison, ("enterprise", ["徐房集团", "城投集团"], 2026), {}),
    ("q6_repeat", "repeat",
     "重复投诉率是多少？哪些小区最严重？",
     get_repeat, (2026, 1), {}),
    ("q7_hotspot", "hotspot",
     "哪些小区今年投诉增长最快？",
     get_hotspot, (2026,), {"metric": "growth", "top_n": 20}),
]


def gen_one(cache_key: str, intent: str, question: str, fn, args, kwargs) -> dict:
    """生成一个问题的缓存"""
    t0 = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
    except Exception as e:
        print(f"  [ERROR] 调用 {fn.__name__} 失败: {e}")
        return {"ok": False, "cache_key": cache_key, "err": str(e)}

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    # 文字总结:优先 LLM,失败走模板
    reply = ""
    if llm_client.available():
        try:
            slim = {k: v for k, v in result.items() if not str(k).startswith("_")}
            reply = llm_client.summarize_result(question, slim)
        except Exception as e:
            print(f"  [WARN] LLM 总结失败,走模板: {e}")
            reply = ""
    if not reply:
        reply = template_summarize(intent, question, result)

    # repeat / property 详情:补小区表格说明
    if intent == "repeat" and result.get("_table_communities"):
        reply = reply + "\n\n【重复投诉 Top 小区】"
    if intent == "property" and result.get("enterprise") and result.get("_table_communities"):
        reply = reply + "\n\n【该企业服务小区投诉排行】"

    # 保存
    try:
        save_cache(cache_key, result, reply)
    except Exception as e:
        print(f"  [ERROR] 保存缓存失败 {cache_key}: {e}")
        return {"ok": False, "cache_key": cache_key, "err": str(e)}

    print(f"  [OK] {cache_key}  intent={intent}  elapsed={elapsed_ms}ms  "
          f"reply_head={reply[:50]}...")
    return {"ok": True, "cache_key": cache_key, "elapsed_ms": elapsed_ms,
            "reply_len": len(reply), "intent": intent}


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    print(f"=== 预缓存生成开始 ===")
    print(f"  LLM 可用: {llm_client.available()}")
    print(f"  缓存目录: {CACHE_DIR}")
    print(f"  预设问题数: {len(PRESET_QUERIES)}")
    print()

    results = []
    for cache_key, intent, question, fn, args, kwargs in PRESET_QUERIES:
        print(f"→ [{cache_key}] {question}")
        r = gen_one(cache_key, intent, question, fn, args, kwargs)
        r["question"] = question
        results.append(r)

    # 汇总
    ok = sum(1 for r in results if r.get("ok"))
    fail = len(results) - ok
    total_elapsed = sum(r.get("elapsed_ms", 0) for r in results)
    print()
    print(f"=== 预缓存生成完成 ===")
    print(f"  成功: {ok} / {len(results)}, 失败: {fail}, 总耗时: {total_elapsed}ms")
    print(f"  缓存目录: {CACHE_DIR}")

    # 列出文件
    if os.path.isdir(CACHE_DIR):
        files = sorted(os.listdir(CACHE_DIR))
        print(f"  缓存文件 ({len(files)} 个):")
        for f in files:
            size = os.path.getsize(os.path.join(CACHE_DIR, f))
            print(f"    {f}  ({size} bytes)")

    # 写一份索引文件
    index_path = os.path.join(CACHE_DIR, "_index.json")
    index = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "llm_available": llm_client.available(),
        "total": len(results),
        "ok": ok,
        "fail": fail,
        "items": [
            {
                "cache_key": r.get("cache_key"),
                "intent": r.get("intent"),
                "question": r.get("question"),
                "ok": r.get("ok"),
                "elapsed_ms": r.get("elapsed_ms"),
                "reply_len": r.get("reply_len", 0),
            } for r in results
        ]
    }
    try:
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        print(f"  索引文件: {index_path}")
    except Exception as e:
        print(f"  [WARN] 写索引失败: {e}")

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
