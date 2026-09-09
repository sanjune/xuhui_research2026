import os
import time
import json
import sqlite3
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from src.config import (
    DASHSCOPE_API_KEY, API_BEARER_TOKEN, DB_PATH,
    LLM_TIMEOUT_MS, QUERY_TIMEOUT_MS, SESSION_TIMEOUT_MIN,
    STANDARD_CATEGORIES, STANDARD_STREETS,
)
from src.intent_classifier import classify_intent, rule_based_intent, extract_params
from src.session_manager import session_manager
from src.cache_manager import match_preset, load_cache, save_cache
from src.llm_client import llm_client
from src.query_functions import (
    get_summary, get_trend, get_ranking, get_category_detail,
    get_comparison, get_hotspot, get_repeat, get_property,
    get_conn, pct_change_str,
)

# ============================================================
# 配置与日志
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ABS_DB_PATH = DB_PATH if os.path.isabs(DB_PATH) else os.path.join(BASE_DIR, DB_PATH)
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "access.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("xuhui-ai")

app = FastAPI(title="徐汇区物业投诉AI智能体", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态前端挂载(可选,访问 / 时返回 H5 页面)
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Bearer Token 鉴权
bearer_scheme = HTTPBearer(auto_error=False)


async def verify_token(credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)):
    """API 鉴权:Bearer Token 校验"""
    if not credentials or credentials.credentials != API_BEARER_TOKEN:
        raise HTTPException(status_code=401, detail="未授权:无效的 Bearer Token")
    return credentials


# ============================================================
# 请求/响应模型
# ============================================================
class ChatRequest(BaseModel):
    message: str
    session_id: str = ""


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    table: Optional[Dict[str, Any]] = None
    chart: Optional[Dict[str, Any]] = None
    raw_intent: str
    query_time_ms: int


# ============================================================
# 实体名提取(用于对比/物业查询)
# ============================================================
ENTERPRISE_KEYWORDS = [
    "徐房集团", "城投集团", "高建物业", "衡复物业", "中企物业",
    "上房物业", "中星集团", "西部集团", "新长宁集团", "新曹杨集团",
]

ENTERPRISE_ALIASES = {
    "徐房": "徐房集团", "城投": "城投集团",
    "高建": "高建物业", "衡复": "衡复物业",
}


def extract_entities(message: str) -> List[str]:
    """从问题中提取多个实体名(集团/物业企业)"""
    found = []
    for ent in ENTERPRISE_KEYWORDS:
        if ent in message and ent not in found:
            found.append(ent)
    for short, full in ENTERPRISE_ALIASES.items():
        if short in message and full not in found:
            # 仅在完整名也不在 message 时才用简称补
            if full not in message:
                found.append(full)
    return found


def extract_enterprise_single(message: str) -> Optional[str]:
    """提取单个企业名(用于 get_property 详情)"""
    ents = extract_entities(message)
    if ents:
        return ents[0]
    # 兜底:看问题里是否含"物业"+"X公司"
    import re
    m = re.search(r"([\u4e00-\u9fa5]{2,8}(?:物业|集团|公司))", message)
    if m:
        return m.group(1)
    return None


def infer_dimension(message: str, intent: str) -> str:
    """根据问题推断 ranking/category 的维度"""
    if intent == "ranking":
        if "街道" in message or "哪个街道" in message:
            return "street"
        if "小区" in message or "哪些小区" in message:
            return "community"
        if "物业" in message or "企业" in message or "公司" in message:
            return "enterprise"
        if any(c in message for c in STANDARD_CATEGORIES):
            return "category"
        return "street"  # 默认街道
    return "street"


def infer_group_by(message: str) -> str:
    """根据问题推断 category_detail 的分组维度"""
    if "街道" in message and "小区" not in message:
        return "street"
    if "物业" in message or "企业" in message or "公司" in message:
        return "enterprise"
    return "community"  # 默认按小区


def infer_metric(message: str) -> str:
    """根据问题推断 hotspot 的指标"""
    if "增长最快" in message or "增长" in message or "同比" in message:
        return "growth"
    if "密度" in message or "户均" in message or "小区均" in message:
        return "density"
    if "最多" in message or "数量" in message or "最高" in message:
        return "volume"
    return "growth"


def infer_trend_dimension(message: str) -> Tuple[str, Optional[str]]:
    """根据问题推断 trend 查询的 dimension 和 dimension_value"""
    if "类别" in message or "分类" in message:
        for cat in STANDARD_CATEGORIES:
            if cat in message:
                return "category", cat
    if "街道" in message:
        for st in STANDARD_STREETS:
            if st in message:
                return "street", st
    return "total", None


# ============================================================
# 调度:根据意图执行对应查询
# ============================================================
def dispatch_query(intent: str, params: Dict[str, Any], message: str) -> Tuple[Dict[str, Any], str]:
    """根据意图调度查询函数,返回 (结果, 缓存key)"""
    year = int(params.get("year", 2026))
    month = params.get("month")
    month_int = int(month) if month else None
    top_n = int(params.get("top_n", 10)) if params.get("top_n") else 10

    cache_key_map = {
        "summary": "q1_summary", "trend": "q2_trend", "ranking": "q3_ranking",
        "category": "q4_category", "comparison": "q5_comparison",
        "repeat": "q6_repeat", "hotspot": "q7_hotspot", "property": "q_property",
    }
    cache_key = cache_key_map.get(intent, "")

    if intent == "summary":
        result = get_summary(year, month_int)
    elif intent == "trend":
        dimension, dimension_value = infer_trend_dimension(message)
        result = get_trend(year, dimension=dimension, dimension_value=dimension_value)
    elif intent == "ranking":
        dimension = infer_dimension(message, intent)
        result = get_ranking(year, dimension, month=month_int, top_n=top_n)
    elif intent == "category":
        category = params.get("category") or "停车管理"
        group_by = infer_group_by(message)
        result = get_category_detail(category, year, month=month_int, group_by=group_by, top_n=top_n)
    elif intent == "comparison":
        entities = extract_entities(message)
        if not entities or len(entities) < 2:
            # 单实体降级为 property 详情
            single = extract_enterprise_single(message)
            if single:
                result = get_property(year, month=month_int, enterprise=single, top_n=top_n)
                cache_key = "q_property"
            else:
                result = get_property(year, month=month_int, top_n=top_n)
                cache_key = "q_property"
            return result, cache_key
        result = get_comparison("enterprise", entities, year, month=month_int)
    elif intent == "hotspot":
        metric = infer_metric(message)
        result = get_hotspot(year, metric=metric, top_n=top_n)
    elif intent == "repeat":
        half = int(params.get("half", 1))
        result = get_repeat(year, half=half)
    elif intent == "property":
        single = extract_enterprise_single(message)
        if single and ("详情" in message or "表现" in message or single in message):
            result = get_property(year, month=month_int, enterprise=single, top_n=top_n)
        else:
            result = get_property(year, month=month_int, top_n=top_n)
    else:
        result = {"error": "unsupported_intent", "_table": None}

    return result, cache_key


# ============================================================
# 模板兜底总结(LLM 不可用 / 超时时使用)
# ============================================================
def template_summarize(intent: str, question: str, result: Dict[str, Any]) -> str:
    """LLM 不可用时,用预设模板生成简洁总结"""
    try:
        if intent == "summary":
            period = result.get("period", "")
            total = result.get("total", 0)
            yoy = result.get("yoy_change", "—")
            mom = result.get("mom_change", "—")
            cats = result.get("top3_categories", [])
            strs = result.get("top3_streets", [])
            cat_str = "、".join(f"{c['name']}({c['count']}件)" for c in cats[:3]) if cats else "—"
            st_str = "、".join(f"{s['name']}({s['count']}件)" for s in strs[:3]) if strs else "—"
            return (f"{period}，徐汇区共受理12345物业类投诉{total:,}件，"
                    f"同比{yoy}{', 环比' + mom if mom != '—' else ''}。"
                    f"投诉量前三类别：{cat_str}。投诉量前三街道：{st_str}。")

        if intent == "trend":
            period = result.get("period", "")
            cur = result.get("total_current", 0)
            prev = result.get("total_compare", 0)
            yoy = result.get("yoy_change", "—")
            dim = result.get("dim_label", "全区总量")
            return (f"{period}，{dim}共{cur:,}件，去年同期{prev:,}件，"
                    f"同比{yoy}。详见月度趋势表格。")

        if intent == "ranking":
            period = result.get("period", "")
            dim = result.get("dimension", "")
            ranking = result.get("ranking", [])
            if not ranking:
                return f"{period}暂无{dim}排行数据。"
            top3 = ranking[:3]
            top_str = "、".join(f"{r['name']}({r['count']}件)" for r in top3)
            return f"{period}{dim}投诉量Top3：{top_str}。完整排行见下表。"

        if intent == "category":
            period = result.get("period", "")
            cat = result.get("category", "")
            total = result.get("total", 0)
            cc = result.get("community_count", 0)
            subs = result.get("sub_issues", [])
            sub_str = "、".join(f"{s['name']}({s['count']}件)" for s in subs[:3]) if subs else "—"
            return (f"{period}，{cat}类投诉共{total}件，涉及{cc}个小区。"
                    f"主要子问题：{sub_str}。详见下表。")

        if intent == "comparison":
            period = result.get("period", "")
            entities = result.get("entities", [])
            if not entities:
                return f"{period}未匹配到对比实体。"
            lines = []
            for e in entities:
                lines.append(
                    f"{e['entity_name']}(匹配{len(e.get('matched_names', []))}家)"
                    f"：{e['total']}件/{e['community_count']}小区/小区均{e['avg_per_community']}"
                )
            return f"{period}对比：\n" + "\n".join(lines)

        if intent == "hotspot":
            metric = result.get("metric", "")
            hots = result.get("hotspots", [])
            if not hots:
                return f"未识别到{metric}热点小区。"
            top3 = hots[:3]
            top_str = "、".join(
                f"{h['community']}({h['count']}件,{h['yoy_change']})" for h in top3
            )
            return f"{metric}Top3：{top_str}。完整热点列表见下表。"

        if intent == "repeat":
            period = result.get("period", "")
            total = result.get("total_orders", 0)
            rep = result.get("repeat_orders", 0)
            rate = result.get("repeat_rate", "0%")
            cats = result.get("top_categories", [])
            coms = result.get("top_communities", [])
            cat_str = "、".join(f"{c['category']}({c['repeat_count']}件)" for c in cats[:3]) if cats else "—"
            com_str = "、".join(f"{c['community']}({c['repeat_count']}件)" for c in coms[:3]) if coms else "—"
            return (f"{period}，工单总量{total:,}件，重复投诉{rep}件(近似)，"
                    f"重复率{rate}。Top类别：{cat_str}。Top小区：{com_str}。")

        if intent == "property":
            if result.get("enterprise"):
                period = result.get("period", "")
                ent = result.get("enterprise", "")
                matched = result.get("matched_names", [])
                total = result.get("total", 0)
                cc = result.get("community_count", 0)
                avg = result.get("avg_per_community", 0)
                matched_str = " / ".join(matched[:3]) if matched else "—"
                return (f"{period}，{ent}实际匹配到：{matched_str}，"
                        f"投诉总量{total}件，服务小区{cc}个，小区均{avg}件。"
                        f"详见下表。")
            period = result.get("period", "")
            ranking = result.get("ranking", [])
            if not ranking:
                return f"{period}暂无物业企业排行数据。"
            top3 = ranking[:3]
            top_str = "、".join(
                f"{r['enterprise']}({r['total']}件,均{r['avg_per_community']})" for r in top3
            )
            return f"{period}物业企业投诉排行Top3：{top_str}。完整排行见下表。"

        return "查询结果已生成，详见下表。"
    except Exception as e:
        logger.warning(f"template_summarize 失败: {e}")
        return "查询结果已生成，详见下表。"


# ============================================================
# 主接口:POST /api/chat
# ============================================================
@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, credentials: HTTPAuthorizationCredentials = Depends(verify_token)):
    t_start = time.perf_counter()
    message = (req.message or "").strip()
    session_id = req.session_id or f"s_{int(time.time())}_{id(req)}"

    if not message:
        return ChatResponse(
            session_id=session_id,
            reply="请输入您要查询的问题，例如：本月哪个街道投诉最多？",
            table=None,
            chart=None,
            raw_intent="empty",
            query_time_ms=0,
        )

    # 1. 优先匹配预设问题(走缓存兜底)
    preset = match_preset(message)
    use_cache_fallback = False

    # 2. 获取上下文
    ctx = session_manager.get_context(session_id)

    # 3. 意图分类(规则优先,LLM 兜底)
    intent, params = classify_intent(message, ctx)

    # LLM 兜底:规则未匹配时
    if intent == "unknown" and llm_client.available():
        try:
            llm_result = llm_client.classify_intent(message)
            if isinstance(llm_result, dict) and llm_result.get("function") not in (None, "unknown"):
                llm_func = llm_result.get("function", "")
                # 把 get_xxx 映射回 intent id
                intent_map = {
                    "get_summary": "summary", "get_trend": "trend",
                    "get_ranking": "ranking", "get_category_detail": "category",
                    "get_comparison": "comparison", "get_hotspot": "hotspot",
                    "get_repeat": "repeat", "get_property": "property",
                }
                if llm_func in intent_map:
                    intent = intent_map[llm_func]
                    llm_params = llm_result.get("params", {}) or {}
                    # 合并 LLM 提取的参数(不覆盖已提取的)
                    for k, v in llm_params.items():
                        if k not in params and v is not None:
                            params[k] = v
        except Exception as e:
            logger.warning(f"LLM 意图兜底失败: {e}")

    # 4. 未知意图:返回友好引导
    if intent == "unknown":
        elapsed = int((time.perf_counter() - t_start) * 1000)
        reply = ("您的问题我暂时无法理解，可以试试问：\n"
                 "· 这个月全区投诉情况怎么样？\n"
                 "· 本月投诉量最多的5个街道是哪些？\n"
                 "· 停车类投诉主要集中在哪些小区？\n"
                 "· 重复投诉率是多少？")
        logger.info(f"[{session_id}] intent=unknown msg={message[:50]} elapsed={elapsed}ms")
        return ChatResponse(
            session_id=session_id,
            reply=reply,
            table=None,
            chart=None,
            raw_intent="unknown",
            query_time_ms=elapsed,
        )

    # 5. 调度执行查询
    try:
        result, cache_key = dispatch_query(intent, params, message)
    except Exception as e:
        logger.exception(f"dispatch_query 异常: intent={intent} msg={message[:50]} err={e}")
        elapsed = int((time.perf_counter() - t_start) * 1000)
        # 尝试走缓存兜底
        if preset:
            cached = load_cache(preset[0])
            if cached:
                data, reply = cached
                return ChatResponse(
                    session_id=session_id,
                    reply=reply or template_summarize(intent, message, data),
                    table=data.get("_table") if isinstance(data, dict) else None,
                    chart=None,
                    raw_intent=intent,
                    query_time_ms=elapsed,
                )
        return ChatResponse(
            session_id=session_id,
            reply="系统暂时无法查询，请稍后重试。",
            table=None,
            chart=None,
            raw_intent=intent,
            query_time_ms=elapsed,
        )

    # 6. 超时兜底:超过 QUERY_TIMEOUT_MS 时用缓存
    elapsed_ms = (time.perf_counter() - t_start) * 1000
    if elapsed_ms > QUERY_TIMEOUT_MS and preset:
        cached = load_cache(preset[0])
        if cached:
            data, reply = cached
            if isinstance(data, dict) and not result.get("_table"):
                result = data
            if reply:
                elapsed = int(elapsed_ms)
                logger.info(f"[{session_id}] intent={intent} (cache fallback) elapsed={elapsed}ms")
                session_manager.add_history(session_id, message, intent, params, reply=reply)
                return ChatResponse(
                    session_id=session_id,
                    reply=reply,
                    table=result.get("_table") if isinstance(result, dict) else None,
                    chart=None,
                    raw_intent=intent,
                    query_time_ms=elapsed,
                )

    # 7. LLM 结果总结(超时则走模板)
    reply = ""
    llm_started = time.perf_counter()
    # 获取对话历史 + 上下文,注入 LLM
    history = session_manager.get_history(session_id)
    if llm_client.available():
        try:
            # 只传统计结果(剥离 _table 等内部字段),避免大对象
            slim_result = {k: v for k, v in result.items() if not k.startswith("_")}
            reply = llm_client.summarize_result(
                message, slim_result, history=history, context=ctx
            )
        except Exception as e:
            logger.warning(f"LLM summarize 失败,走模板: {e}")
            reply = ""
    if not reply:
        reply = template_summarize(intent, message, result)

    # 8. 记录会话历史+上下文继承(含本轮 reply,供下一轮 LLM 上下文使用)
    session_manager.add_history(session_id, message, intent, params, reply=reply)

    # 9. 缓存预设问题结果(若未缓存)
    if preset and cache_key:
        try:
            cached = load_cache(cache_key)
            if not cached:
                save_cache(cache_key, result, reply)
        except Exception as e:
            logger.warning(f"保存缓存失败 cache_key={cache_key}: {e}")

    elapsed = int((time.perf_counter() - t_start) * 1000)
    table = result.get("_table") if isinstance(result, dict) else None
    # 对 repeat 这种多表格场景,主表用 _table_summary
    if intent == "repeat" and isinstance(result, dict):
        table = result.get("_table_summary") or result.get("_table")
        # 拼接小区表格
        com_table = result.get("_table_communities")
        if com_table:
            reply = reply + "\n\n【重复投诉 Top 小区】"
            table = com_table
    # 对 property 详情,主表用 _table,小区列表用 _table_communities
    if intent == "property" and isinstance(result, dict) and result.get("enterprise"):
        # 详情模式:主表展示指标,_table_communities 展示小区列表(附在 reply 后)
        com_table = result.get("_table_communities")
        if com_table:
            reply = reply + "\n\n【该企业服务小区投诉排行】"
            table = com_table

    logger.info(
        f"[{session_id}] intent={intent} msg={message[:50]} "
        f"elapsed={elapsed}ms llm={int((time.perf_counter() - llm_started) * 1000)}ms"
    )

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        table=table,
        chart=None,
        raw_intent=intent,
        query_time_ms=elapsed,
    )


# ============================================================
# 健康检查:GET /api/health
# ============================================================
@app.get("/api/health")
async def health_check():
    db_connected = False
    total_records = 0
    data_range = "—"
    try:
        conn = get_conn()
        cur = conn.cursor()
        cnt = cur.execute("SELECT COUNT(*) FROM work_orders").fetchone()
        total_records = int(cnt[0]) if cnt else 0
        min_row = cur.execute(
            "SELECT year, month FROM work_orders ORDER BY year, month LIMIT 1"
        ).fetchone()
        max_row = cur.execute(
            "SELECT year, month FROM work_orders ORDER BY year DESC, month DESC LIMIT 1"
        ).fetchone()
        if min_row and max_row:
            data_range = f"{min_row[0]}.{min_row[1]:02d} - {max_row[0]}.{max_row[1]:02d}"
        db_connected = True
        conn.close()
    except Exception as e:
        logger.warning(f"health_check DB 异常: {e}")

    llm_connected = llm_client.available()

    return {
        "status": "ok" if db_connected else "degraded",
        "db_connected": db_connected,
        "llm_connected": llm_connected,
        "data_range": data_range,
        "total_records": total_records,
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================
# 前端 H5 入口:GET /
# ============================================================
@app.get("/")
async def index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"message": "frontend not found", "hint": "请访问 /docs 查看 API"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
