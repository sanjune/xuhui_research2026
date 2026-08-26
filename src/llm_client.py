import json
import time
from typing import Dict, Any, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from src.config import DASHSCOPE_API_KEY, LLM_TIMEOUT_MS


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

    def summarize_result(self, question: str, query_result: Dict[str, Any]) -> str:
        fallback_templates = {
            "total": f"根据统计数据，查询结果已生成。",
            "summary": f"徐汇区投诉统计结果已整理，详见表格数据。"
        }
        fallback = fallback_templates.get("summary", "查询结果已生成。")
        if not self.available():
            return fallback

        system_prompt = """你是徐汇区物业投诉数据分析助手。根据查询结果，用简洁专业的语言生成分析总结。
要求：
1. 先给出核心数字（总量、变化率）
2. 再列出重点发现（Top3、异常项）
3. 最后给一句简短建议（可选）
4. 语言简洁，不超过150字
5. 不要编造数据，只使用提供的结果"""

        try:
            user_msg = f"用户问题：{question}\n查询结果：{json.dumps(query_result, ensure_ascii=False)}"
            response = self.client.chat.completions.create(
                model="qwen-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.3,
                timeout=LLM_TIMEOUT_MS / 1000
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return fallback


llm_client = LLMClient()
