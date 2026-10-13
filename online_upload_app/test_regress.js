/**
 * test_regress.js — 阶段2回归测试
 * 用 JS（app.js）解析 热线日报数据/*.xlsx，与 Python 种子脚本产出的 seed_*.json
 * （已入库的 12 条）逐字段 diff。除 generatedAt（时间戳）外必须完全一致。
 */
const fs = require('fs');
const path = require('path');

global.XLSX = require('xlsx');
const app = require('/Users/macbookpro/Desktop/8-24 徐汇课题一期/online_upload_app/app.js');

const XLSX_DIR = '/Users/macbookpro/Desktop/8-24 徐汇课题一期/热线日报数据';
const SEED_DIR = '/Users/macbookpro/Desktop/8-24 徐汇课题一期/online_upload_app/data';

const xlsxFiles = fs.readdirSync(XLSX_DIR).filter(f => f.endsWith('.xlsx') && !f.startsWith('_') && !f.startsWith('~'));

// 收集 JS 产物
const jsRecords = {}; // date -> record
let skippedTotal = 0;
for (const f of xlsxFiles) {
  const buf = fs.readFileSync(path.join(XLSX_DIR, f));
  const { records, skipped } = app.buildRecordsFromWorkbook(buf, f);
  skippedTotal += skipped;
  for (const r of records) jsRecords[r.report_date] = r;
}

// 载入种子
const seedFiles = fs.readdirSync(SEED_DIR).filter(f => /^seed_\d{4}-\d{2}-\d{2}\.json$/.test(f));
const seedRecords = {};
for (const f of seedFiles) {
  const d = JSON.parse(fs.readFileSync(path.join(SEED_DIR, f), 'utf8'));
  seedRecords[d.report_date] = d;
}

let pass = 0, fail = 0;
const failMsgs = [];

function deepDiff(a, b, pathStr, diffs) {
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) { diffs.push(`${pathStr}: 数组长度 ${a.length} vs ${b.length}`); return; }
    for (let i = 0; i < a.length; i++) deepDiff(a[i], b[i], `${pathStr}[${i}]`, diffs);
  } else if (a && b && typeof a === 'object' && typeof b === 'object') {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const k of keys) {
      if (!(k in a)) { diffs.push(`${pathStr}.${k}: JS 缺失`); continue; }
      if (!(k in b)) { diffs.push(`${pathStr}.${k}: JS 多余`); continue; }
      deepDiff(a[k], b[k], `${pathStr}.${k}`, diffs);
    }
  } else {
    if (a !== b) diffs.push(`${pathStr}: JS=${JSON.stringify(a)} vs 种子=${JSON.stringify(b)}`);
  }
}

const dates = Object.keys(seedRecords).sort();
for (const date of dates) {
  const seed = seedRecords[date];
  const js = jsRecords[date];
  if (!js) { fail++; failMsgs.push(`${date}: JS 未产出该日期`); continue; }
  const diffs = [];
  // summary 字段
  for (const k of ['report_date', 'weekday', 'total', 'matched', 'unmatched', 'rep', 'rep_rate', 'streets']) {
    if (js[k] !== seed[k]) diffs.push(`summary.${k}: JS=${JSON.stringify(js[k])} vs 种子=${JSON.stringify(seed[k])}`);
  }
  // main_cat 逐项
  deepDiff(js.main_cat, seed.main_cat, 'main_cat', diffs);
  // report_data（排除 generatedAt）
  const jsRd = { ...js.report_data }; delete jsRd.generatedAt;
  const seedRd = { ...seed.report_data }; delete seedRd.generatedAt;
  deepDiff(jsRd, seedRd, 'report_data', diffs);

  if (diffs.length === 0) { pass++; console.log(`✅ ${date} 一致（total=${seed.total} rep=${seed.rep}）`); }
  else { fail++; failMsgs.push(`${date}: ${diffs.length} 处差异`); diffs.slice(0, 10).forEach(d => failMsgs.push(`   ${d}`)); if (diffs.length > 10) failMsgs.push(`   ...共 ${diffs.length} 处`); }
}

// JS 多产出的日期
for (const date of Object.keys(jsRecords).sort()) {
  if (!seedRecords[date]) { failMsgs.push(`⚠️ ${date}: JS 产出但种子无（应检查日期分组）`); }
}

console.log(`\n========== 回归结果 ==========`);
console.log(`xlsx 文件数: ${xlsxFiles.length}，解析跳过行(无日期): ${skippedTotal}`);
console.log(`通过: ${pass} / ${pass + fail}`);
if (fail) {
  console.log('\n❌ 差异明细:');
  failMsgs.forEach(m => console.log(m));
  process.exit(1);
} else {
  console.log('🎉 全部一致 — JS 移植与 Python 种子逐字段相同');
}
