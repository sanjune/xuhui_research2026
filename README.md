# 徐汇物业课题一期

徐汇区物业投诉治理数字化课题一期项目成果仓库。

## 🚀 在线访问

👉 **[课题成果总览页面](https://sanjune.github.io/xuhui_research2026/)**

直接访问：`https://sanjune.github.io/xuhui_research2026/`

## 📊 成果清单（12项已完成 · 进度80%）

### 核心成果
1. ✅ 12345投诉量下降数据报告
2. ✅ 投诉去重识别方法论说明
3. ✅ 数据质量优化专项报告
4. ✅ 重点问题专题分析报告（5份）
5. ✅ 高风险小区预警清单
6. ✅ 治理效果追踪分析报告
7. ✅ 物业投诉根因分析报告
8. ✅ 数据分析月报合集

### 深度分析
9. ✅ 底部抬升小区热线数据分析报告
10. ✅ 多源数据清洗与关联分析报告

### 工具成果
11. ✅ 徐汇AI智能体
12. ✅ 2026年6月投诉去重建议清单

## 📁 项目结构

```
├── 课题成果总览.html          # 总目录入口
├── index.html                 # GitHub Pages 首页
├── *.html                     # 各成果报告HTML
├── daily/                     # 12345物业工单日报（日历索引+各日详情）
├── scripts/                   # 数据分析脚本（含日报生成 gen_daily_report）
├── src/                       # AI智能体后端代码
├── frontend/                  # 前端demo
├── tests/                     # 测试用例
├── data/                      # 数据字典、质量报告
├── 月度分析报告/              # Word格式月度报告
└── 年度分析报告/              # 街道/集团年度分析报告
```

## 📅 12345物业工单日报

按日历查阅每日 12345 热线物业工单日报，支持月历/列表双视图切换、月份翻页、点击日期查看当日详情。

- 生成脚本：`scripts/gen_daily_report_1009.py`（按街镇分类，市局12345原生四级口径）
- 日历索引：`daily/index.html`（月历视图 + 列表视图）
- 日报详情：`daily/YYYY-MM-DD.html`

本地预览：`python3 -m http.server 8765 --directory _publish`，访问 http://localhost:8765/

## 🔧 技术栈

- 数据分析：Python + Pandas + DuckDB
- 可视化：原生 SVG / HTML / CSS
- AI智能体：Python + LLM API
- 部署：GitHub Pages
