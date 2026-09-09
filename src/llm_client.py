import json
import time
from typing import Dict, Any, Optional, List

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from src.config import DASHSCOPE_API_KEY, LLM_TIMEOUT_MS

# ============================================================
# 系统 Prompt:定义 AI 角色 + 数据驱动 + 上下文感知
# ============================================================
SYSTEM_PROMPT = """你是「徐汇区物业投诉数据分析智能助手」，专门服务于徐汇区12345热线物业投诉数据的查询与分析。

【你的职责】
1. 基于数据库查询结果，生成专业、准确的数据分析总结
2. 结合对话上下文理解用户意图，保持多轮对话的连贯性
3. 每次回答前，系统已从数据库读取相关统计数据，你只能基于这些数据回答

【数据来源与规范】
- 数据库：徐汇区12345热线投诉数据（数据范围：2024年1月至今，含6万余条记录）
- 预计算聚合表：monthly_stats（月度统计）、category_monthly_stats（类别月度）、street_monthly_stats（街道月度）、enterprise_stats（企业统计）、community_stats（小区统计）
- ⚠️ 严禁编造数据！只使用下方「本次查询结果」中的数字
- 如查询结果为空或异常，如实告知用户并建议换一种问法

【回答规范】
1. 先给出核心数字（总量、同比/环比变化率）
2. 再列出重点发现（Top3排名、异常增长项、对比差异）
3. 最后给一句简短建议或关注方向
4. 语言简洁专业，不超过200字
5. 数字带单位（件、%），变化方向明确（增长/下降）

【上下文感知规则】
- 继承最近3轮对话的时间参数（year、month）
- 当用户追问"那XX类呢"时，自动继承上一轮的时间范围
- 当用户追问"那个街道/小区呢"时，自动继承上一轮的维度
- 如果用户未指定时间，默认查询最新月度数据"""

# ============================================================
# LLM 客户端
# ============================================================
class LLMClient:
    def __init__(self):
        self.client = None
        if OpenAI and DASHSCOPE_API_KEY and DASHSCOPE_API_KEY.startswith("sk-"):
            try:
                self.client = OpenAI(
                    api_key=DASHSCOPE_API_KEY,
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
                )
            except Exception:
                self.client = None

    def available(self) -> bool:
        return self.client is not None

    def classify_intent(self, message: str) -> Dict[str, Any]:
        fallback = {"function": "unknown", "reply": "建议问法：本月概况、投诉趋势、街道排行、停车分析等"}
        if not self.available():
            return fallback

        system_prompt = """你是一个意图分类器。根据用户问题，从以下函数中选择一个并提取参数：
- get_summary(year, month?): 综合概况
- get_trend(year, dimension?, dimension_value?): 趋势查询
- get_ranking(year, dimension, month?, top_n?): 排行查询
- get_category_detail(category, year, month?, group_by?): 类别分析
- get_comparison(entity_type, entity_names, year, month?): 对比查询
- get_hotspot(year, metric?, top_n?): 热点查询
- get_repeat(year, half): 重复投诉
- get_property(year, month?, enterprise?, top_n?): 物业企业
返回JSON格式：{"function": "函数名", "params": {...}}
如果无法匹配，返回：{"function": "unknown", "reply": "建议问法"}"""

        try:
            response = self.client.chat.completions.create(
                model="qwen-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=LLM_TIMEOUT_MS / 1000
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception:
            return fallback

    def _build_context_summary(self, context: Dict[str, Any]) -> str:
        """将会话上下文参数格式化为文本"""
        if not context:
            return "（无上下文，本次为首次对话）"
        parts = []
        if "year" in context:
            parts.append(f"年份={context['year']}")
        if "month" in context:
            parts.append(f"月份={context['month']}")
        if "dimension" in context:
            parts.append(f"维度={context['dimension']}")
        if "category" in context:
            parts.append(f"类别={context['category']}")
        if "street" in context:
            parts.append(f"街道={context['street']}")
        return "、".join(parts) if parts else "（无上下文）"

    def _build_history_messages(self, history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """将对话历史转为 LLM messages 格式(user/assistant 交替)"""
        msgs = []
        for turn in history:
            user_msg = turn.get("message", "")
            assistant_reply = turn.get("reply", "")
            if user_msg:
                msgs.append({"role": "user", "content": user_msg})
            if assistant_reply:
                msgs.append({"role": "assistant", "content": assistant_reply})
        return msgs

    def summarize_result(self, question: str, query_result: Dict[str, Any],
                         history: List[Dict[str, Any]] = None,
                         context: Dict[str, Any] = None) -> str:
        """基于数据库查询结果 + 对话上下文 + 历史记录，生成智能总结"""
        fallback = "查询结果已生成，详见表格数据。"
        if not self.available():
            return fallback

        try:
            # 构建多轮对话 messages
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]

            # 注入对话历史(最近3轮 user/assistant 交替)
            if history:
                history_msgs = self._build_history_messages(history)
                messages.extend(history_msgs)

            # 构建当前轮 user 消息:上下文 + 查询结果 + 用户问题
            context_str = self._build_context_summary(context)
            result_str = json.dumps(query_result, ensure_ascii=False)
            user_msg = (
                f"【对话上下文】{context_str}\n"
                f"【本次数据库查询结果】\n{result_str}\n"
                f"【用户问题】{question}\n"
                f"请基于以上数据库查询结果回答用户问题。"
            )
            messages.append({"role": "user", "content": user_msg})

            response = self.client.chat.completions.create(
                model="qwen-turbo",
                messages=messages,
                temperature=0.3,
                timeout=LLM_TIMEOUT_MS / 1000
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return fallback


llm_client = LLMClient()
