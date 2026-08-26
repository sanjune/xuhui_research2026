from typing import Dict, Any, Optional, List, Tuple
import re
from datetime import datetime

from src.config import STANDARD_CATEGORIES, STANDARD_STREETS

INTENT_PRIORITY = {
    "trend": 80, "repeat": 95, "hotspot": 90, "property": 85,
    "category": 88, "comparison": 75, "ranking": 60, "summary": 50,
}

INTENT_RULES = [
    ("trend", ["趋势", "走势", "变化", "降了没有", "比去年", "同比", "环比"]),
    ("repeat", ["重复投诉", "重复率", "重复", "反复", "多次", "催办"]),
    ("hotspot", ["增长最快", "异常", "高发", "热点问题"]),
    ("property", ["物业公司", "哪个物业", "物业企业", "企业", "徐房集团", "城投集团", "集团"]),
    ("category", ["停车类投诉", "停车管理", "停车类", "群租类", "群租管理", "停车问题", "停车", "群租", "维修", "纠纷", "类投诉", "类的", "房屋维修", "邻里纠纷", "房屋违规使用", "业主大会", "业委会", "消防管理", "物业安保", "旧住房改造", "清洁卫生", "物业收费", "物业服务态度", "房屋交易纠纷"]),
    ("comparison", ["对比", "比较", "vs", "表现怎么样", "哪个好", "和..比"]),
    ("ranking", ["排名", "排行", "top", "最多的", "最多的5", "最少", "最高", "最低", "前几", "前多少", "哪些街道", "哪些小区", "哪些物业", "哪个街道", "哪个小区", "最多的街道", "最多的小区"]),
    ("summary", ["整体", "概况", "全区情况", "全区", "整个区", "全区投诉"]),
]


def rule_based_intent(message: str) -> Tuple[Optional[str], Dict[str, Any]]:
    msg = message
    matched = []
    for intent_id, keywords in INTENT_RULES:
        best_kw_len = 0
        for kw in keywords:
            if not kw:
                continue
            if kw in msg and len(kw) > best_kw_len:
                best_kw_len = len(kw)
        if best_kw_len > 0:
            score = INTENT_PRIORITY.get(intent_id, 0) + best_kw_len * 2
            matched.append((intent_id, score))
    has_multi_entity = bool(re.search(r"(和|与|跟|对比|比较|vs).{0,6}(集团|物业|街道|小区)", msg)) or bool(
        re.search(r"(集团|物业|街道|小区).{0,6}(和|与|跟).{0,6}(集团|物业|街道|小区)", msg))
    if has_multi_entity:
        for i, (iid, score) in enumerate(matched):
            if iid == "comparison":
                matched[i] = (iid, score + 50)
    if not matched:
        return None, {}
    matched.sort(key=lambda x: -x[1])
    return matched[0][0], {}


def extract_params(message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    params = {}
    now = datetime.now()

    if re.search(r"今年", message):
        params["year"] = 2026
    elif re.search(r"去年", message):
        params["year"] = 2025
    else:
        year_match = re.search(r"(2024|2025|2026)", message)
        if year_match:
            params["year"] = int(year_match.group(1))

    if re.search(r"本月|这个月", message):
        params["month"] = 7
    elif re.search(r"上月|上个月", message):
        params["month"] = 6
    else:
        month_match = re.search(r"(\d{1,2})月", message)
        if month_match:
            m = int(month_match.group(1))
            if 1 <= m <= 12:
                params["month"] = m

    for cat in STANDARD_CATEGORIES:
        if cat[:2] in message or cat in message:
            params["category"] = cat
            break

    for st in STANDARD_STREETS:
        if st in message:
            params["street"] = st
            break

    top_match = re.search(r"top\s*(\d+)|前\s*(\d+)|最多的\s*(\d+)", message, re.IGNORECASE)
    if top_match:
        for g in top_match.groups():
            if g:
                params["top_n"] = int(g)
                break

    half_match = re.search(r"(上|下)半年", message)
    if half_match:
        params["half"] = 1 if half_match.group(1) == "上" else 2

    if context:
        for k, v in context.items():
            if k not in params and k in ("year", "month", "dimension"):
                params[k] = v

    if "year" not in params:
        params["year"] = 2026

    return params


def classify_intent(message: str, context: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
    intent, _ = rule_based_intent(message)
    params = extract_params(message, context)

    if intent is None:
        return "unknown", params

    return intent, params
