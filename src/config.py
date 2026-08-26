import os
from dotenv import load_dotenv

load_dotenv()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
API_BEARER_TOKEN = os.getenv("API_BEARER_TOKEN", "xuhui-demo-2026")
DB_PATH = os.getenv("DB_PATH", "./data/xuhui_complaints.db")
LLM_TIMEOUT_MS = int(os.getenv("LLM_TIMEOUT_MS", "2000"))
QUERY_TIMEOUT_MS = int(os.getenv("QUERY_TIMEOUT_MS", "3000"))
SESSION_TIMEOUT_MIN = int(os.getenv("SESSION_TIMEOUT_MIN", "30"))

STANDARD_CATEGORIES = [
    "停车管理", "房屋维修", "邻里纠纷", "房屋违规使用",
    "业主大会/业委会", "消防管理", "群租管理", "物业安保",
    "旧住房改造", "清洁卫生", "物业收费", "物业服务态度",
    "房屋交易纠纷", "其他"
]

STANDARD_STREETS = [
    "漕河泾", "长桥", "徐家汇", "田林", "枫林路",
    "斜土路", "龙华", "康健新村", "天平路", "湖南路",
    "虹梅路", "凌云路", "华泾镇"
]

VALID_ORDER_TYPES = ["投诉举报类", "求助类"]
