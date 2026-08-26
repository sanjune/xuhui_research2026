import json
import os
from typing import Dict, Any, Optional, Tuple

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "demo_cache")

PRESET_QUESTIONS = {
    "这个月全区投诉情况怎么样？": ("q1_summary", "summary"),
    "今年的投诉量和去年比降了没有？": ("q2_trend", "trend"),
    "本月投诉量最多的5个街道是哪些？": ("q3_ranking", "ranking"),
    "停车类投诉主要集中在哪些小区？": ("q4_category", "category"),
    "徐房集团和城投集团今年表现怎么样？": ("q5_comparison", "comparison"),
    "重复投诉率是多少？哪些小区最严重？": ("q6_repeat", "repeat"),
    "哪些小区今年投诉增长最快？": ("q7_hotspot", "hotspot"),
}


def match_preset(message: str) -> Optional[Tuple[str, str]]:
    msg = message.strip()
    if msg in PRESET_QUESTIONS:
        return PRESET_QUESTIONS[msg]
    for q, (cache_key, intent) in PRESET_QUESTIONS.items():
        if len(set(msg) & set(q)) >= len(q) * 0.7:
            return cache_key, intent
    return None


def load_cache(cache_key: str) -> Optional[Tuple[Dict[str, Any], str]]:
    json_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
    txt_path = os.path.join(CACHE_DIR, f"{cache_key}_reply.txt")
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        reply = ""
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                reply = f.read().strip()
        return data, reply
    except Exception:
        return None


def save_cache(cache_key: str, data: Dict[str, Any], reply: str):
    os.makedirs(CACHE_DIR, exist_ok=True)
    json_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
    txt_path = os.path.join(CACHE_DIR, f"{cache_key}_reply.txt")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(reply)
