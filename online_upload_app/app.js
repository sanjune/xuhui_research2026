/**
 * app.js — 12345 物业工单日报 共享模块
 *
 * 三页共用：upload.html（上传解析） / index.html（日历索引） / report.html（日报详情）
 *
 * 组成：
 *   1. PUBLIC_CONFIG + SDK 初始化（WorkBuddyCloud，对标 Supabase）
 *   2. PII 脱敏（与 scripts/seed_daily_reports.py 完全一致）
 *   3. Excel 解析（SheetJS）+ 按工单日期分组
 *   4. 统计逻辑（seed_daily_reports.py:extract_for_date 的 JS 移植，逐字段一致）
 *   5. 日报渲染模板（gen_daily_report_1009.py 模板的 JS 移植）
 *   6. DB 读写（daily_reports 表：upsert / select）
 *
 * 兼容浏览器（window.DailyReportApp）与 Node（module.exports，供回归测试）。
 */
(function (global) {
  'use strict';

  // ============ 1. 配置与 SDK ============
  const PUBLIC_CONFIG = {
    endpoint: 'https://xuhui-property-reports.app.workbuddy.host',
    publishableKey: 'wbpk_VPtKCSEAs0RVwIWRwLF3mX_Fq068wzA24qbRoolk2UiUPvE40GiieUk'
  };
  const TABLE = 'daily_reports';

  let _cloudPromise = null;
  function getCloud() {
    if (!_cloudPromise) {
      if (typeof WorkBuddyCloud === 'undefined') {
        return Promise.reject(new Error('WorkBuddyCloud SDK 未加载（检查 CDN <script>）'));
      }
      _cloudPromise = WorkBuddyCloud.createWorkBuddyCloud(PUBLIC_CONFIG);
    }
    return _cloudPromise;
  }

  // ============ 2. PII 脱敏（seed_daily_reports.py 同款） ============
  const RE_PHONE = /1[3-9]\d{9}/g;
  const RE_IDCARD = /\d{17}[\dXx]/g;
  const RE_EMAIL = /[\w.-]+@[\w.-]+\.\w+/g;

  function maskPii(text) {
    let t = String(text == null ? '' : text);
    t = t.replace(/1[3-9]\d{9}/g, '[手机]');
    t = t.replace(/\d{17}[\dXx]/g, '[证件]');
    t = t.replace(/[\w.-]+@[\w.-]+\.\w+/g, '[邮箱]');
    return t;
  }

  function cleanProb(prob) {
    let s = String(prob == null ? '' : prob).trim();
    s = s.replace(/\s+/g, ' ');
    s = maskPii(s);
    if (s.length > 60) s = s.slice(0, 60) + '…';
    return s || '—';
  }

  /** 交付自检：report_data 不得残留手机号/证件号/邮箱（正则同脱敏三条规则） */
  function assertNoPii(reportData, label) {
    const raw = JSON.stringify(reportData);
    const checks = [
      [new RegExp(RE_PHONE.source), '手机号'],
      [new RegExp(RE_IDCARD.source), '证件号'],
      [new RegExp(RE_EMAIL.source), '邮箱'],
    ];
    for (const [rx, name] of checks) {
      const hits = raw.match(rx);
      if (hits) throw new Error(`PII 断言失败：${name} 残留 (${label || ''}): ${hits.slice(0, 3).join(', ')}`);
    }
  }

  // ============ 3. 基础工具 ============
  const STREET_ORDER = ['枫林路街道', '斜土路街道', '漕河泾街道', '天平路街道', '虹梅路街道',
    '徐家汇街道', '康健新村街道', '田林街道', '长桥街道', '龙华街道',
    '华泾镇', '湖南路街道', '凌云路街道', '__未匹配__'];
  const WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日'];
  const WEEKDAYS_SHORT = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

  /** Python round() 半舍入到偶数（banker's rounding）— 保证与 DB 种子数据逐位一致 */
  function pyRound(x, d) {
    d = (d == null) ? 1 : d;
    const f = Math.pow(10, d);
    const y = x * f;
    const near = Math.round(y);
    // 恰在 .5 边界（含 FP 误差）→ 取偶数
    if (Math.abs(Math.abs(y - Math.floor(y)) - 0.5) < 1e-9) {
      const k = Math.floor(y);
      return ((k % 2 === 0) ? k : k + 1) / f;
    }
    return near / f;
  }

  /** Python f'{x:.0f}'（半偶舍入取整） */
  function pyRound0(x) { return pyRound(x, 0); }

  /** 计数统计：保持首次出现顺序，按计数降序稳定排序（对齐 pandas value_counts） */
  function valueCounts(rows, keyFn) {
    const map = new Map();
    for (const r of rows) {
      const k = keyFn(r);
      map.set(k, (map.get(k) || 0) + 1);
    }
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1]);
  }

  const pad2 = (n) => String(n).padStart(2, '0');

  /** processtime → 'YYYY-MM-DD'（支持字符串/Date/Excel 序列号），无法解析返回 null */
  function parseDateSlug(v) {
    if (v == null || v === '') return null;
    if (v instanceof Date && !isNaN(v)) {
      return `${v.getFullYear()}-${pad2(v.getMonth() + 1)}-${pad2(v.getDate())}`;
    }
    if (typeof v === 'number') {
      // Excel 序列号（1900 日期系统）
      const ms = Math.round((v - 25569) * 86400 * 1000);
      const d = new Date(ms);
      return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
    }
    const m = String(v).trim().match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
    if (m) return `${m[1]}-${pad2(+m[2])}-${pad2(+m[3])}`;
    return null;
  }

  function weekdayIndexOfSlug(slug) {
    const [y, m, d] = slug.split('-').map(Number);
    return (new Date(y, m - 1, d).getDay() + 6) % 7; // 周一=0 … 周日=6
  }

  // ============ 4. 统计逻辑（extract_for_date 的 JS 移植） ============
  /**
   * @param {Array<Object>} rows 当日工单（sheet_to_json 行对象）
   * @param {string} dateSlug 'YYYY-MM-DD'
   * @param {string} srcName 源文件名
   * @returns {{summary: Object, reportData: Object}}
   */
  function extractForDate(rows, dateSlug, srcName) {
    const total = rows.length;
    const wIdx = weekdayIndexOfSlug(dateSlug);
    const [y, m, d] = dateSlug.split('-').map(Number);
    const dateCn = `${y}年${m}月${d}日`;
    const weekdayFull = WEEKDAYS[wIdx];

    // 街道归并：s30_str_name 空值/无// → __未匹配__
    const streetOf = (r) => {
      const v = r.s30_str_name;
      if (v == null || String(v).trim() === '') return '__未匹配__';
      const s = String(v);
      if (s === '无' || s === '/') return '__未匹配__';
      return s;
    };

    // 街镇汇总（按 STREET_ORDER 遍历，再按 n 降序稳定排序）
    const rows0 = [];
    for (const st of STREET_ORDER) {
      const sub = rows.filter((r) => streetOf(r) === st);
      if (sub.length === 0) continue;
      const n = sub.length;
      const subTyped = valueCounts(sub, (r) => (r.problemtyped == null ? '未分类' : String(r.problemtyped))).slice(0, 3);
      const mainCat = subTyped.map(([k, v]) => `${k} ${v}`).join('、');
      const rep = sub.filter((r) => String(r.is_repeat) === '是').length;
      const repRate = pyRound(rep / n * 100, 1);
      const label = st === '__未匹配__' ? '待关联街道' : st;
      rows0.push({ street: label, n: n, mainCat: mainCat, rep: rep, repRate: repRate });
    }
    rows0.sort((a, b) => b.n - a.n); // 稳定排序，并列保持 STREET_ORDER

    // 最细一级分类全量统计
    const typedOf = (r) => (r.problemtyped == null ? '未分类' : String(r.problemtyped));
    const typedFull = valueCounts(rows, typedOf).map(([k, v]) => {
      const matchedSub = rows.filter((r) => typedOf(r) === k && streetOf(r) !== '__未匹配__');
      const nSt = new Set(matchedSub.map(streetOf)).size;
      return { name: k, count: v, pct: pyRound(v / total * 100, 1), streets: nSt };
    });

    const srcVC = valueCounts(rows, (r) => (r.hotlinesource == null ? '未知' : String(r.hotlinesource)));
    const typeVC = valueCounts(rows, (r) => (r.hotlinetype == null ? '未标注' : String(r.hotlinetype)));
    const pbVC = valueCounts(rows, (r) => (r.problemtypeb == null ? '未分类' : String(r.problemtypeb)));

    const repTotal = rows.filter((r) => String(r.is_repeat) === '是').length;
    const repRateTotal = pyRound(repTotal / total * 100, 1);

    const matched = rows0.filter((r) => r.street !== '待关联街道').reduce((s, r) => s + r.n, 0);
    const unmatched = rows0.filter((r) => r.street === '待关联街道').reduce((s, r) => s + r.n, 0);

    // 重点街镇：当日工单 ≥6 件 或 重复率 ≥40%
    const focus = rows0.filter((r) => (r.n >= 6 || r.repRate >= 40) && r.street !== '待关联街道');

    const focusStreets = focus.map((r) => {
      const stKey = r.street === '待关联街道' ? '__未匹配__' : r.street;
      const repRows = rows.filter((rr) => streetOf(rr) === stKey && String(rr.is_repeat) === '是');
      const repeatCases = repRows.map((row) => ({
        addr: maskPii(String(row.appealaddr == null ? '' : row.appealaddr).trim()) || '—',
        typed: String(row.problemtyped == null ? '' : row.problemtyped).trim() || '—',
        prob: cleanProb(row.problem),
      }));
      return {
        street: r.street, n: r.n, mainCat: r.mainCat, rep: r.rep,
        repRate: r.repRate, repeatCases: repeatCases,
      };
    });

    const mainCatList = valueCounts(rows, typedOf).slice(0, 3).map(([k, v]) => `${k} ${v}`);

    const summary = {
      report_date: dateSlug,
      weekday: WEEKDAYS_SHORT[wIdx],
      total: total,
      matched: matched,
      unmatched: unmatched,
      rep: repTotal,
      rep_rate: repRateTotal,
      streets: rows0.filter((r) => r.street !== '待关联街道').length,
      main_cat: mainCatList,
    };

    const now = new Date();
    const reportData = {
      dateCn: dateCn,
      weekdayFull: weekdayFull,
      srcName: srcName,
      generatedAt: `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())} ${pad2(now.getHours())}:${pad2(now.getMinutes())}`,
      streetRows: rows0,
      categoryStats: {
        typed: typedFull,
        source: srcVC.map(([k, v]) => ({ name: k, count: v })),
        type: typeVC.map(([k, v]) => ({ name: k, count: v })),
        problemTypeB: pbVC.map(([k, v]) => ({ name: k, count: v })),
      },
      focusStreets: focusStreets,
    };

    assertNoPii(reportData, dateSlug);
    return { summary: summary, reportData: reportData };
  }

  /**
   * SheetJS 工作簿 → 全部日报记录（按 processtime 日期分组，多日期分别生成）
   * @param {ArrayBuffer|Uint8Array} buf xlsx 文件二进制
   * @param {string} srcName 源文件名
   * @returns {{records: Array, skipped: number}} records: summary+report_data 合并对象
   */
  function buildRecordsFromWorkbook(buf, srcName) {
    const XLSX = global.XLSX;
    if (!XLSX) throw new Error('SheetJS (XLSX) 未加载（检查 CDN <script>）');
    const wb = XLSX.read(buf, { type: 'array' });
    const ws = wb.Sheets[wb.SheetNames[0]];
    const allRows = XLSX.utils.sheet_to_json(ws, { raw: false, defval: null });

    // 按日期分组（保持出现顺序，最后按日期升序输出）
    const groups = new Map();
    let skipped = 0;
    for (const r of allRows) {
      const slug = parseDateSlug(r.processtime);
      if (!slug) { skipped++; continue; }
      if (!groups.has(slug)) groups.set(slug, []);
      groups.get(slug).push(r);
    }

    const records = [];
    for (const slug of Array.from(groups.keys()).sort()) {
      const { summary, reportData } = extractForDate(groups.get(slug), slug, srcName);
      records.push(Object.assign({}, summary, { report_data: reportData }));
    }
    return { records: records, skipped: skipped };
  }

  // ============ 5. DB 读写 ============
  async function upsertReport(record) {
    const cloud = await getCloud();
    return cloud.database.from(TABLE)
      .upsert({
        report_date: record.report_date,
        weekday: record.weekday,
        total: record.total,
        matched: record.matched,
        unmatched: record.unmatched,
        rep: record.rep,
        rep_rate: record.rep_rate,
        streets: record.streets,
        main_cat: record.main_cat,
        report_data: record.report_data,
      }, { onConflict: 'report_date' })
      .select();
  }

  async function fetchAllReports() {
    const cloud = await getCloud();
    return cloud.database.from(TABLE)
      .select('report_date, weekday, total, matched, unmatched, rep, rep_rate, streets, main_cat')
      .order('report_date', { ascending: true });
  }

  async function fetchReport(date) {
    const cloud = await getCloud();
    const { data, error } = await cloud.database.from(TABLE)
      .select('*').eq('report_date', date);
    return { data: (data && data[0]) || null, error: error || null };
  }

  async function deleteReport(date) {
    const cloud = await getCloud();
    return cloud.database.from(TABLE).delete().eq('report_date', date);
  }

  // ============ 6. 日报渲染模板（gen_daily_report_1009.py 模板移植） ============
  function bar(val, mx, color) {
    const w = mx ? (val / mx * 100) : 0;
    return `<div class="bar-track"><div class="bar-fill" style="width:${w.toFixed(1)}%;background:${color || '#3b82f6'}"></div></div>`;
  }

  const esc = (s) => String(s == null ? '' : s);

  /**
   * 渲染完整日报 HTML（与 Python 版模板同构）
   * @param {Object} record DB 行（summary 字段 + report_data）
   * @param {string} backHref 返回按钮链接
   */
  function renderReportHTML(record, backHref) {
    const rd = record.report_data;
    // 数值字段防御性转换（NUMERIC 列经 PostgREST 可能返回字符串）
    const num = (v, dflt) => { const n = Number(v); return isNaN(n) ? (dflt || 0) : n; };
    const total = num(record.total);
    const repTotal = num(record.rep);
    const repRateTotal = num(record.rep_rate);
    const matched = num(record.matched);
    const unmatched = num(record.unmatched);
    const rows = rd.streetRows;
    const cat = rd.categoryStats;
    const focus = rd.focusStreets;
    const now = rd.generatedAt;

    const maxN = Math.max.apply(null, rows.map((r) => r.n));
    const tableRows = rows.map((r, i) => {
      const cls = (i % 2 === 1) ? ' class="alt"' : '';
      let flag = '';
      if (r.street === '待关联街道') flag = '<span class="tag warn">待关联</span>';
      else if (r.repRate >= 40) flag = '<span class="tag danger">重复高</span>';
      else if (r.n >= 10) flag = '<span class="tag info">量大</span>';
      const streetCell = flag ? `${r.street} ${flag}` : r.street;
      return `<tr${cls}>
      <td>${i + 1}</td>
      <td class="left">${streetCell}</td>
      <td class="num"><b>${r.n}</b></td>
      <td>${bar(r.n, maxN)}</td>
      <td class="left">${esc(r.mainCat)}</td>
      <td class="num">${r.rep}</td>
      <td class="num ${r.repRate >= 40 ? 'danger' : ''}">${pyRound0(r.repRate)}%</td>
    </tr>`;
    }).join('\n');

    const cards = `
  <div class="card"><div class="c-val">${total}</div><div class="c-lab">当日工单总量</div></div>
  <div class="card"><div class="c-val">${repTotal}</div><div class="c-lab">重复案件 · ${repRateTotal.toFixed(1)}%</div></div>
  <div class="card"><div class="c-val">${matched}</div><div class="c-lab">已关联街镇工单</div></div>
  <div class="card"><div class="c-val">${unmatched}</div><div class="c-lab">待关联街道工单</div></div>
  <div class="card"><div class="c-val">13</div><div class="c-lab">涉及街镇数</div></div>
`;

    const distRows = (arr, color) => {
      const mx = Math.max.apply(null, arr.map((x) => x.count));
      return arr.map((x) =>
        `<div class="dist-row"><span class="dist-lab">${esc(x.name)}</span>` +
        `<span class="dist-bar">${bar(x.count, mx, color)}</span>` +
        `<span class="dist-num">${x.count}</span></div>`).join('\n');
    };
    const srcItems = distRows(cat.source, '#6366f1');
    const typeItems = distRows(cat.type, '#0ea5e9');
    const pbItems = distRows(cat.problemTypeB, '#f59e0b');

    const topTyped = cat.typed.slice(0, 10);
    const mxTypedAll = Math.max.apply(null, cat.typed.map((x) => x.count));
    const typedItems = topTyped.map((x) =>
      `<div class="dist-row"><span class="dist-lab">${esc(x.name)}</span>` +
      `<span class="dist-bar">${bar(x.count, mxTypedAll, '#ef4444')}</span>` +
      `<span class="dist-num">${x.count}</span></div>`).join('\n');

    const pbCount = (name) => {
      const hit = cat.problemTypeB.find((x) => x.name === name);
      return hit ? hit.count : 0;
    };

    const focusHtml = focus.length === 0 ? '<p class="empty">暂无重点街镇。</p>' : focus.map((r) => {
      let repBlock = '';
      if (r.repeatCases && r.repeatCases.length) {
        const repItems = r.repeatCases.map((rc) =>
          `<div class="rep-row">` +
          `<span class="rep-addr">${esc(rc.addr)}</span>` +
          `<span class="rep-type">${esc(rc.typed)}</span>` +
          `<span class="rep-prob">${esc(rc.prob)}</span>` +
          `</div>`).join('');
        repBlock = `<div class="rep-list"><div class="rep-head">重复案件明细（${r.repeatCases.length} 件 · 地址 / 问题细类 / 问题摘要）</div>${repItems}</div>`;
      }
      return `<div class="focus-item"><div class="focus-head">` +
        `<span class="focus-name">${esc(r.street)}</span>` +
        `<span class="focus-n">${r.n} 件</span></div>` +
        `<div class="focus-meta">主要类别：${esc(r.mainCat)}` +
        ` · 重复案件 ${r.rep}（${pyRound0(r.repRate)}%）` +
        `</div>${repBlock}</div>`;
    }).join('\n');

    const maxTf = Math.max.apply(null, cat.typed.map((x) => x.count));
    const typedFullRows = cat.typed.map((t, i) => {
      const cls = (i % 2 === 1) ? ' class="alt"' : '';
      return `<tr${cls}>
      <td>${i + 1}</td>
      <td class="left">${esc(t.name)}</td>
      <td class="num"><b>${t.count}</b></td>
      <td class="num">${t.pct.toFixed(1)}%</td>
      <td>${bar(t.count, maxTf, '#ef4444')}</td>
      <td class="num">${t.streets}</td>
    </tr>`;
    }).join('\n');

    return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>徐汇区12345物业工单日报 · ${rd.dateCn}</title>
<style>
  :root {
    --bg:#f5f7fa; --card:#fff; --border:#e5e9f0; --txt:#1f2937; --muted:#6b7280;
    --accent:#3b82f6; --danger:#ef4444; --warn:#f59e0b; --info:#0ea5e9; --ok:#10b981;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:"PingFang SC","Microsoft YaHei","Helvetica Neue",sans-serif;
    background:var(--bg); color:var(--txt); line-height:1.6; padding:24px; }
  .wrap { max-width:1100px; margin:0 auto; }
  header { text-align:center; margin-bottom:24px; }
  header h1 { font-size:24px; color:#111827; margin-bottom:6px; }
  header .sub { color:var(--muted); font-size:14px; }
  header .meta { color:var(--muted); font-size:12px; margin-top:4px; }
  .cards { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:24px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:10px;
    padding:16px 8px; text-align:center; }
  .c-val { font-size:26px; font-weight:700; color:var(--accent); }
  .c-lab { font-size:12px; color:var(--muted); margin-top:4px; }
  section { background:var(--card); border:1px solid var(--border); border-radius:10px;
    padding:18px 20px; margin-bottom:20px; }
  section h2 { font-size:17px; color:#111827; border-left:4px solid var(--accent);
    padding-left:10px; margin-bottom:14px; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
  .grid3 { display:grid; grid-template-columns:1fr 1fr 1fr; gap:20px; }
  .dist-row { display:flex; align-items:center; gap:8px; margin-bottom:8px; font-size:13px; }
  .dist-lab { width:96px; text-align:right; color:var(--muted); flex-shrink:0; }
  .dist-bar { flex:1; }
  .dist-num { width:34px; text-align:right; font-weight:600; flex-shrink:0; }
  .bar-track { background:#eef1f6; border-radius:4px; height:14px; overflow:hidden; }
  .bar-fill { height:100%; border-radius:4px; transition:width .4s; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { padding:8px 6px; text-align:center; border-bottom:1px solid var(--border); }
  th { background:#f0f4f9; color:#374151; font-weight:600; white-space:nowrap; }
  td.num { font-variant-numeric:tabular-nums; }
  td.left { text-align:left; }
  td.danger { color:var(--danger); font-weight:600; }
  tr.alt { background:#fafbfc; }
  .tag { display:inline-block; font-size:11px; padding:1px 6px; border-radius:4px; margin-left:4px; }
  .tag.danger { background:#fee2e2; color:#b91c1c; }
  .tag.warn { background:#fef3c7; color:#92400e; }
  .tag.info { background:#dbeafe; color:#1e40af; }
  .focus-item { border-left:3px solid var(--accent); padding:10px 14px; background:#f8fafc;
    border-radius:0 8px 8px 0; margin-bottom:10px; }
  .focus-head { display:flex; justify-content:space-between; align-items:center; }
  .focus-name { font-weight:600; font-size:15px; }
  .focus-n { color:var(--accent); font-weight:700; }
  .focus-meta { font-size:13px; color:var(--muted); margin-top:2px; }
  .empty { color:var(--muted); }
  .rep-list { margin-top:10px; border-top:1px dashed var(--border); padding-top:8px; }
  .rep-head { font-size:13px; font-weight:600; color:#374151; margin-bottom:6px; }
  .rep-row { display:grid; grid-template-columns:110px 92px 1fr; gap:8px; font-size:12px;
    padding:5px 0; border-bottom:1px solid #f0f2f5; align-items:start; }
  .rep-addr { color:#374151; word-break:break-all; }
  .rep-type { color:#92400e; background:#fef3c7; padding:0 4px; border-radius:3px;
    text-align:center; height:fit-content; white-space:nowrap; }
  .rep-prob { color:var(--muted); word-break:break-all; }
  .note { font-size:12px; color:var(--muted); margin-top:10px; }
  footer { text-align:center; color:var(--muted); font-size:12px; padding:16px 0; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <a href="${backHref}" onclick="location.href='${backHref}';return false;" style="display:inline-block;font-size:13px;color:#9bb8e0;text-decoration:none;margin-bottom:10px;cursor:pointer;">← 返回日报日历索引</a>
    <h1>徐汇区12345物业工单日报</h1>
    <div class="sub">数据日期：${rd.dateCn}（${rd.weekdayFull}）</div>
    <div class="meta">数据源：${esc(rd.srcName)} 同步工单 · 报告生成：${now}</div>
  </header>

  <div class="cards">${cards}</div>

  <section>
    <h2>一、当日总体情况</h2>
    <p style="font-size:14px;margin-bottom:14px;">${rd.dateCn}，徐汇区12345热线共接入物业相关工单 <b>${total}</b> 件，
    其中已关联到所属街镇的 <b>${matched}</b> 件，待关联（地址未匹配标准街镇）<b>${unmatched}</b> 件。
    重复案件（即工单补充来电，含补充信息、催办、查进度等，每件通常指向一条不同原始工单，非同一工单的重复登记）<b>${repTotal}</b> 件，重复率 <b>${repRateTotal.toFixed(1)}%</b>。
    问题集中在 <b>住房保障·物业服务管理</b>（${pbCount('住房保障')} 件）与 <b>城管执法·物业相关执法</b>（${pbCount('城管执法')} 件）。</p>
    <div class="grid3">
      <div><h3 style="font-size:14px;margin-bottom:10px;">受理来源</h3>${srcItems}</div>
      <div><h3 style="font-size:14px;margin-bottom:10px;">热线类型</h3>${typeItems}</div>
      <div><h3 style="font-size:14px;margin-bottom:10px;">问题中类</h3>${pbItems}</div>
    </div>
  </section>

  <section>
    <h2>二、街镇分类明细</h2>
    <table>
      <thead><tr>
        <th>#</th><th class="left">街镇</th><th>工单</th><th>占比</th>
        <th class="left">主要类别</th>
        <th>重复案件</th><th>重复率</th>
      </tr></thead>
      <tbody>${tableRows}</tbody>
    </table>
    <p class="note">注："主要类别"= 当街镇内按市局12345原生最细一级(problemtyped)统计的前3个细类，格式"类别 件数"；
    "待关联街道"指工单地址未匹配到徐汇区13个标准街镇的记录，需人工补录街道归属；
    "重复案件"指市民就已有工单再次来电（补充信息、催办、查进度等，即工单补充），每件通常指向一条不同原始工单，非同一工单的重复登记；
    "重复率"= 当街镇内 is_repeat=是 工单数 ÷ 当街镇工单总量。</p>
  </section>

  <section>
    <h2>三、12345平台原生分类</h2>
    <p style="font-size:13px;margin-bottom:14px;color:var(--muted);">按市局12345原生分类最细一级（problemtyped）统计，共 ${cat.typed.length} 类 ${total} 件。</p>
    <table>
      <thead><tr><th>#</th><th class="left">最细一级分类</th><th>工单</th><th>占比</th><th>分布</th><th>涉及街镇</th></tr></thead>
      <tbody>${typedFullRows}</tbody>
    </table>
    <p class="note">注：占比 = 该细类工单数 ÷ 当日总量 ${total}；"涉及街镇"=该细类出现的已关联街镇数（不含待关联）。</p>
  </section>

  <section>
    <h2>四、重点街镇关注</h2>
    <p style="font-size:13px;margin-bottom:12px;color:var(--muted);">筛选标准：当日工单 ≥ 6 件 或 重复率 ≥ 40%。</p>
    ${focusHtml}
  </section>

  <footer>徐汇区物业投诉治理数字化分析项目 · 日报自动生成</footer>
</div>
</body>
</html>`;
  }

  // ============ 导出 ============
  const DailyReportApp = {
    PUBLIC_CONFIG: PUBLIC_CONFIG,
    STREET_ORDER: STREET_ORDER,
    WEEKDAYS: WEEKDAYS,
    WEEKDAYS_SHORT: WEEKDAYS_SHORT,
    maskPii: maskPii,
    cleanProb: cleanProb,
    assertNoPii: assertNoPii,
    pyRound: pyRound,
    pyRound0: pyRound0,
    valueCounts: valueCounts,
    parseDateSlug: parseDateSlug,
    weekdayIndexOfSlug: weekdayIndexOfSlug,
    extractForDate: extractForDate,
    buildRecordsFromWorkbook: buildRecordsFromWorkbook,
    getCloud: getCloud,
    upsertReport: upsertReport,
    fetchAllReports: fetchAllReports,
    fetchReport: fetchReport,
    deleteReport: deleteReport,
    renderReportHTML: renderReportHTML,
    bar: bar,
  };

  global.DailyReportApp = DailyReportApp;
  if (typeof module !== 'undefined' && module.exports) module.exports = DailyReportApp;
})(typeof window !== 'undefined' ? window : globalThis);
