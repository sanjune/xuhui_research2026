"""
验收现场演示演练脚本 (阶段10)
============================
按需求文档 7.1 节 8 个问题顺序,加上 1 个上下文追问,完整跑一遍:
Q1 → Q2 → Q3 → [追问]那停车类呢？ → Q4 → Q5 → Q6 → Q7 → Q8(自由提问)

用法:
    python3 scripts/run_demo_rehearsal.py
产出:
    demo_rehearsal_report.json  (原始结果)
    验收演练报告.html           (可视化报告)
"""
import os
import sys
import time
import json
import urllib.request
import urllib.error
import html

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

API_URL = "http://localhost:8000/api/chat"
BEARER = "xuhui-demo-2026"
SESSION_ID = "demo_rehearsal_v1_" + str(int(time.time()))

# ============================================================
# 验收 8 个问题(需求文档 7.1 节)
# ============================================================
DEMO_FLOW = [
    {
        "step": "Q1",
        "title": "综合概览",
        "expected_intent": "summary",
        "expected_hints": ["2097", "-0.2%", "+13.0%", "房屋维修", "漕河泾"],
        "question": "这个月全区投诉情况怎么样？",
    },
    {
        "step": "Q2",
        "title": "趋势对比",
        "expected_intent": "trend",
        "expected_hints": ["2026", "2025", "同比", "-"],
        "question": "今年的投诉量和去年比，降了没有？",
    },
    {
        "step": "Q3",
        "title": "街道排行",
        "expected_intent": "ranking",
        "expected_hints": ["漕河泾", "226"],
        "question": "本月投诉量最多的5个街道是哪些？",
    },
    # -------- 插入上下文追问(展示上下文继承能力) --------
    {
        "step": "Q3.5",
        "title": "上下文追问→停车类",
        "expected_intent": "category",
        "expected_hints": ["停车管理", "263"],
        "question": "那停车类呢？",
        "note": '从 Q3 继承 month=7,无需再提"本月"',
    },
    {
        "step": "Q4",
        "title": "类别深挖",
        "expected_intent": "category",
        "expected_hints": ["停车管理", "小区"],
        "question": "停车类投诉主要集中在哪些小区？",
    },
    {
        "step": "Q5",
        "title": "企业对比",
        "expected_intent": "comparison",
        "expected_hints": ["徐房集团", "城投集团", "746"],
        "question": "徐房集团和城投集团今年表现怎么样？",
    },
    {
        "step": "Q6",
        "title": "重复投诉",
        "expected_intent": "repeat",
        "expected_hints": ["重复", "小区", "率"],
        "question": "重复投诉率是多少？哪些小区最严重？",
    },
    {
        "step": "Q7",
        "title": "热点小区",
        "expected_intent": "hotspot",
        "expected_hints": ["增长最快", "+"],
        "question": "哪些小区今年投诉增长最快？",
    },
    {
        "step": "Q8",
        "title": "自由提问(领导追问)",
        "expected_intent": "property",
        "expected_hints": ["物业", "企业"],
        "question": "今年投诉最少、表现最好的物业企业是哪家？",
    },
]


def call_chat_api(message: str, session_id: str) -> dict:
    """调用 /api/chat 接口"""
    payload = json.dumps({"message": message, "session_id": session_id}).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {BEARER}",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    data["_wall_time_ms"] = int((time.perf_counter() - t0) * 1000)
    return data


def evaluate(step: dict, resp: dict) -> dict:
    """评估单个问题的响应是否通过"""
    intent_ok = resp.get("raw_intent") == step["expected_intent"]
    time_ok = resp.get("query_time_ms", 99999) <= 3000
    reply = resp.get("reply", "") or ""
    hints_hit = 0
    for h in step["expected_hints"]:
        if h in reply or (resp.get("table") and h in str(resp["table"])):
            hints_hit += 1
    hints_ratio = hints_hit / max(1, len(step["expected_hints"]))
    hints_ok = hints_ratio >= 0.5
    passed = intent_ok and time_ok and hints_ok
    return {
        "intent_ok": intent_ok,
        "time_ok": time_ok,
        "hints_hit": hints_hit,
        "hints_total": len(step["expected_hints"]),
        "hints_ratio": round(hints_ratio, 2),
        "hints_ok": hints_ok,
        "passed": passed,
        "fail_reasons": [r for r, ok in [
            ("意图识别错误", intent_ok),
            ("响应超时(>3秒)", time_ok),
            (f"关键词命中率不足({hints_hit}/{len(step['expected_hints'])})", hints_ok),
        ] if not ok],
    }


def main():
    print("=" * 70)
    print("徐汇区物业投诉 AI 智能体 — 验收现场演示演练")
    print("=" * 70)
    print(f"会话 ID: {SESSION_ID}")
    print(f"API:     {API_URL}")
    print()

    results = []
    pass_count = 0
    total_wall = 0

    for step in DEMO_FLOW:
        print(f"[{step['step']}] {step['title']}")
        print(f"     问题: {step['question']}")
        if step.get("note"):
            print(f"     说明: {step['note']}")

        try:
            resp = call_chat_api(step["question"], SESSION_ID)
        except Exception as e:
            print(f"     [ERROR] API 调用失败: {e}")
            results.append({
                "step": step["step"], "title": step["title"],
                "question": step["question"], "note": step.get("note"),
                "error": str(e), "passed": False,
            })
            print()
            continue

        eval_res = evaluate(step, resp)
        passed = eval_res["passed"]
        if passed:
            pass_count += 1
        total_wall += resp.get("_wall_time_ms", 0)

        print(f"     意图识别: {resp.get('raw_intent')} {'✅' if eval_res['intent_ok'] else '❌ (期望'+step['expected_intent']+')'}")
        print(f"     API耗时 : {resp.get('query_time_ms')}ms  {'✅' if eval_res['time_ok'] else '❌ (>3s)'}")
        print(f"     总耗时  : {resp.get('_wall_time_ms')}ms")
        print(f"     关键词  : {eval_res['hints_hit']}/{eval_res['hints_total']}  {'✅' if eval_res['hints_ok'] else '❌'}")
        print(f"     结果    : {'✅ 通过' if passed else '❌ 失败: ' + ', '.join(eval_res['fail_reasons'])}")
        reply_head = (resp.get("reply") or "").replace("\n", " ")[:140]
        print(f"     总结摘要: {reply_head}...")
        if resp.get("table"):
            n_rows = len(resp["table"].get("rows", []))
            print(f"     表格    : {len(resp['table'].get('headers', []))}列 × {n_rows}行")
        print()

        results.append({
            "step": step["step"],
            "title": step["title"],
            "question": step["question"],
            "note": step.get("note"),
            "expected_intent": step["expected_intent"],
            "response": {
                "raw_intent": resp.get("raw_intent"),
                "reply": resp.get("reply"),
                "table": resp.get("table"),
                "query_time_ms": resp.get("query_time_ms"),
                "wall_time_ms": resp.get("_wall_time_ms"),
                "session_id": resp.get("session_id"),
            },
            "evaluation": eval_res,
            "passed": passed,
        })

    # ============================================================
    # 汇总
    # ============================================================
    total = len(DEMO_FLOW)
    pass_rate = pass_count / total * 100
    avg_time = sum(r["response"].get("query_time_ms", 0) for r in results if r.get("response")) / max(1, pass_count)
    max_time = max((r["response"].get("query_time_ms", 0) for r in results if r.get("response")), default=0)
    min_time = min((r["response"].get("query_time_ms", 0) for r in results if r.get("response")), default=99999)

    print("=" * 70)
    print(f"演示演练汇总: {pass_count}/{total} 通过 ({pass_rate:.1f}%)   总耗时: {total_wall}ms")
    print(f"平均 API 耗时: {avg_time:.0f}ms  最快: {min_time}ms  最慢: {max_time}ms")
    print("=" * 70)

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "session_id": SESSION_ID,
        "summary": {
            "total": total,
            "passed": pass_count,
            "failed": total - pass_count,
            "pass_rate_pct": round(pass_rate, 1),
            "total_wall_time_ms": total_wall,
            "avg_query_time_ms": round(avg_time, 1),
            "max_query_time_ms": max_time,
            "min_query_time_ms": min_time,
        },
        "results": results,
    }

    # 保存原始 JSON
    json_path = os.path.join(BASE_DIR, "demo_rehearsal_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n原始结果已保存: {json_path}")

    # 生成 HTML 报告
    html_path = os.path.join(BASE_DIR, "验收演练报告.html")
    render_html_report(report, html_path)
    print(f"HTML 报告已生成: {html_path}")

    return 0 if pass_count == total else 1


# ============================================================
# HTML 报告渲染
# ============================================================
def render_html_report(report: dict, path: str):
    s = report["summary"]
    overall_status = "✅ 全部通过" if s["passed"] == s["total"] else f"⚠️ {s['failed']} 项失败"
    color_green = "#16a34a"
    color_red = "#dc2626"
    color_amber = "#d97706"

    result_rows_html = ""
    for r in report["results"]:
        ev = r.get("evaluation") or {}
        resp = r.get("response") or {}
        passed_class = "pass" if r.get("passed") else "fail"
        status_text = "✅ 通过" if r.get("passed") else "❌ 失败"
        fail_reasons = "<br>".join(html.escape(x) for x in ev.get("fail_reasons", [])) or "—"

        # 渲染表格
        table_html = ""
        tbl = resp.get("table")
        if tbl and tbl.get("headers") and tbl.get("rows"):
            ths = "".join(f"<th>{html.escape(str(h))}</th>" for h in tbl["headers"])
            trs = ""
            for row in tbl["rows"]:
                tds = "".join(
                    f"<td class='num'>{x}</td>" if isinstance(x, (int, float))
                    else f"<td>{html.escape(str(x))}</td>" for x in row
                )
                trs += f"<tr>{tds}</tr>"
            table_html = f"<div class='table-wrap'><table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>"

        reply_html = html.escape(resp.get("reply", "") or "").replace("\n", "<br>")

        result_rows_html += f"""
<div class="case {passed_class}">
  <div class="case-header">
    <span class="step-tag">{r['step']}</span>
    <span class="case-title">{html.escape(r['title'])}</span>
    <span class="case-status {'status-pass' if r.get('passed') else 'status-fail'}">{status_text}</span>
  </div>
  <div class="case-body">
    <div class="case-meta">
      <div><b>问题:</b> {html.escape(r['question'])}</div>
      {f'<div><i>说明:</i> {html.escape(r["note"])}</div>' if r.get('note') else ''}
      <div class="metrics">
        <span>意图: <b>{html.escape(resp.get('raw_intent',''))}</b> {'✅' if ev.get('intent_ok') else '❌'}</span>
        <span>API耗时: <b>{resp.get('query_time_ms')}ms</b> {'✅' if ev.get('time_ok') else '❌'}</span>
        <span>关键词: <b>{ev.get('hints_hit',0)}/{ev.get('hints_total',0)}</b> {'✅' if ev.get('hints_ok') else '❌'}</span>
      </div>
      <div class="fail-reason"><b>失败原因:</b> {fail_reasons}</div>
    </div>
    <div class="case-reply">
      <div class="reply-label">💡 LLM 智能总结</div>
      <div class="reply-text">{reply_html}</div>
    </div>
    {table_html}
  </div>
</div>
"""

    # 图表:响应时间柱状图(SVG 手绘)
    times = [r["response"].get("query_time_ms", 0) for r in report["results"] if r.get("response")]
    labels = [r["step"] for r in report["results"] if r.get("response")]
    max_t = max(times + [3000])
    bars = ""
    cum_x = 40
    bar_w = 60
    gap = 24
    chart_h = 280
    chart_w = cum_x + (bar_w + gap) * len(times) + 40
    for i, t in enumerate(times):
        h = int(t / max_t * (chart_h - 60))
        color = color_green if t <= 3000 else color_red
        x = cum_x + i * (bar_w + gap)
        y = chart_h - 30 - h
        bars += f'<rect x="{x}" y="{y}" width="{bar_w}" height="{h}" fill="{color}" rx="4"/>'
        bars += f'<text x="{x + bar_w/2}" y="{chart_h - 10}" text-anchor="middle" font-size="12" fill="#475569">{labels[i]}</text>'
        bars += f'<text x="{x + bar_w/2}" y="{y - 6}" text-anchor="middle" font-size="11" fill="#334155">{t}ms</text>'
    # 3s 阈值线
    threshold_y = chart_h - 30 - int(3000 / max_t * (chart_h - 60))
    bars += f'<line x1="30" y1="{threshold_y}" x2="{chart_w-10}" y2="{threshold_y}" stroke="{color_amber}" stroke-dasharray="6 4" stroke-width="1.5"/>'
    bars += f'<text x="30" y="{threshold_y - 4}" font-size="11" fill="{color_amber}">3s 阈值线</text>'

    report_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>徐汇区物业 AI 智能体验收演练报告</title>
<style>
body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; margin: 0; padding: 32px; background: #f1f5f9; color: #0f172a; }}
.container {{ max-width: 1100px; margin: 0 auto; }}
h1 {{ margin: 0 0 8px; font-size: 28px; }}
.sub {{ color: #64748b; margin-bottom: 28px; font-size: 14px; }}
.overview {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap: 16px; margin-bottom: 28px; }}
.card {{ background: #fff; border-radius: 12px; padding: 18px 20px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
.card .label {{ font-size: 12px; color: #64748b; margin-bottom: 6px; }}
.card .value {{ font-size: 26px; font-weight: 700; }}
.card .value.green {{ color: {color_green}; }}
.card .value.red {{ color: {color_red}; }}
.card .value.amber {{ color: {color_amber}; }}
.card .unit {{ font-size: 13px; color: #64748b; font-weight: 400; margin-left: 4px; }}
.bigstatus {{ font-size: 22px; font-weight: 700; color: {color_green if s['passed']==s['total'] else color_amber}; }}
.chart-box {{ background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.06); margin-bottom: 28px; overflow-x: auto; }}
.chart-title {{ font-size: 16px; font-weight: 600; margin-bottom: 12px; }}
.case {{ background: #fff; border-radius: 12px; padding: 18px 22px; margin-bottom: 18px; box-shadow: 0 1px 3px rgba(0,0,0,.06); border-left: 6px solid {color_green}; }}
.case.fail {{ border-left-color: {color_red}; }}
.case-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }}
.step-tag {{ background: #1e293b; color: #fff; padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; }}
.case-title {{ font-size: 17px; font-weight: 600; flex: 1; }}
.case-status {{ padding: 3px 10px; border-radius: 6px; font-size: 13px; font-weight: 600; }}
.status-pass {{ background: #dcfce7; color: {color_green}; }}
.status-fail {{ background: #fee2e2; color: {color_red}; }}
.case-body {{ display: grid; grid-template-columns: 340px 1fr; gap: 18px; }}
@media (max-width: 800px) {{ .case-body {{ grid-template-columns: 1fr; }} }}
.case-meta {{ background: #f8fafc; border-radius: 8px; padding: 12px 14px; font-size: 13px; line-height: 1.8; }}
.case-meta .metrics {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }}
.case-meta .metrics span {{ background: #fff; padding: 2px 8px; border-radius: 6px; font-size: 12px; border: 1px solid #e2e8f0; }}
.fail-reason {{ margin-top: 6px; color: {color_red}; font-size: 12px; }}
.case-reply {{ background: linear-gradient(135deg, #eff6ff 0%, #eef2ff 100%); border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; }}
.reply-label {{ font-size: 12px; color: #3730a3; font-weight: 600; margin-bottom: 6px; }}
.reply-text {{ font-size: 14px; color: #1e1b4b; line-height: 1.7; }}
.table-wrap {{ overflow-x: auto; border: 1px solid #e2e8f0; border-radius: 8px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th {{ background: #f1f5f9; padding: 8px 12px; text-align: left; border-bottom: 1px solid #e2e8f0; font-weight: 600; }}
td {{ padding: 7px 12px; border-bottom: 1px solid #f1f5f9; }}
tr:nth-child(even) td {{ background: #fafafa; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.footer {{ text-align: center; margin-top: 30px; color: #94a3b8; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <h1>🏛️ 徐汇区物业投诉 AI 智能体 — 验收演示演练报告</h1>
  <div class="sub">生成时间: {report['generated_at']} ｜ 会话ID: {report['session_id']} ｜ 按需求文档 7.1 节 Q1-Q8 顺序 + 1 追问</div>

  <div class="overview">
    <div class="card">
      <div class="label">整体结果</div>
      <div class="bigstatus">{overall_status}</div>
    </div>
    <div class="card">
      <div class="label">通过率</div>
      <div class="value {'green' if s['pass_rate_pct']>=90 else ('amber' if s['pass_rate_pct']>=70 else 'red')}">{s['pass_rate_pct']}<span class="unit">% ({s['passed']}/{s['total']})</span></div>
    </div>
    <div class="card">
      <div class="label">平均响应时间</div>
      <div class="value {'green' if s['avg_query_time_ms'] <= 2000 else ('amber' if s['avg_query_time_ms'] <= 3000 else 'red')}">{s['avg_query_time_ms']}<span class="unit">ms</span></div>
    </div>
    <div class="card">
      <div class="label">最快 / 最慢</div>
      <div class="value">{s['min_query_time_ms']}<span class="unit">ms</span> / {s['max_query_time_ms']}<span class="unit">ms</span></div>
    </div>
    <div class="card">
      <div class="label">演练总耗时(串行)</div>
      <div class="value">{round(s['total_wall_time_ms']/1000, 2)}<span class="unit">秒</span></div>
    </div>
  </div>

  <div class="chart-box">
    <div class="chart-title">⏱️ 各问题响应时间 (目标 ≤ 3000ms)</div>
    <svg width="{chart_w}" height="{chart_h}" viewBox="0 0 {chart_w} {chart_h}">
      <line x1="30" y1="10" x2="30" y2="{chart_h-30}" stroke="#cbd5e1"/>
      {bars}
    </svg>
  </div>

  <h2 style="font-size:20px; margin-bottom:14px;">📋 逐项详情</h2>

  {result_rows_html}

  <div class="footer">© 2026 徐汇区物业课题一期 · AI 智能体验收演示演练 · FastAPI + SQLite + 通义千问 Qwen-Turbo</div>
</div>
</body>
</html>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_html)


if __name__ == "__main__":
    sys.exit(main())
