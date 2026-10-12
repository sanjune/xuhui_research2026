#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
徐汇区12345物业工单日报 - 每日数据上传服务

功能：
  1. 提供上传页面（GET /upload）
  2. 接收每日 excel 文件（POST /upload）
  3. 保存到 热线日报数据/ 目录
  4. 调用 gen_daily_report_1009.py 生成日报
  5. 提取摘要数据，自动更新 daily/index.html 的 REPORTS 数组
  6. 返回生成结果

用法：
  python scripts/upload_server.py [端口]
  默认端口 8766
"""
import os, sys, re, json, subprocess, html
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, '热线日报数据')
DAILY_DIR = os.path.join(ROOT, 'daily')
INDEX_HTML = os.path.join(DAILY_DIR, 'index.html')
GEN_SCRIPT = os.path.join(ROOT, 'scripts', 'gen_daily_report_1009.py')
PYTHON = '/usr/bin/python3'
VENDOR = os.path.expanduser('~/.workbuddy/binaries/python/vendor')

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
HOST = '127.0.0.1'

# ---------- 样式（与日报体系一致）----------
CSS = '''
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: #f0f4f8; color: #1a2a3a; min-height: 100vh; padding: 20px;
}
.wrap { max-width: 640px; margin: 40px auto; background: #fff;
  border-radius: 14px; box-shadow: 0 6px 24px rgba(0,0,0,.08); padding: 36px 40px; }
h1 { font-size: 22px; color: #1a3a5c; margin-bottom: 4px; }
.sub { font-size: 13px; color: #6b7c8e; margin-bottom: 24px; }
.upload-zone {
  border: 2px dashed #b8c8d8; border-radius: 10px; padding: 32px 20px;
  text-align: center; transition: all .2s; cursor: pointer; background: #fafcfe;
}
.upload-zone:hover { border-color: #4a7ab8; background: #f0f6fc; }
.upload-zone.drag { border-color: #2a6ab8; background: #e8f0fc; }
.upload-zone p { color: #6b7c8e; font-size: 14px; margin-top: 8px; }
.upload-icon { font-size: 36px; color: #b8c8d8; }
input[type=file] { display: none; }
.file-name { margin-top: 12px; font-size: 13px; color: #2a6ab8; word-break: break-all; }
.btn {
  display: inline-block; background: #2a6ab8; color: #fff; border: none;
  padding: 12px 32px; border-radius: 8px; font-size: 15px; cursor: pointer;
  margin-top: 20px; transition: background .2s;
}
.btn:hover { background: #1a5a98; }
.btn:disabled { background: #b8c8d8; cursor: not-allowed; }
.back {
  display: inline-block; font-size: 13px; color: #4a7ab8; text-decoration: none;
  margin-bottom: 16px; cursor: pointer;
}
.result {
  margin-top: 24px; padding: 18px 20px; border-radius: 10px; font-size: 14px;
}
.result.ok { background: #e8f6e8; border: 1px solid #8cc88c; color: #2a6a2a; }
.result.err { background: #fde8e8; border: 1px solid #e8a8a8; color: #8a2a2a; }
.result b { font-size: 15px; }
.stats { margin-top: 14px; display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; }
.stat { background: #f4f8fc; border-radius: 8px; padding: 12px; text-align: center; }
.stat .v { font-size: 22px; font-weight: 700; color: #1a3a5c; }
.stat .l { font-size: 11px; color: #6b7c8e; margin-top: 2px; }
.links { margin-top: 18px; display: flex; gap: 12px; flex-wrap: wrap; }
.links a {
  font-size: 13px; color: #2a6ab8; text-decoration: none; padding: 8px 16px;
  background: #eef4fc; border-radius: 6px; border: 1px solid #cce0f0;
}
.links a:hover { background: #e0ecf8; }
.spin { display: none; margin-top: 16px; color: #6b7c8e; font-size: 13px; }
.spin.show { display: block; }
.spin::after { content: ''; display: inline-block; width: 14px; height: 14px;
  border: 2px solid #b8c8d8; border-top: 2px solid #2a6ab8; border-radius: 50%;
  animation: sp .6s linear infinite; vertical-align: middle; margin-left: 6px; }
@keyframes sp { to { transform: rotate(360deg); } }
.note { margin-top: 20px; padding: 12px 14px; background: #fffbe8; border-radius: 8px;
  font-size: 12px; color: #8a6a2a; line-height: 1.6; }
'''


# ---------- 上传页面 ----------
UPLOAD_PAGE = f'''<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>每日数据上传 · 12345物业工单日报</title>
<style>{CSS}</style></head><body>
<div class="wrap">
  <a class="back" onclick="location.href='index.html'">← 返回日报日历索引</a>
  <h1>每日热线数据上传</h1>
  <div class="sub">选择当日 12345 热线工单 Excel 文件，自动生成日报并更新日历索引</div>

  <form id="upForm" enctype="multipart/form-data" method="POST" action="/upload">
    <label class="upload-zone" id="dropZone" for="fileInput">
      <div class="upload-icon">📁</div>
      <p>点击选择文件 或 拖拽 Excel 到此处</p>
      <p style="font-size:12px;color:#a8b8c8;margin-top:4px;">支持 .xlsx 格式</p>
      <div class="file-name" id="fileName"></div>
    </label>
    <input type="file" id="fileInput" name="file" accept=".xlsx,.xls" required>
    <button type="submit" class="btn" id="submitBtn" disabled>上传并生成日报</button>
  </form>

  <div class="spin" id="spin">正在处理：保存文件 → 生成日报 → 更新索引</div>
  <div id="resultBox"></div>

  <div class="note">
    <b>说明</b>：上传的 Excel <b>仅用于跑数据</b>——保存为临时文件，生成日报 + 更新索引后<b>自动删除</b>，
    不留存、不覆盖 <code>热线日报数据/</code> 里的源数据。数据不离开本机（本地 <code>127.0.0.1:{PORT}</code>）。
  </div>
</div>
<script>
const fi = document.getElementById('fileInput');
const fn = document.getElementById('fileName');
const sb = document.getElementById('submitBtn');
const dz = document.getElementById('dropZone');
fi.addEventListener('change', function() {{
  if (this.files.length) {{
    fn.textContent = '已选择：' + this.files[0].name;
    sb.disabled = false;
  }}
}});
dz.addEventListener('dragover', e => {{ e.preventDefault(); dz.classList.add('drag'); }});
dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
dz.addEventListener('drop', e => {{
  e.preventDefault(); dz.classList.remove('drag');
  if (e.dataTransfer.files.length) {{
    fi.files = e.dataTransfer.files;
    fn.textContent = '已选择：' + e.dataTransfer.files[0].name;
    sb.disabled = false;
  }}
}});
document.getElementById('upForm').addEventListener('submit', function() {{
  document.getElementById('spin').classList.add('show');
  sb.disabled = true;
}});
</script>
</body></html>'''


# ---------- 临时文件清理 ----------
def _safe_remove(path):
    """安全删除临时文件（不存在或删除失败都静默处理）"""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


# ---------- multipart 解析 ----------
def parse_multipart(body, boundary):
    """解析 multipart/form-data，返回 {fieldname: (filename, content_bytes)}"""
    fields = {}
    delim = b'--' + boundary
    parts = body.split(delim)
    for part in parts:
        part = part.strip(b'\r\n')
        if not part or part == b'--':
            continue
        # 分离 header 和 content
        header_end = part.find(b'\r\n\r\n')
        if header_end < 0:
            continue
        header = part[:header_end].decode('utf-8', 'ignore')
        content = part[header_end + 4:]
        # 解析 Content-Disposition
        name_m = re.search(r'name="([^"]+)"', header)
        file_m = re.search(r'filename="([^"]*)"', header)
        if name_m:
            name = name_m.group(1)
            filename = file_m.group(1) if file_m else None
            # 去尾部 \r\n
            if content.endswith(b'\r\n'):
                content = content[:-2]
            fields[name] = (filename, content)
    return fields


# ---------- 提取数据摘要 ----------
def extract_summary(xlsx_path):
    """读取 xlsx，提取日报摘要数据用于 REPORTS 数组"""
    import pandas as pd
    df = pd.read_excel(xlsx_path)
    total = len(df)
    # 日期
    dates = pd.to_datetime(df['processtime']).dt.date
    data_date = dates.mode().iloc[0]
    date_slug = data_date.isoformat()
    WEEKDAYS_CN = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    weekday = WEEKDAYS_CN[data_date.weekday()]
    # 街镇
    df['street'] = df['s30_str_name'].fillna('__未匹配__')
    df.loc[df['street'].isin(['无', '/']), 'street'] = '__未匹配__'
    matched = int((df['street'] != '__未匹配__').sum())
    unmatched = int((df['street'] == '__未匹配__').sum())
    streets = int(df[df['street'] != '__未匹配__']['street'].nunique())
    # 重复
    rep = int((df['is_repeat'] == '是').sum())
    rep_rate = round(rep / total * 100, 1) if total else 0
    # 主要类别 TOP3
    vc = df['problemtyped'].fillna('未分类').value_counts().head(3)
    main_cat = [f'{k} {v}' for k, v in vc.items()]
    return {
        'date': date_slug, 'weekday': weekday, 'total': total,
        'matched': matched, 'unmatched': unmatched,
        'rep': rep, 'repRate': rep_rate, 'streets': streets,
        'mainCat': main_cat, 'file': f'{date_slug}.html'
    }


# ---------- 更新日历索引 REPORTS 数组 ----------
def update_reports_array(summary):
    """更新 daily/index.html 的 REPORTS 数组（去重按日期，追加新记录）"""
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        content = f.read()
    # 匹配整个 REPORTS = [...] 数组
    pattern = r'(const\s+REPORTS\s*=\s*\[)(.*?)(\];)'
    m = re.search(pattern, content, re.S)
    if not m:
        raise RuntimeError('未找到 REPORTS 数组，daily/index.html 结构可能已变')
    prefix, body, suffix = m.group(1), m.group(2), m.group(3)
    date = summary['date']
    # 单条记录：{ date:'YYYY-MM-DD', ... }。记录内部只出现方括号（mainCat:[...]），
    # 不会嵌套花括号，故 [^{}]* 可安全匹配整条记录。
    REC = r"\{\s*date:\s*'(\d{4}-\d{2}-\d{2})'[^{}]*\}"
    # 解析现有记录：按日期归并（同日多条时后出现的覆盖先出现的，可修复历史脏数据）
    kept = {}
    for mm in re.finditer(REC, body):
        kept[mm.group(1)] = mm.group(0)
    existed = date in kept
    # 构造新记录的 JS 对象
    mc = ', '.join(f"'{x}'" for x in summary['mainCat'])
    kept[date] = (
        f"{{ date:'{date}', weekday:'{summary['weekday']}', "
        f"total:{summary['total']}, matched:{summary['matched']}, unmatched:{summary['unmatched']}, "
        f"rep:{summary['rep']}, repRate:{summary['repRate']}, streets:{summary['streets']}, "
        f"mainCat:[{mc}], file:'{summary['file']}' }}"
    )
    # ⚠️ 必须「解析后整体重建」，不要在原文上做删除/替换：
    #    旧实现（替换第一条）用 lookahead (?=\s*(?:\{|\];)) 定界，但 body 是 group(2)、
    #    **不含 '];'** → 数组最后一条永远匹配不上 → 走兜底追加 → 反复上传同一天就多一条重复卡片。
    #    中间版本改成「先删记录再追加」，又把被删记录**后面的分隔逗号**留了下来
    #    （`[\n  ,\n  {...}` → 数组空洞 → [...REPORTS] 出现 undefined → renderList 抛 TypeError、
    #     列表视图整块崩掉）。整体重建两个坑都不会有。
    body_new = '\n  ' + ',\n  '.join(kept[d] for d in sorted(kept)) + '\n'
    # 自检：同一天恰好一条，且记录总数与解析结果一致，否则宁可报错也不写出坏索引
    if len(re.findall(REC, body_new)) != len(kept) or body_new.count("date:'" + date + "'") != 1:
        raise RuntimeError(f'REPORTS 去重自检失败：{date} 记录数异常')
    if re.search(r'\[\s*,|,\s*,', body_new):
        raise RuntimeError('REPORTS 自检失败：存在游离逗号（会产生数组空洞）')
    # 写回
    new_array = prefix + body_new + suffix
    new_content = content[:m.start()] + new_array + content[m.end():]
    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(new_content)
    return existed


# ---------- 生成结果页面 ----------
def build_result_page(ok, summary, log, error_msg=''):
    if not ok:
        return f'''<div class="result err">
  <b>❌ 生成失败</b>
  <div style="margin-top:10px;font-size:13px;white-space:pre-wrap;">{html.escape(error_msg)}</div>
  <div style="margin-top:10px;font-size:12px;color:#8a5a5a;">脚本日志（末尾）：<br>{html.escape(log[-800:])}</div>
</div>'''

    s = summary
    return f'''<div class="result ok">
  <b>✅ 日报已生成：{s['date']}（{s['weekday']}）</b>
  <div class="stats">
    <div class="stat"><div class="v">{s['total']}</div><div class="l">工单总量</div></div>
    <div class="stat"><div class="v">{s['rep']}</div><div class="l">重复案件</div></div>
    <div class="stat"><div class="v">{s['repRate']}%</div><div class="l">重复率</div></div>
  </div>
  <div style="margin-top:12px;font-size:13px;color:#4a5a6a;">
    已关联街镇 <b>{s['matched']}</b> 件（{s['streets']} 个街镇）· 待关联 <b>{s['unmatched']}</b> 件<br>
    主要类别：{ '、'.join(s['mainCat']) }
  </div>
  <div class="links">
    <a onclick="location.href='index.html'">查看日历索引</a>
    <a onclick="location.href='{s['file']}'">查看当日日报</a>
    <a onclick="location.href='/upload'">继续上传</a>
  </div>
</div>'''


# ---------- HTTP Handler ----------
class UploadHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # 注意：不使用 fmt % args（fmt 可能含 % 字符如重复率，会触发 TypeError）
        msg = fmt % args if args else fmt
        sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

    def _send(self, code, body, ctype='text/html; charset=utf-8'):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/upload'):
            self._send(200, UPLOAD_PAGE)
        elif path == '/index.html':
            # 重定向到日历索引（方便从上传页返回）
            with open(INDEX_HTML, 'rb') as f:
                self._send(200, f.read())
        else:
            self._send(404, '<h1>404 Not Found</h1>')

    def do_POST(self):
        path = urlparse(self.path).path
        if path != '/upload':
            self._send(404, '<h1>404 Not Found</h1>')
            return
        # 读取 body
        clen = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(clen) if clen else b''
        ctype = self.headers.get('Content-Type', '')
        # 解析 boundary
        bmatch = re.search(r'boundary=(.+)', ctype)
        if not bmatch:
            self._send(400, '错误的 Content-Type')
            return
        boundary = bmatch.group(1).strip().encode('utf-8')
        fields = parse_multipart(body, boundary)
        if 'file' not in fields:
            self._send(400, '未收到文件')
            return
        filename, content = fields['file']
        if not filename:
            self._send(400, '文件名为空')
            return
        # 校验扩展名
        if not filename.lower().endswith(('.xlsx', '.xls')):
            self._send(400, '仅支持 .xlsx / .xls 格式')
            return
        # 保存为临时文件（不覆盖 热线日报数据/ 里的源数据，跑完自动删除）
        os.makedirs(DATA_DIR, exist_ok=True)
        _ts = datetime.now().strftime('%Y%m%d%H%M%S')
        _safe_ext = '.xlsx' if filename.lower().endswith('.xlsx') else '.xls'
        save_path = os.path.join(DATA_DIR, f'_upload_tmp_{_ts}{_safe_ext}')
        with open(save_path, 'wb') as f:
            f.write(content)
        self.log_message(f"已保存临时文件: {save_path} ({len(content)} bytes) — 跑完将自动删除")

        # 调用 gen_daily_report_1009.py 生成日报
        env = os.environ.copy()
        env['PYTHONPATH'] = VENDOR
        try:
            proc = subprocess.run(
                [PYTHON, GEN_SCRIPT, save_path],
                capture_output=True, text=True, cwd=ROOT, env=env, timeout=120
            )
            log = proc.stdout + '\n' + proc.stderr
            if proc.returncode != 0:
                _safe_remove(save_path)
                page = UPLOAD_PAGE.replace(
                    '<div id="resultBox"></div>',
                    build_result_page(False, None, log, '日报脚本执行失败（返回码 %d）' % proc.returncode)
                )
                self._send(200, page)
                return
        except subprocess.TimeoutExpired:
            _safe_remove(save_path)
            page = UPLOAD_PAGE.replace(
                '<div id="resultBox"></div>',
                build_result_page(False, None, '', '脚本执行超时（120s）')
            )
            self._send(200, page)
            return
        except Exception as e:
            _safe_remove(save_path)
            page = UPLOAD_PAGE.replace(
                '<div id="resultBox"></div>',
                build_result_page(False, None, '', str(e))
            )
            self._send(200, page)
            return

        # 提取摘要并更新索引
        try:
            summary = extract_summary(save_path)
            updated_existing = update_reports_array(summary)
            # 同步 _publish/daily/
            pub_daily = os.path.join(ROOT, '_publish', 'daily')
            if os.path.isdir(pub_daily):
                import shutil
                src_daily_html = os.path.join(DAILY_DIR, summary['file'])
                if os.path.exists(src_daily_html):
                    shutil.copy2(src_daily_html, os.path.join(pub_daily, summary['file']))
                if os.path.exists(INDEX_HTML):
                    shutil.copy2(INDEX_HTML, os.path.join(pub_daily, 'index.html'))
            self.log_message(
                f"日报已生成: {summary['date']} | 工单{summary['total']} | "
                f"重复{summary['rep']}({summary['repRate']}%) | 索引已更新"
                + ('(替换已有记录)' if updated_existing else '(新增记录)')
            )
            page = UPLOAD_PAGE.replace(
                '<div id="resultBox"></div>',
                build_result_page(True, summary, log)
            )
            self._send(200, page)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            page = UPLOAD_PAGE.replace(
                '<div id="resultBox"></div>',
                build_result_page(False, None, log + '\n' + tb, '摘要提取/索引更新失败: ' + str(e))
            )
            self._send(200, page)
        finally:
            # 无论成功失败，都删除临时 xlsx 文件（仅用于跑数据，跑完即清理）
            _safe_remove(save_path)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DAILY_DIR, exist_ok=True)
    server = HTTPServer((HOST, PORT), UploadHandler)
    print(f"=" * 56)
    print(f"  12345 物业工单日报 · 每日数据上传服务")
    print(f"  访问地址: http://{HOST}:{PORT}/upload")
    print(f"  数据目录: {DATA_DIR}")
    print(f"  日报脚本: {GEN_SCRIPT}")
    print(f"  按 Ctrl+C 停止服务")
    print(f"=" * 56)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.server_close()


if __name__ == '__main__':
    main()
