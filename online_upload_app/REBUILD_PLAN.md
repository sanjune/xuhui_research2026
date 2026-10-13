# Excel 上传功能重构开发计划（基于 cloud-service / Supabase 架构）

> 编制日期：2026-10-12 ｜ 目标：彻底解决沙箱重部署丢失数据问题，实现 Excel 上传 → JSON 持久化 → 日报展示的闭环

## 一、背景与问题

### 现状
- `online_upload_app/app.py` 是 Python HTTP 服务，数据存本地 `data/reports.json` + `data/*.html`
- 每次重新部署 WorkBuddy sites 会用本地 `data/` 覆盖沙箱 → 线上新上传数据丢失（已发生：10-11 日报被覆盖）
- GitHub Pages 是静态站，无法直接调用 cloud-service SDK（Origin 不匹配）

### 目标（用户需求）
1. Excel 上传入口
2. Excel 解析为 JSON
3. JSON 能被 `daily/index.html`（本地或线上）读取展示
4. 生成 JSON 后自动删除 Excel
5. 基于 Supabase（cloud-service）实现

## 二、推荐架构：客户端解析 + 云数据库持久化

### 核心决策
- **Excel 不上传服务器**，由浏览器内 SheetJS 解析 → 天然满足"自动删除"（仅内存，页面关闭即释放）
- **JSON 存入 cloud-service Database** → 独立于沙箱生命周期，重部署不丢失
- **三个静态页面**托管于 WorkBuddy Sites（Origin 匹配 cloud-service SDK 可正常读写）
- **GitHub Pages 仅做重定向**（已有跳转页）

### 数据流
```
用户选择 xlsx
   ↓
upload.html（SheetJS 浏览器内解析 → 结构化 JSON）
   ↓ cloud SDK 写入
cloud-service Database · daily_reports 表（JSONB）
   ↓ cloud SDK 读取
index.html（日历索引） / report.html（日报详情）
```

### 关键约束
- cloud-service SDK 的 `publishableKey` 受 Origin 严格匹配 → 所有 SDK 调用必须在 WorkBuddy 部署域名发起
- GitHub Pages 无法直接读 DB → 故三个页面统一托管于 WorkBuddy Sites
- 使用 CDN 形式加载 SDK（`<script>` 全局 `WorkBuddyCloud`），无需 npm/构建步骤

## 三、数据模型

### 表 `daily_reports`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | bigint（自增主键） | |
| `report_date` | date（唯一索引） | 报告日期，如 `2026-10-09` |
| `weekday` | text | 星期，如 `星期五` |
| `total` | int | 当日工单总量 |
| `matched` | int | 已关联街镇工单数 |
| `unmatched` | int | 待关联街道工单数 |
| `rep` | int | 重复案件数 |
| `rep_rate` | numeric | 重复率（百分比数值，如 30.8） |
| `streets` | int | 涉及街镇数 |
| `main_cat` | jsonb | 主要类别数组，如 `["物业安保 28","物业维修添置 16"]` |
| `report_data` | jsonb | 日报完整结构化数据（见下） |
| `created_at` | timestamptz | 创建时间，默认 now() |

### `report_data` JSONB 结构

```json
{
  "streetRows": [
    {"street":"枫林路街道","n":28,"mainCat":"物业安保 8、纠纷协调 5","rep":12,"repRate":42.8,"flag":"danger"}
  ],
  "categoryStats": {
    "typed":   [{"name":"物业安保","count":28,"pct":26.9,"streets":10}],
    "source":  [{"name":"12345热线","count":80}],
    "type":    [{"name":"投诉","count":70}],
    "problemTypeB": [{"name":"物业管理","count":45}]
  },
  "focusStreets": [
    {
      "street":"枫林路街道","n":28,"mainCat":"...","rep":12,"repRate":42.8,
      "repeatCases":[
        {"addr":"XX路XX号","typed":"物业安保","prob":"门岗无人值守…"}
      ]
    }
  ]
}
```

### 权限（RLS）
- **读**：公开（anon 可查全部记录）→ 日历索引与日报详情均无需登录
- **写**：由 publishableKey + Origin 匹配控制（仅部署域名可写，无需用户登录）

## 四、文件结构

```
online_upload_app/
├── index.html          # 日历索引（读取 DB，渲染日历 + 列表）
├── upload.html         # 上传页（SheetJS 解析 + 写入 DB）
├── report.html         # 日报详情（读取 DB 单条，渲染四节）
├── app.js               # 共享：SDK 初始化 + 解析逻辑 + 渲染模板
├── style.css           # 共享样式（移植自现有日报 CSS）
├── .genie               # 应用标记（部署用）
└── requirements.txt     # 无 Python 依赖（纯静态），可删除
```

> 原 `app.py`、`index_template.html`、`data/` 目录将废弃——数据全部进 DB，不再需要本地文件。

## 五、开发阶段

### 阶段 0：前置准备
- [ ] 调用 `workbuddy_cloud_service` inspect 查看当前会话应用
- [ ] 复用已有应用（`12345日报上传服务`）或新建 → activate → 获取 `publicConfig`（endpoint / publishableKey / oauthRelayBaseUrl）
- [ ] 读取 `references/database/code-generation.md` 确认建表与读写 API

### 阶段 1：数据层
- [ ] 创建 `daily_reports` 表（按第三节 schema）
- [ ] 设置 RLS：`SELECT` 对 anon 公开；`INSERT/UPDATE` 限 publishableKey Origin
- [ ] 写迁移脚本：把现有 3 份日报（10-09/10-10/10-11）的 summary + 结构化数据导入表
  - 结构化数据从已生成的 `daily/*.html` 反向解析，或从 `热线日报数据/*.xlsx` 用 Python 重跑一次提取

### 阶段 2：共享模块 `app.js`
- [ ] cloud SDK 初始化（CDN 形式，传入 publicConfig 三字段）
- [ ] **解析核心** `parseExcel(file): Promise<ReportData>`：用 SheetJS 读取 xlsx → 移植 `app.py:generate_report()` 的全部统计逻辑到 JS
  - 输入列：`processtime, s30_str_name, problemtyped, is_repeat, appealaddr, problem, hotlinesource, hotlinetype, problemtypeb`
  - 输出：summary 字段 + report_data 结构化对象
  - PII 脱敏正则同步移植（手机号/身份证/邮箱）
  - 街镇排序、重点街镇判定（n≥6 或 repRate≥40）、重复案件明细抽取
- [ ] **渲染模板** `renderIndex(reports)` / `renderReport(report)`：移植现有 HTML 模板到 JS 字符串拼接
  - 含四节：总体情况卡片 / 街镇分类明细表 / 12345平台原生分类 / 重点街镇关注
  - CSS grid 3 列（地址110px/细类92px/摘要1fr）+ upload-zone display:block

### 阶段 3：上传页 `upload.html`
- [ ] 文件选择 + 拖拽上传区（display:block 修复版）
- [ ] 调用 `app.js.parseExcel()` 解析
- [ ] 解析结果校验：必填字段存在、PII 断言通过、日期合法
- [ ] 调用 SDK `database` 写入 `daily_reports`（upsert by report_date）
- [ ] 成功反馈 + 跳转日历索引；失败显示错误
- [ ] Excel 文件对象不持久化（仅 `File` 引用，函数结束即 GC）→ 满足自动删除

### 阶段 4：日历索引 `index.html`
- [ ] SDK 读取 `daily_reports` 全部记录（按 report_date 倒序）
- [ ] 渲染日历网格 + 列表视图（移植现有 `index_template.html` 逻辑）
- [ ] 点击日期 → 跳转 `report.html?date=YYYY-MM-DD`
- [ ] 顶部"上传数据"按钮 → `upload.html`
- [ ] 空状态：无数据时显示引导上传

### 阶段 5：日报详情 `report.html`
- [ ] 从 URL 参数取 `date`
- [ ] SDK 读取该日期单条记录
- [ ] 用 `app.js.renderReport()` 渲染完整日报（四节）
- [ ] 返回按钮 → `index.html`

### 阶段 6：部署与联调
- [ ] 用 `workbuddy_sites_deploy` 发布静态站（reuse 应用 ID，保留域名与 Origin）
- [ ] 端到端验证：上传 xlsx → DB 写入 → 日历显示 → 点击查看日报
- [ ] 验证重新部署后数据仍在（核心目标）
- [ ] GitHub Pages `daily/index.html` 重定向地址确认指向部署域名

### 阶段 7：清理
- [ ] 删除 `app.py`、`index_template.html`、`data/` 目录（数据已在 DB）
- [ ] 删除 `scripts/upload_server.py`（本地版同样被新架构取代）
- [ ] 更新 `.gitignore` 移除 `online_upload_app/data/` 条目
- [ ] `gen_daily_report_1009.py` 保留（本地离线生成仍可用，作为 DB 导入工具）

## 六、技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| Excel 解析 | SheetJS (xlsx) CDN | 浏览器原生，无需服务器 |
| 后端 | cloud-service Database | 对标 Supabase，Origin 匹配安全，数据持久 |
| SDK 加载 | CDN `<script>` 全局 | 纯静态站，无构建步骤 |
| 宿主 | WorkBuddy Sites 静态托管 | Origin 匹配 SDK，重新部署不丢数据 |
| 认证 | 无需（publishableKey + Origin） | 内部工具，公开读 + Origin 限写 |

## 七、风险与对策

| 风险 | 对策 |
|------|------|
| SheetJS 解析逻辑与 Python 版有差异 | 用现有 3 份数据做回归验证：解析结果与 reports.json 逐字段比对 |
| cloud-service 配额/计费 | inspect 时确认 billingStatus=normal；写入量极小（每日1条） |
| Origin 不匹配导致 SDK 失败 | 统一托管于 WorkBuddy Sites，不尝试从 GitHub Pages 调 SDK |
| PII 残留 | 解析后 JS 端做三重正则断言（与 Python 版一致） |
| 重复上传同日期 | upsert by report_date（唯一索引），覆盖旧记录 |

## 八、验证清单

- [ ] 上传 10-09 xlsx → DB 出现该日期记录 → 日历索引显示 → 点击进入日报四节完整
- [ ] 重新部署应用 → 数据仍在 → 日历索引仍显示全部记录
- [ ] 上传已有日期 → 覆盖更新而非新增重复
- [ ] 解析结果与旧 reports.json 逐字段一致（total/rep/mainCat/streets）
- [ ] 日报详情排版正确（grid 3 列、upload-zone display:block）
- [ ] Excel 文件未出现在服务器/存储（仅浏览器内存）

## 九、与现有架构的对比

| 维度 | 旧架构（Python app + 本地文件） | 新架构（静态 + 云 DB） |
|------|------|------|
| 数据存储 | 本地 reports.json + HTML 文件 | cloud-service Database JSONB |
| 重部署影响 | 数据被覆盖丢失 | 数据不丢（在 DB） |
| 服务器进程 | Python HTTP 服务（需运行） | 无（纯静态） |
| Excel 处理 | 服务端 pandas 解析 | 浏览器 SheetJS 解析 |
| Excel 持久化 | 曾存本地（需手动删） | 不持久化（仅内存，自动释放） |
| GitHub Pages | 重定向到部署站 | 重定向到部署站（不变） |
