#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建可对外发布的静态站点目录 _publish/（幂等）

为什么不能直接发布项目根目录：
  根目录含 data/*.pkl（66,812 条工单主数据）、热线数据/、徐汇各科室业务数据/ 等**敏感输入**，
  静态站点会把它们一并暴露为可下载文件。本脚本只复制「报告页 + 其真实依赖的本地资源」。

产出：
  _publish/index.html        门户首页（脚本生成，非手写）
  _publish/*.html            17 份报告页
  _publish/assets/           报告引用的本地 JS（echarts）
  _publish/词云图/           13 张街镇词云 PNG + 词云总览.html

用法：
  PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/build_publish_site.py [--check]

  --check  只校验不写盘（比对 _publish/ 与期望是否一致，用于幂等复验）
"""
import os, re, sys, shutil, hashlib, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_publish")

# ── 发布清单：(文件名, 分类, 标题, 一句话说明) ────────────────────────────────
PAGES = [
    # 核心成果
    ("课题成果总览.html", "核心成果", "课题成果总览",
     "全部交付物索引、核心数字与完成度一览"),
    ("徐汇区1-8月工单综合分析与目标测算.html", "核心成果", "1-8月综合分析与目标测算",
     "全区总量与同比、街镇/国资企业/月度拆解、目标测算与行动建议"),
    ("街镇专项分析报告.html", "核心成果", "街镇专项分析报告",
     "13 街镇密度（件/千户）、同比、占比与诉求主题词云"),

    # 专项分析
    ("高风险小区预警清单.html", "专项分析", "高风险小区预警清单",
     "纳统小区红/橙/黄/蓝/绿五级预警，可按等级下钻查看小区名单"),
    ("物业投诉根因分析报告.html", "专项分析", "物业投诉根因分析报告",
     "诉求根因分类、恶化与改善案例、根因 Top 榜"),
    ("治理效果追踪分析报告.html", "专项分析", "治理效果追踪分析报告",
     "十四类问题治理效果追踪 + 物业服务态度投诉专项排名（公司/小区双视图）"),
    ("底部抬升小区热线数据分析报告.html", "专项分析", "底部抬升小区热线数据分析报告",
     "重点小区热线量与同比，定位底部抬升街道与小区"),
    ("数据质量优化专项报告.html", "专项分析", "数据质量优化专项报告",
     "字段完整性、热线-纳统匹配率与口径问题清单"),
    ("12345投诉量下降数据报告.html", "专项分析", "12345 投诉量下降数据报告",
     "全区投诉量下降的构成拆解与来源归因"),
    ("重点问题专题分析报告（5份）.html", "专项分析", "重点问题专题分析报告（5 份）",
     "防汛防台、停车管理、垃圾清理等重点专题"),
    ("数据分析月报合集.html", "专项分析", "数据分析月报合集",
     "2026 年各月分析报告合集"),

    # 方法与流程
    ("投诉去重识别方法论说明.html", "方法与流程", "投诉去重识别方法论说明",
     "判定重复的规则、阈值与口径边界"),
    ("2026年1-8月投诉去重建议清单.html", "方法与流程", "1-8月投诉去重建议清单",
     "疑似重复工单明细与合并建议"),
    ("多源数据清洗与关联分析报告.html", "方法与流程", "多源数据清洗与关联分析报告",
     "多源数据清洗链路与纳统小区关联结果"),
    ("词云图/词云总览.html", "方法与流程", "13 街镇诉求主题词云",
     "各街镇高频诉求主题词云图（2026 年 1-8 月，案件级归并）"),

    # 项目管理
    ("网页版整改清单（技术方执行版）.html", "项目管理", "网页版整改清单（技术方执行版）",
     "13 项整改项的执行状态、口径决策与实测基准值"),
    ("版本更新记录.html", "项目管理", "版本更新记录",
     "版本迭代、修复项与回归验证记录"),
    ("词云词表审核清单.html", "项目管理", "词云词表审核清单",
     "停用词表与 Top60 候选池人工审核记录"),
]

# 报告引用的本地资源（目录级复制）
#   cloud/ —— 云服务接入资产（publicConfig + Auth/Database 客户端 + 样式），
#             由 gen_wordcloud_review.py 注入到审核页；属应用源码，必须随站点发布
ASSET_DIRS = ["assets", "词云图", "cloud"]
# 发布目录内**禁止**出现的东西（敏感输入兜底断言）
FORBIDDEN_EXT = {".pkl", ".db", ".xlsx", ".xls", ".csv", ".docx", ".doc", ".py", ".bak", ".off"}

CAT_ORDER = ["核心成果", "专项分析", "方法与流程", "项目管理"]
CAT_DESC = {
    "核心成果": "全区与街镇的主线结论、目标测算",
    "专项分析": "按专题深入：预警、根因、治理、底抬、质量、月度",
    "方法与流程": "口径说明、去重方法、数据清洗链路与词云",
    "项目管理": "整改清单、版本记录与审核留痕",
}


def build_index_html(meta):
    """生成门户首页。meta: {file: (cat, title, desc)}"""
    groups = {c: [] for c in CAT_ORDER}
    for f, (cat, title, desc) in meta.items():
        groups[cat].append((f, title, desc))

    cards = []
    for cat in CAT_ORDER:
        items = groups[cat]
        if not items:
            continue
        lis = "\n".join(
            f'      <a class="card" href="{f}">\n'
            f'        <div class="card-t">{title}</div>\n'
            f'        <div class="card-d">{desc}</div>\n'
            f'      </a>' for f, title, desc in items
        )
        cards.append(
            f'  <section class="group">\n'
            f'    <div class="g-head"><h2>{cat}</h2><span class="g-sub">{CAT_DESC[cat]}</span></div>\n'
            f'    <div class="grid">\n{lis}\n    </div>\n'
            f'  </section>'
        )
    body = "\n".join(cards)
    n = len(meta)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>徐汇区物业投诉数据分析 · 课题一期成果</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:"PingFang SC","Microsoft YaHei",-apple-system,sans-serif;
         background:#f4f6fa; color:#1f2937; line-height:1.6; }}
  header {{ background:linear-gradient(135deg,#0d47a1,#1976d2); color:#fff; padding:38px 24px 30px; }}
  .wrap {{ max-width:1180px; margin:0 auto; }}
  header h1 {{ margin:0 0 8px; font-size:26px; letter-spacing:.5px; }}
  header p {{ margin:0; opacity:.9; font-size:14px; }}
  .kpis {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:18px; }}
  .kpi {{ background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.28);
          border-radius:8px; padding:8px 14px; font-size:13px; }}
  .kpi b {{ font-size:17px; margin-right:4px; }}
  main {{ padding:28px 24px 60px; }}
  .group {{ margin-bottom:34px; }}
  .g-head {{ display:flex; align-items:baseline; gap:12px; margin-bottom:14px;
             border-left:4px solid #1976d2; padding-left:12px; }}
  .g-head h2 {{ margin:0; font-size:18px; }}
  .g-sub {{ font-size:13px; color:#6b7280; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; }}
  .card {{ display:block; background:#fff; border:1px solid #e3e8ef; border-radius:10px;
           padding:16px 18px; text-decoration:none; color:inherit;
           transition:box-shadow .18s, transform .18s, border-color .18s; }}
  .card:hover {{ box-shadow:0 6px 20px rgba(25,118,210,.14); transform:translateY(-2px);
                 border-color:#90caf9; }}
  .card-t {{ font-size:15px; font-weight:600; color:#0d47a1; margin-bottom:6px; }}
  .card-d {{ font-size:13px; color:#5b6572; }}
  footer {{ text-align:center; color:#8a94a6; font-size:12px; padding:0 24px 40px; }}
</style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>徐汇区物业投诉数据分析 · 课题一期成果</h1>
    <p>数据周期 2024 年 1 月 — 2026 年 8 月 ｜ 密度单位：件/千户 ｜ 纳统口径：993 个小区</p>
    <div class="kpis">
      <div class="kpi"><b>13,726</b>件 · 2026年1-8月投诉量</div>
      <div class="kpi"><b>-13.1%</b>同比（全区口径）</div>
      <div class="kpi"><b>4,908</b>件 · 判定重复（去重率 35.8%）</div>
      <div class="kpi"><b>772</b>个 · 参评高风险小区</div>
      <div class="kpi"><b>{n}</b>份报告</div>
    </div>
  </div>
</header>
<main class="wrap">
{body}
</main>
<footer>
  由脚本 <code>scripts/build_publish_site.py</code> 生成 ｜ 报告口径以《网页版整改清单（技术方执行版）》与《版本更新记录》为准
</footer>
</body>
</html>
"""


def collect_assets():
    """返回需要复制的资源文件相对路径列表"""
    got = []
    for d in ASSET_DIRS:
        src = os.path.join(ROOT, d)
        if not os.path.isdir(src):
            continue
        for dirpath, _dirs, files in os.walk(src):
            for fn in files:
                if fn.startswith("."):
                    continue
                full = os.path.join(dirpath, fn)
                got.append(os.path.relpath(full, ROOT))
    return sorted(got)


def referenced_local(html_text):
    """提取报告里引用的本地资源（排除外链/锚点/data URI）"""
    out = set()
    for m in re.finditer(r'(?:src|href)\s*=\s*"([^"]+)"', html_text):
        u = m.group(1).strip()
        if u.startswith(("http://", "https://", "//", "#", "data:", "mailto:", "javascript:", "computer:")):
            continue
        out.add(u.split("#")[0])
    return out


def main():
    check_only = "--check" in sys.argv
    problems = []

    # 1) 源文件必须存在
    for f, *_ in PAGES:
        if not os.path.isfile(os.path.join(ROOT, f)):
            problems.append(f"源文件缺失：{f}")
    if problems:
        print("\n".join("❌ " + p for p in problems)); return 1

    meta = {f: (cat, title, desc) for f, cat, title, desc in PAGES}
    index_html = build_index_html(meta)
    assets = collect_assets()

    expected = {f for f, *_ in PAGES} | set(assets) | {"index.html"}

    # 2) 复制
    if not check_only:
        if os.path.isdir(OUT):
            shutil.rmtree(OUT)
        os.makedirs(OUT, exist_ok=True)
        for f in [f for f, *_ in PAGES] + assets:
            dst = os.path.join(OUT, f)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, f), dst)
        with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as fp:
            fp.write(index_html)

    # 3) 断言
    actual = set()
    for dirpath, _d, files in os.walk(OUT):
        for fn in files:
            if fn.startswith("."):
                continue
            actual.add(os.path.relpath(os.path.join(dirpath, fn), OUT))

    # 3.1 清单一致
    if actual != expected:
        problems.append(f"文件清单不一致：多出 {sorted(actual - expected)}；缺少 {sorted(expected - actual)}")

    # 3.2 敏感文件兜底
    for rel in actual:
        if os.path.splitext(rel)[1].lower() in FORBIDDEN_EXT:
            problems.append(f"发布目录出现禁止的敏感/非静态文件：{rel}")

    # 3.3 报告内引用的本地资源必须都已复制（相对「引用者所在目录」解析，非站点根）
    for f, *_ in PAGES:
        p = os.path.join(OUT, f)
        if not os.path.isfile(p):
            continue
        base = os.path.dirname(f)
        for ref in referenced_local(open(p, encoding="utf-8", errors="ignore").read()):
            if not ref.endswith((".html", ".js", ".css", ".png", ".jpg", ".svg")):
                continue
            resolved = os.path.normpath(os.path.join(base, ref)) if base else os.path.normpath(ref)
            if resolved not in actual:
                problems.append(f"{f} 引用了未发布的本地资源：{ref}（解析为 {resolved}）")

    # 3.4 门户页链接可达
    for f, *_ in PAGES:
        if f not in index_html:
            problems.append(f"门户页缺少入口：{f}")

    # 3.5 成果总览分类计数与卡片结构一致（「N项已完成 · 含M项附件」一律脚本生成，禁止手填）
    sync = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_overview_counts.py")
    if os.path.isfile(sync):
        r = subprocess.run([sys.executable, sync, "--check"], capture_output=True, text=True)
        if r.returncode != 0:
            detail = "；".join(ln.strip() for ln in (r.stdout or "").splitlines()
                               if "→" in ln or "❌" in ln)
            problems.append("成果总览分类计数与卡片结构不符（跑 scripts/sync_overview_counts.py 校正）"
                            + (f"：{detail}" if detail else ""))

    # 4) 汇总
    total = sum(os.path.getsize(os.path.join(OUT, r)) for r in actual) if os.path.isdir(OUT) else 0
    print(f"{'【校验】' if check_only else '【构建】'} {OUT}")
    print(f"  页面 {len(PAGES)} 份 · 资源 {len(assets)} 个 · 合计 {len(actual)} 文件 · {total/1024/1024:.2f} MB")
    print(f"  门户 index.html {len(index_html)} 字符 · 分 {len(CAT_ORDER)} 类")
    if problems:
        print("\n".join("  ❌ " + p for p in problems))
        print(f"\n断言未通过：{len(problems)} 项")
        return 1
    print("  ✅ 断言全通过（清单一致 / 无敏感文件 / 本地资源齐备 / 门户入口完整 / 分类计数一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
