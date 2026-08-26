# 徐汇区物业数据AI智能体 — 开发需求文档

## 1. 项目概述

### 1.1 背景
徐汇区物业课题一期项目积累了约7万条12345热线投诉数据（2024-2026年），覆盖14类物业投诉、13个街道、200+家物业企业、800+个小区。需要开发一个可现场演示的AI对话查询工具，让领导通过手机微信直接用自然语言查询投诉统计数据。

### 1.2 目标
- 构建一个微信端可访问的AI对话查询工具
- 支持自然语言提问，返回结构化统计数据+文字总结
- 数据全程不出区级服务器，LLM不接触原始数据
- 验收现场可稳定演示7-8个预设问题

### 1.3 用户场景
验收汇报现场，领导拿出手机微信，输入"本月哪个街道投诉最多"，智能体3秒内返回排名表格+文字分析。领导继续追问"那停车类呢"，智能体理解上下文返回停车类排行。

---

## 2. 系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────┐
│              演示端（手机微信）                    │
│   企业微信自建应用 / H5聊天页面                     │
│   输入自然语言 → 看到表格+文字分析                  │
└────────────────────┬────────────────────────────┘
                     │ HTTP POST
┌────────────────────▼────────────────────────────┐
│           后端API服务（Python FastAPI）            │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ 意图理解   │→│ 查询执行  │→│ 结果生成   │      │
│  │ (LLM API) │  │(本地SQL)  │  │(LLM API) │      │
│  └──────────┘  └──────────┘  └──────────┘      │
│      ↓              ↓              ↓             │
│  只传意图文本    本地执行查询    只传统计结果        │
│  不传原始数据   不出服务器      不传原始数据        │
└────────────────────┬────────────────────────────┘
                     │ 本地查询
┌────────────────────▼────────────────────────────┐
│         数据库（SQLite）                          │
│   work_orders主表 + 5张预计算聚合表 + 数据字典     │
│   约7万条工单记录                                  │
└─────────────────────────────────────────────────┘
```

### 2.2 技术栈

| 组件 | 技术选型 | 版本要求 | 说明 |
|------|---------|---------|------|
| 数据库 | SQLite | 3.x | 7万条数据量小，零部署，单文件 |
| 数据处理 | Python pandas | 2.x | Excel合并、清洗、导入 |
| AI引擎 | 通义千问 API (Qwen-Turbo) | 最新 | 免费，每月100万token额度 |
| 后端框架 | Python FastAPI | 0.100+ | 轻量快速，自带API文档 |
| 前端 | H5页面 或 企业微信自建应用 | — | 二选一，见5.1节 |
| 部署 | 区级服务器 | — | 不上公有云 |

### 2.3 核心设计原则
1. **LLM不接触原始数据**：LLM只做意图理解和结果总结，SQL查询在后端本地执行
2. **预设模板为主**：常见问题用预设查询模板，确保演示稳定；复杂问题走LLM Function Calling兜底
3. **数据不出服务器**：LLM API调用只传意图文本和统计结果，不含明细数据

---

## 3. 数据层需求

### 3.1 数据源

三个Excel文件：

| 文件 | 记录数 | 时间范围 | 字段数 | 路径 |
|------|--------|---------|--------|------|
| 2024年市局14类.xlsx | 35,646 | 2024全年 | 27列 | 热线数据/ |
| 2025年全年、2026年1-6月市局14类.xlsx | 33,005 | 2025全年+2026H1 | 23列 | 热线数据/ |
| 2026年7月市局14类.xlsx | 2,097 | 2026年7月 | 21列 | 热线数据/ |

### 3.2 数据清洗规则

三个文件的字段不一致，需统一处理：

#### 3.2.1 字段对齐

| 统一字段名 | 2024原始字段 | 2025-2026原始字段 | 2026.7原始字段 | 处理方式 |
|------------|-------------|-------------------|---------------|---------|
| order_id | 12345工单编号 | 12345工单编号 | 工单编号 | 去前缀 |
| accept_time | 12345受理时间 | 12345受理时间 | 受理时间 | 统一为datetime |
| source | 12345工单来源 | 12345工单来源 | 工单来源 | — |
| order_type | 12345工单类型 | 12345工单类型 | 工单类型 | — |
| content | 12345内容描述 | 12345内容描述 | 内容描述 | — |
| handler | 主办单位 | 主办单位 | 主办单位 | — |
| reply | 答复市民要点 | 答复市民要点 | 答复市民要点 | — |
| year | 年 | 年 | — | 2026.7文件补填2026 |
| month | 月份 | 月份 | 月份 | 统一为整数 |
| community_name | 小区名称 | 小区名称 | 小区名称 | — |
| community_id | 小区编号 | 小区编号 | — | 2026.7无此字段，置空 |
| community_addr | 小区地址 | 小区地址 | 小区地址 | — |
| property_company | 物业公司 | 物业公司 | 物业公司 | — |
| street | 街道 | 街道 | 街道 | 去掉"街道"后缀统一 |
| category_14 | 十四类 | 十四类 | 十四类 | 见3.2.3 |

#### 3.2.2 日期格式统一

| 文件 | 原始格式 | 示例 | 转换方式 |
|------|---------|------|---------|
| 2024 | datetime字符串 | 2024-01-31 00:00:00 | pd.to_datetime() |
| 2025-2026 | Excel序列号 | 45681 | pd.to_datetime(unit='D', origin='1899-12-30') |
| 2026.7 | datetime字符串 | 2026-07-07 20:07:25 | pd.to_datetime() |

#### 3.2.3 十四类分类名称统一

2024年文件有21个分类值（含"剔除"类），需清洗为14个标准分类：

| 统一名称 | 2024原始名称 | 处理 |
|----------|-------------|------|
| 停车管理 | 停车管理 | — |
| 房屋维修 | 房屋维修 | — |
| 邻里纠纷 | 邻里纠纷 | — |
| 房屋违规使用 | 房屋违规使用 | — |
| 业主大会/业委会 | 业委会 | 重命名 |
| 消防管理 | 消防管理 | — |
| 群租管理 | 群租问题 | 重命名 |
| 物业安保 | 物业安保 | — |
| 旧住房改造 | 旧住房改造 | — |
| 清洁卫生 | 清洁卫生 | — |
| 物业收费 | 物业收费 | — |
| 物业服务态度 | 物业服务态度/服务态度 | 统一名称 |
| 房屋交易纠纷 | 房屋交易纠纷 | — |
| 其他 | 其他 | — |
| （删除） | 剔除三大类、剔除-商办楼宇、剔除-非物业管理区域、剔除-无效工单、无 | 过滤掉 |

#### 3.2.4 其他清洗规则
- 去掉"剔除"类记录
- 工单类型过滤：只保留"投诉举报类"和"求助类"（2024年还有咨询类/意见建议类/其他类，但2025年后已不含）
- 街道名称去掉"街道"后缀（"漕河泾街道"→"漕河泾"），统一"无"值的处理
- 物业公司名称去空格、统一简称

### 3.3 数据库表结构

#### 3.3.1 主表：work_orders

```sql
CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE,           -- 工单编号
    accept_time DATETIME,           -- 受理时间
    source TEXT,                    -- 工单来源
    district TEXT,                  -- 行政区（固定"徐汇区"）
    address TEXT,                   -- 诉求地址
    order_type TEXT,                -- 工单类型
    content TEXT,                   -- 内容描述
    handler TEXT,                   -- 主办单位
    reply TEXT,                     -- 答复市民要点
    year INTEGER,                   -- 年
    month INTEGER,                  -- 月（1-12）
    community_id TEXT,              -- 小区编号
    community_name TEXT,            -- 小区名称
    community_addr TEXT,            -- 小区地址
    property_company TEXT,          -- 物业公司
    street TEXT,                    -- 街道
    category_14 TEXT,               -- 十四类分类
    -- 五级业务分类（仅2024有完整数据）
    level1 TEXT,                    -- 一级业务分类
    level2 TEXT,                    -- 二级业务分类
    level3 TEXT,                    -- 三级业务分类
    level4 TEXT,                    -- 四级业务分类
    level5 TEXT                     -- 五级业务分类
);

-- 索引
CREATE INDEX idx_year_month ON work_orders(year, month);
CREATE INDEX idx_street ON work_orders(street);
CREATE INDEX idx_category ON work_orders(category_14);
CREATE INDEX idx_company ON work_orders(property_company);
CREATE INDEX idx_community ON work_orders(community_name);
```

#### 3.3.2 预计算聚合表

```sql
-- 月度总量统计
CREATE TABLE monthly_stats (
    year INTEGER,
    month INTEGER,
    total_count INTEGER,           -- 当月工单总数
    complaint_count INTEGER,       -- 投诉举报类数量
    help_count INTEGER,            -- 求助类数量
    yoy_count INTEGER,             -- 去年同期数量（用于计算同比）
    mom_count INTEGER,             -- 上月数量（用于计算环比）
    PRIMARY KEY (year, month)
);

-- 类别×月度统计
CREATE TABLE category_monthly_stats (
    year INTEGER,
    month INTEGER,
    category TEXT,                 -- 十四类
    count INTEGER,
    yoy_count INTEGER,
    PRIMARY KEY (year, month, category)
);

-- 街道×月度统计
CREATE TABLE street_monthly_stats (
    year INTEGER,
    month INTEGER,
    street TEXT,
    count INTEGER,
    yoy_count INTEGER,
    PRIMARY KEY (year, month, street)
);

-- 物业企业统计
CREATE TABLE enterprise_stats (
    year INTEGER,
    property_company TEXT,
    total_count INTEGER,
    yoy_count INTEGER,
    community_count INTEGER,       -- 管辖小区数
    avg_per_community REAL,         -- 户均/小区均
    PRIMARY KEY (year, property_company)
);

-- 小区统计
CREATE TABLE community_stats (
    year INTEGER,
    community_name TEXT,
    street TEXT,
    property_company TEXT,
    total_count INTEGER,
    yoy_count INTEGER,
    PRIMARY KEY (year, community_name)
);
```

### 3.4 数据字典

编写一份JSON格式的数据字典，供LLM理解表结构：

```json
{
  "tables": {
    "work_orders": {
      "description": "12345热线物业投诉工单明细表",
      "row_count": 70000,
      "columns": {
        "year": {"type": "int", "values": "2024, 2025, 2026"},
        "month": {"type": "int", "values": "1-12"},
        "street": {"type": "text", "values": "漕河泾, 长桥, 徐家汇, 田林, 枫林路, 斜土路, 龙华, 康健新村, 天平路, 湖南路, 虹梅路, 凌云路, 华泾镇"},
        "category_14": {"type": "text", "values": "停车管理, 房屋维修, 邻里纠纷, 房屋违规使用, 业主大会/业委会, 消防管理, 群租管理, 物业安保, 旧住房改造, 清洁卫生, 物业收费, 物业服务态度, 房屋交易纠纷, 其他"},
        "property_company": {"type": "text", "values": "200+家物业企业"},
        "community_name": {"type": "text", "values": "800+个小区"},
        "order_type": {"type": "text", "values": "投诉举报类, 求助类"}
      }
    }
  }
}
```

---

## 4. AI引擎需求

### 4.1 处理流程

```
用户输入（自然语言）
    │
    ▼
┌─────────────────────────────────┐
│ 第1步：意图分类                  │
│                                 │
│ 方式1（优先）：关键词规则匹配     │
│   匹配到预设意图 → 走预设模板     │
│                                 │
│ 方式2（兜底）：LLM Function Call  │
│   规则未匹配 → 调用LLM判断意图    │
│   LLM返回函数名+参数             │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│ 第2步：执行查询                   │
│                                 │
│ 调用对应查询函数 → 执行SQL → 获取  │
│ 结构化结果（列表/字典）           │
│                                 │
│ 数据全程在本地，不外传           │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│ 第3步：结果生成                   │
│                                 │
│ 将结构化结果 + 用户原始问题       │
│ 传给LLM，生成自然语言总结         │
│                                 │
│ 只传统计结果，不传原始明细        │
└────────────────┬────────────────┘
                 │
                 ▼
            返回用户
         （表格 + 文字总结）
```

### 4.2 意图分类规则

用关键词匹配实现快速意图分类：

| 意图ID | 关键词规则 | 对应函数 |
|--------|-----------|---------|
| trend | 趋势/走势/变化/降了没有/比去年/同比/环比 | get_trend |
| ranking | 排名/排行/top/最多/最少/最高/最低 | get_ranking |
| category | XX类/XX投诉/停车/群租/维修/纠纷 | get_category_detail |
| comparison | 对比/比较/VS/和...比 | get_comparison |
| hotspot | 哪些小区/增长最快/异常/高发 | get_hotspot |
| repeat | 重复/反复/多次/催办 | get_repeat |
| property | 物业公司/哪个物业/企业 | get_property |
| summary | 整体/概况/怎么样/情况 | get_summary |

匹配逻辑：按优先级从上到下匹配，命中即返回。未命中走LLM。

### 4.3 预设查询函数详细规格

#### 4.3.1 get_summary — 综合概览

```
功能：返回指定时间段的投诉整体概况
参数：
  - year: int（必填，如2026）
  - month: int（可选，不填则返回全年累计）
返回：
{
  "period": "2026年7月",
  "total": 2097,
  "yoy_change": "-0.2%",        // 同比
  "mom_change": "+13.0%",       // 环比
  "top3_categories": [
    {"name": "房屋维修", "count": 414, "yoy": "+3.5%"},
    {"name": "邻里纠纷", "count": 333, "yoy": "+55.6%"},
    {"name": "停车管理", "count": 263, "yoy": "-24.2%"}
  ],
  "top3_streets": [
    {"name": "漕河泾", "count": 226},
    {"name": "长桥", "count": 198},
    {"name": "徐家汇", "count": 175}
  ]
}
LLM总结模板：
"20XX年X月，徐汇区共受理12345物业类投诉{total}件，同比{yoy_change}，环比{mom_change}。
 投诉量前三类别是：{top1}（{count}件）、{top2}（{count}件）、{top3}（{count}件）。
 投诉量最高的街道是{street1}（{count}件）。"
```

#### 4.3.2 get_trend — 趋势查询

```
功能：返回月度趋势数据，支持同比/环比对比
参数：
  - year: int（必填）
  - dimension: str（可选，"total"/"category"/"street"，默认"total"）
  - dimension_value: str（dimension非total时必填，如"停车管理"/"漕河泾"）
  - compare_year: int（可选，默认去年）
返回：
{
  "period": "2026年1-7月",
  "current_data": [{"month": 1, "count": 1200}, ...],
  "compare_data": [{"month": 1, "count": 1500}, ...],
  "total_current": 7083,
  "total_compare": 9441,
  "yoy_change": "-24.97%"
}
```

#### 4.3.3 get_ranking — 排行查询

```
功能：返回指定维度的排行
参数：
  - year: int（必填）
  - month: int（可选，不填返回全年累计）
  - dimension: str（"street"/"category"/"community"/"enterprise"）
  - top_n: int（可选，默认10）
  - order: str（"desc"/"asc"，默认"desc"）
返回：
{
  "period": "2026年7月",
  "dimension": "街道",
  "ranking": [
    {"rank": 1, "name": "漕河泾", "count": 226, "yoy": "+5.2%"},
    {"rank": 2, "name": "长桥", "count": 198, "yoy": "-12.3%"},
    ...
  ]
}
```

#### 4.3.4 get_category_detail — 类别分析

```
功能：返回某类投诉的详细分布
参数：
  - category: str（必填，如"停车管理"）
  - year: int（必填）
  - month: int（可选）
  - group_by: str（可选，"community"/"street"/"enterprise"，默认"community"）
  - top_n: int（可选，默认10）
返回：
{
  "period": "2026年7月",
  "category": "停车管理",
  "total": 263,
  "community_count": 85,
  "top_communities": [
    {"name": "XX小区", "count": 12, "street": "漕河泾", "company": "XX物业"},
    ...
  ],
  "sub_issues": [
    {"issue": "车位不足", "count": 96},
    {"issue": "费用争议", "count": 54},
    {"issue": "车位被占", "count": 62}
  ]
}
```

#### 4.3.5 get_comparison — 对比查询

```
功能：对比两个实体（物业企业或街道）
参数：
  - entity_type: str（"enterprise"/"street"）
  - entity_names: list[str]（如["高建物业", "衡复物业"]）
  - year: int
  - month: int（可选）
返回：
{
  "period": "2026年7月",
  "entities": [
    {"name": "高建物业", "count": 65, "yoy": "-4.4%", "communities": 80, "avg": 0.81},
    {"name": "衡复物业", "count": 48, "yoy": "-26.2%", "communities": 103, "avg": 0.47}
  ]
}
```

#### 4.3.6 get_hotspot — 热点查询

```
功能：识别投诉异常增长/高发的小区
参数：
  - year: int
  - metric: str（"growth"/"density"/"volume"，默认"growth"）
  - top_n: int（默认20）
返回：
{
  "year": 2026,
  "metric": "同比增长",
  "hotspots": [
    {"community": "绿邑翠苑", "street": "漕河泾", "current": 106, "last_year": 48, "growth": "+120.8%", "company": "XX物业"},
    {"community": "金牛苑", "street": "...", "current": 63, "last_year": 33, "growth": "+90.9%", "company": "XX物业"},
    ...
  ]
}
```

#### 4.3.7 get_repeat — 重复投诉

```
功能：返回重复投诉统计数据
参数：
  - year: int
  - half: int（1=上半年, 2=下半年）
返回：
{
  "period": "2026年1-6月",
  "total_orders": 9239,
  "repeat_orders": 3746,
  "repeat_rate": "40.5%",
  "top_communities": [
    {"name": "新家园一期", "count": 56, "street": "...", "main_issue": "停车管理"},
    ...
  ],
  "top_categories": [
    {"category": "停车管理", "count": 466, "share": "15.3%"},
    {"category": "邻里纠纷", "count": 442, "share": "14.5%"},
    ...
  ]
}
```

#### 4.3.8 get_property — 物业企业分析

```
功能：返回物业企业投诉排行
参数：
  - year: int
  - month: int（可选）
  - enterprise: str（可选，指定企业名则返回该企业详情）
  - top_n: int（默认10）
返回：
{
  "period": "2026年7月",
  "ranking": [
    {"name": "高建物业", "count": 65, "yoy": "-4.4%", "communities": 80, "avg_per_community": 0.81},
    ...
  ]
}
```

### 4.4 LLM调用规范

#### 4.4.1 意图理解调用（兜底）

```
调用：通义千问 Qwen-Turbo API
System Prompt:
  "你是一个意图分类器。根据用户问题，从以下函数中选择一个并提取参数：
   - get_summary(year, month?): 综合概况
   - get_trend(year, dimension?, dimension_value?): 趋势查询
   - get_ranking(year, dimension, month?, top_n?): 排行查询
   - get_category_detail(category, year, month?, group_by?): 类别分析
   - get_comparison(entity_type, entity_names, year, month?): 对比查询
   - get_hotspot(year, metric?, top_n?): 热点查询
   - get_repeat(year, half): 重复投诉
   - get_property(year, month?, enterprise?, top_n?): 物业企业

   返回JSON格式：{"function": "函数名", "params": {...}}
   如果无法匹配，返回：{"function": "unknown", "reply": "建议问法"}"

输入：只传用户的问题文本，不传任何数据
```

#### 4.4.2 结果总结调用

```
调用：通义千问 Qwen-Turbo API
System Prompt:
  "你是徐汇区物业投诉数据分析助手。根据查询结果，用简洁专业的语言生成分析总结。
   要求：
   1. 先给出核心数字（总量、变化率）
   2. 再列出重点发现（Top3、异常项）
   3. 最后给一句简短建议（可选）
   4. 语言简洁，不超过150字
   5. 不要编造数据，只使用提供的结果"

输入：用户原始问题 + 查询返回的结构化结果（统计值，不含明细）
```

### 4.5 会话上下文

支持追问场景。维护最近3轮对话上下文：

```
用户："本月哪个街道投诉最多？"
  → 意图: get_ranking(year=2026, month=7, dimension="street")
  → 返回: 漕河泾226件...

用户："那停车类呢？"
  → 上下文推断: year=2026, month=7不变，dimension="category", category="停车管理"
  → 意图: get_category_detail(category="停车管理", year=2026, month=7)
  → 返回: 停车管理263件...
```

上下文继承规则：
- 时间参数（year, month）默认沿用上一轮
- 维度参数（dimension）根据新问题关键词判断
- 如果新问题包含新时间，则覆盖

---

## 5. 后端API需求

### 5.1 接口定义

#### POST /api/chat — 主对话接口

```
请求体：
{
  "message": "本月哪个街道投诉最多？",   // 用户输入
  "session_id": "xxx"                   // 会话ID（用于上下文）
}

响应体：
{
  "session_id": "xxx",
  "reply": "2026年7月投诉量最高的街道是漕河泾（226件），其次是长桥（198件）、徐家汇（175件）。",
  "table": {                           // 可选，有表格数据时返回
    "headers": ["排名", "街道", "投诉量", "同比"],
    "rows": [
      [1, "漕河泾", 226, "+5.2%"],
      [2, "长桥", 198, "-12.3%"],
      ...
    ]
  },
  "chart": null,                        // 预留，暂不实现
  "raw_intent": "ranking",              // 识别到的意图（调试用）
  "query_time_ms": 120                 // 查询耗时（调试用）
}
```

#### GET /api/health — 健康检查

```
响应体：
{
  "status": "ok",
  "db_connected": true,
  "llm_connected": true,
  "data_range": "2024.01 - 2026.07",
  "total_records": 70748
}
```

### 5.2 错误处理

| 场景 | HTTP状态码 | 响应 |
|------|-----------|------|
| 意图无法识别 | 200 | "您的问题我暂时无法理解，可以试试问：本月投诉概况、停车类投诉排行、哪个街道投诉最多" |
| 查询参数缺失 | 200 | "请问您想查询哪个月份的数据？" |
| 数据库错误 | 500 | "系统暂时无法查询，请稍后重试" |
| LLM API超时 | 200 | 走预设模板兜底，不返回错误 |

### 5.3 性能要求

| 指标 | 要求 |
|------|------|
| 查询响应时间 | ≤3秒（从收到请求到返回结果） |
| 数据库查询 | ≤500ms（走预计算聚合表） |
| LLM API调用 | ≤2秒（超时则走兜底） |
| 并发 | 支持5个并发会话（演示场景足够） |

---

## 6. 前端需求

### 6.1 方案选择

| 方案 | 开发量 | 演示效果 | 推荐场景 |
|------|--------|---------|---------|
| A: H5聊天页面 | 2天 | 好，界面可控 | 团队有前端能力 |
| B: 企业微信自建应用 | 1天 | 好，最接近微信场景 | 有企业微信管理员权限 |
| C: 命令行/Postman | 0天 | 差 | 最后兜底 |

推荐方案A（H5聊天页面），原因：
- 界面可控，可定制"徐汇区物业投诉分析智能助手"标题和图标
- 在微信中打开链接即可使用，不需要企业微信配置
- 演示效果最好

### 6.2 H5页面设计

```
┌─────────────────────────────────────┐
│  [图标] 徐汇区物业投诉分析智能助手      │  ← 顶部标题栏，深蓝色背景
├─────────────────────────────────────┤
│                                     │
│  [助手] 您好！我是徐汇区物业投诉数据    │
│         分析助手，可以问我任何关于      │
│         12345投诉数据的问题。          │
│                                     │
│  [用户] 本月哪个街道投诉最多？         │
│                                     │
│  [助手] 2026年7月投诉量最高的街道      │
│         是漕河泾（226件）...          │
│        ┌──────────────────┐         │
│        │ 排名 街道  投诉量  │         │
│        │ 1   漕河泾  226   │         │
│        │ 2   长桥    198   │         │
│        │ 3   徐家汇  175   │         │
│        └──────────────────┘         │
│                                     │
│  [快捷问题按钮]                       │
│  [本月概况] [投诉趋势] [街道排行]      │
│  [停车分析] [重复投诉]                │
│                                     │
├─────────────────────────────────────┤
│  [输入框]                    [发送]   │  ← 底部输入栏
└─────────────────────────────────────┘
```

设计要求：
- 聊天气泡风格，助手消息左对齐，用户消息右对齐
- 表格用HTML table渲染，带边框和斑马纹
- 快捷问题按钮在底部，点击直接发送预设问题
- 输入框支持回车发送
- 页面适配手机屏幕（viewport meta tag）
- 配色：深蓝(#1a3a5f) + 白色为主，数据用橙色高亮

### 6.3 快捷问题按钮

预设5个快捷按钮，点击即发送：

| 按钮 | 发送内容 |
|------|---------|
| 本月概况 | "这个月全区投诉情况怎么样？" |
| 投诉趋势 | "今年的投诉量和去年比降了没有？" |
| 街道排行 | "本月投诉量最多的5个街道是哪些？" |
| 停车分析 | "停车类投诉主要集中在哪些小区？" |
| 重复投诉 | "重复投诉率是多少？哪些小区最严重？" |

---

## 7. 演示场景设计

### 7.1 预设演示问题（8个，按由浅入深排序）

| 序号 | 演示问题 | 展示能力 | 预期输出要点 |
|------|---------|---------|-------------|
| 1 | 这个月全区投诉情况怎么样？ | 综合概览 | 总量2097件，同比-0.2%，环比+13.0%，Top3类别 |
| 2 | 今年的投诉量和去年比，降了没有？ | 趋势对比 | 1-5月同比-24.97%，月度趋势下降，重点类别降幅 |
| 3 | 本月投诉量最多的5个街道是哪些？ | 排行查询 | Top5街道表格，漕河泾226件居首 |
| 4 | 停车类投诉主要集中在哪些小区？ | 类别深挖 | 停车263件，Top5小区，子问题分布（车位不足96件等） |
| 5 | 徐房集团和城投集团今年表现怎么样？ | 企业对比 | 两集团投诉量、同比、下属企业排行 |
| 6 | 重复投诉率是多少？哪些小区最严重？ | 技术含量 | 40.5%重复率，Top5热点小区，类别分布 |
| 7 | 哪些小区今年投诉增长最快？ | 异常发现 | 绿邑翠苑+120.8%、金牛苑+90.9%等，关联物业企业 |
| 8 | （领导自由提问） | 灵活性 | Function Calling兜底或引导话术 |

### 7.2 演示兜底方案

| 风险场景 | 兜底措施 |
|---------|---------|
| 现场网络不稳定 | 预缓存问题1-7的结果截图，网络断了切到截图展示 |
| LLM API超时 | 查询结果仍可返回（表格数据），文字总结用模板生成 |
| 领导问预设外问题 | Function Calling兜底；无法回答时"这个问题我记录下来后续分析" |
| 数据库查询异常 | 返回最近一次成功查询的缓存结果 |

### 7.3 预缓存实现

为问题1-7预先生成结果，存储为JSON文件：

```
/demo_cache/
  ├── q1_summary.json       # 预计算结果
  ├── q1_summary_reply.txt  # 预生成文字总结
  ├── q2_trend.json
  ├── q2_trend_reply.txt
  ...
```

演示时优先尝试实时查询，超时3秒则返回缓存结果。

---

## 8. 数据安全要求

### 8.1 三层隔离

| 层级 | 要求 | 实现方式 |
|------|------|---------|
| 数据存储 | 热线数据存储在区级服务器 | SQLite文件放在服务器本地，不上传云端 |
| 查询执行 | SQL查询在后端本地执行 | 后端直接读取本地SQLite，不经过网络 |
| LLM调用 | LLM不接触原始数据 | 只传意图文本(几十字)和统计结果(几十个数字)，不传投诉明细 |

### 8.2 LLM数据传输边界

```
可以传给LLM的内容：
  ✓ 用户问题文本（如"本月哪个街道投诉最多"）
  ✓ 查询结果统计值（如"漕河泾226件, 长桥198件"）
  ✓ 数据字典（表名、字段名、分类列表）

不能传给LLM的内容：
  ✗ 投诉内容描述（12345内容描述字段）
  ✗ 市民个人信息（地址、姓名等）
  ✗ 工单明细记录
  ✗ 完整数据库内容
```

### 8.3 部署安全

- 服务器只开放必要端口（API服务的端口）
- API接口加简单鉴权（Bearer Token）
- 不暴露数据库文件路径
- 访问日志记录所有查询（审计用）

---

## 9. 非功能性需求

| 指标 | 要求 |
|------|------|
| 响应时间 | 单次查询≤3秒 |
| 并发 | 支持5个并发会话 |
| 可用性 | 演示期间99%可用（有缓存兜底） |
| 数据时效 | 数据更新到2026年7月 |
| 浏览器兼容 | 微信内置浏览器、Safari、Chrome |
| 屏幕适配 | 手机屏幕（375px-414px宽度） |

---

## 10. 验收标准

### 10.1 功能验收

- [ ] 8个预设问题全部能正确返回结果
- [ ] 表格数据正确（与Excel原始数据一致）
- [ ] 文字总结准确（不编造数据）
- [ ] 追问场景能正确继承上下文
- [ ] 异常输入有友好兜底

### 10.2 性能验收

- [ ] 单次查询响应≤3秒
- [ ] 预计算聚合表查询≤500ms
- [ ] LLM超时后有兜底，不报错

### 10.3 安全验收

- [ ] LLM API调用不包含原始投诉文本
- [ ] 数据库文件不在公网可访问路径
- [ ] API有鉴权
- [ ] 有访问日志

### 10.4 演示验收

- [ ] 手机微信打开H5页面正常显示
- [ ] 预设8个问题现场演示通过
- [ ] 断网情况下缓存兜底可用
- [ ] 快捷按钮点击正常

---

## 11. 开发排期

| 阶段 | 任务 | 工时 | 依赖 |
|------|------|------|------|
| 1 | 数据清洗合并（3.2节） | 1天 | 无 |
| 2 | 数据库建表+导入+预计算（3.3节） | 0.5天 | 阶段1 |
| 3 | 查询函数开发（4.3节，8个函数） | 2天 | 阶段2 |
| 4 | 意图分类+LLM调用（4.2-4.4节） | 1天 | 阶段3 |
| 5 | 后端API（5.1节） | 1天 | 阶段4 |
| 6 | 前端H5页面（6.2节） | 1.5天 | 阶段5 |
| 7 | 会话上下文+追问（4.5节） | 0.5天 | 阶段5 |
| 8 | 预缓存+兜底（7.3节） | 0.5天 | 阶段5 |
| 9 | 联调测试 | 1天 | 阶段6-8 |
| 10 | 演示演练 | 0.5天 | 阶段9 |
| **合计** | | **约9天** | |

---

## 12. 目录结构建议

```
xuhui-ai-agent/
├── data/                         # 数据文件
│   ├── raw/                      # 原始Excel
│   │   ├── 2024年市局14类.xlsx
│   │   ├── 2025年全年、2026年1-6月市局14类.xlsx
│   │   └── 2026年7月市局14类.xlsx
│   ├── xuhui_complaints.db       # SQLite数据库
│   └── data_dictionary.json      # 数据字典
├── scripts/                      # 数据处理脚本
│   ├── clean_data.py             # 数据清洗合并
│   ├── build_database.py         # 建库+导入
│   └── precompute.py             # 预计算聚合表
├── src/                          # 后端源码
│   ├── main.py                   # FastAPI入口
│   ├── query_functions.py        # 8个查询函数
│   ├── intent_classifier.py      # 意图分类
│   ├── llm_client.py             # LLM API调用
│   ├── session_manager.py        # 会话上下文管理
│   └── config.py                 # 配置（API Key等）
├── frontend/                     # 前端H5
│   ├── index.html
│   ├── style.css
│   └── app.js
├── demo_cache/                   # 预缓存结果
│   ├── q1_summary.json
│   └── ...
├── tests/                        # 测试
│   ├── test_query_functions.py
│   └── test_intent.py
├── requirements.txt              # Python依赖
├── .env                          # 环境变量（API Key等）
└── README.md                     # 部署说明
```

---

## 附录：通义千问API调用示例

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 意图理解
response = client.chat.completions.create(
    model="qwen-turbo",
    messages=[
        {"role": "system", "content": "你是一个意图分类器...（见4.4.1）"},
        {"role": "user", "content": "本月哪个街道投诉最多？"}
    ],
    response_format={"type": "json_object"},  # 强制返回JSON
    temperature=0.1  # 低温度确保稳定
)

# 结果总结
response = client.chat.completions.create(
    model="qwen-turbo",
    messages=[
        {"role": "system", "content": "你是徐汇区物业投诉数据分析助手...（见4.4.2）"},
        {"role": "user", "content": f"用户问题：{question}\n查询结果：{json.dumps(query_result)}"}
    ],
    temperature=0.3
)
```

API Key获取：阿里云百炼平台 https://bailian.console.aliyun.com/ → 开通模型服务 → 获取API Key
