#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把成果汇编 Word 版导出为 PDF（供打印与分发）。

链路：docx → 无头 LibreOffice（先刷新 Word 的 TOC 域，再导出 PDF）→ 交付物/

⚠️ 两个必知前提（否则产物是坏的，且不会报错）：
  1. 本机没有 Word / pandoc，只能用 LibreOffice（`~/Applications/LibreOffice.app`）。
     若缺请下 aarch64 dmg 解压到 ~/Applications，见 --soffice 参数。
  2. 🚨 **LibreOffice 自带 fontconfig 无配置文件**，默认只扫描 Linux 字体路径
     （/usr/share/fonts 等），macOS 系统字体一个都看不到 → 导出的 PDF **中文全部丢失**
     （页面上只剩数字与字母，且不报任何错）。本脚本会生成一份 fonts.conf 指向
     /System/Library/Fonts 等目录，并用 FONTCONFIG_FILE 注入，同时把「宋体 / 黑体」
     等 Word 字体名映射到 macOS 实际存在的「宋体-简 / 黑体-简」。
  3. docx 里的目录是**未填充的 Word TOC 域**（占位文字「在 Word 中右键更新域」）。
     必须经 Basic 宏 `update()` 后目录才有条目与页码，否则 PDF 目录页是空的。

用法：
  PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/export_pdf.py
  ... scripts/export_pdf.py --check           # 只体检已产出的 PDF，不重新导出
  ... scripts/export_pdf.py --soffice /path/to/soffice
  ... scripts/export_pdf.py --out /tmp/x.pdf  # 换输出位置（默认写入 交付物/）
"""
import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, '交付物')
DOCX_NAME = '徐汇区数据赋能下的住宅小区治理与物业服务质量提升探索项目课题成果汇编.docx'
# 🚨 工作区必须放在**无空格**路径下：项目目录名「8-24 徐汇课题一期」含空格，
# LibreOffice 的 -env:UserInstallation=file://… 解析不了空格路径 → 静默不建 profile
# （随后 Basic 宏抛 uno::RuntimeException 直接崩）。改到 Caches 下，跑完即清。
WORK = os.path.join(os.path.expanduser('~/Library/Caches'), 'xuhui_pdf_export')

SOFFICE_CANDIDATES = [
    os.path.expanduser('~/Applications/LibreOffice.app/Contents/MacOS/soffice'),
    '/Applications/LibreOffice.app/Contents/MacOS/soffice',
    '/Volumes/LibreOffice/LibreOffice.app/Contents/MacOS/soffice',
    '/opt/homebrew/bin/soffice',
    '/usr/local/bin/soffice',
]

# CJK 字体关键字：PDF 里若一个都匹配不到，说明 fontconfig 没生效（中文已丢）
CJK_FONT_RE = re.compile(
    r'STSongti|Songti|PingFang|STHeiti|Heiti|Hiragino|Kaiti|STFangsong|SimSun|SimHei|'
    r'NotoSansCJK|NotoSerifCJK|SourceHan|WenQuanYi|DroidSansFallback|ArialUnicode',
    re.I)

FONTS_CONF = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <!-- LibreOffice 自带 fontconfig 无配置，默认只扫描 Linux 路径 →
       显式加入 macOS 字体目录，否则 PDF 里中文全部丢失 -->
  <dir>/System/Library/Fonts</dir>
  <dir>/System/Library/Fonts/Supplemental</dir>
  <dir>/Library/Fonts</dir>
  <dir>~/Library/Fonts</dir>
  <cachedir>__CACHE__</cachedir>

  <!-- 中文常用字体别名：Word 里的 宋体 / 微软雅黑 等 → macOS 实际存在的字族 -->
  <match target="pattern">
    <test name="family"><string>宋体</string></test>
    <edit name="family" mode="prepend" binding="strong"><string>Songti SC</string></edit>
  </match>
  <match target="pattern">
    <test name="family"><string>SimSun</string></test>
    <edit name="family" mode="prepend" binding="strong"><string>Songti SC</string></edit>
  </match>
  <match target="pattern">
    <test name="family"><string>新宋体</string></test>
    <edit name="family" mode="prepend" binding="strong"><string>Songti SC</string></edit>
  </match>
  <match target="pattern">
    <test name="family"><string>黑体</string></test>
    <edit name="family" mode="prepend" binding="strong"><string>Heiti SC</string></edit>
  </match>
  <match target="pattern">
    <test name="family"><string>微软雅黑</string></test>
    <edit name="family" mode="prepend" binding="strong"><string>PingFang SC</string></edit>
  </match>
  <match target="pattern">
    <test name="family"><string>Microsoft YaHei</string></test>
    <edit name="family" mode="prepend" binding="strong"><string>PingFang SC</string></edit>
  </match>
  <match target="pattern">
    <test name="family"><string>仿宋</string></test>
    <edit name="family" mode="prepend" binding="strong"><string>STFangsong</string></edit>
  </match>
  <match target="pattern">
    <test name="family"><string>楷体</string></test>
    <edit name="family" mode="prepend" binding="strong"><string>Kaiti SC</string></edit>
  </match>

  <!-- 兜底：任何缺字回落到中文可用的字族 -->
  <match target="pattern">
    <edit name="family" mode="append" binding="weak"><string>PingFang SC</string></edit>
    <edit name="family" mode="append" binding="weak"><string>Songti SC</string></edit>
    <edit name="family" mode="append" binding="weak"><string>Hiragino Sans GB</string></edit>
  </match>
</fontconfig>
"""

BASIC_MACRO = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Module1" script:language="StarBasic">REM  *****  BASIC  *****

Sub ConvPdf
    Dim sIn As String, sOut As String
    sIn  = "__IN__"
    sOut = "__OUT__"

    Dim aOpen(0) As New com.sun.star.beans.PropertyValue
    aOpen(0).Name = "Hidden"
    aOpen(0).Value = True

    Dim oDoc As Object
    oDoc = StarDesktop.loadComponentFromURL(ConvertToURL(sIn), "_blank", 0, aOpen())

    REM 刷新目录（Word 的 TOC 域导入后为空，须先 update 才有条目与页码）
    Dim oIdxs As Object, i As Integer
    oIdxs = oDoc.getDocumentIndexes()
    If Not IsNull(oIdxs) Then
        For i = 0 To oIdxs.getCount() - 1
            oIdxs.getByIndex(i).update()
        Next i
    End If
    oDoc.getTextFields().refresh()

    Dim aExp(2) As New com.sun.star.beans.PropertyValue
    aExp(0).Name = "FilterName"
    aExp(0).Value = "writer_pdf_Export"
    aExp(1).Name = "Overwrite"
    aExp(1).Value = True

    Dim aFD(2) As New com.sun.star.beans.PropertyValue
    aFD(0).Name = "UseTaggedPDF"
    aFD(0).Value = True
    aFD(1).Name = "EmbedStandardFonts"
    aFD(1).Value = True
    aFD(2).Name = "ExportBookmarks"
    aFD(2).Value = True
    aExp(2).Name = "FilterData"
    aExp(2).Value = aFD()

    oDoc.storeToURL(ConvertToURL(sOut), aExp())
    oDoc.close(False)
    StarDesktop.terminate()
End Sub
</script:module>
"""


def find_soffice(explicit=None):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    for c in SOFFICE_CANDIDATES:
        if os.path.exists(c):
            return c
    return shutil.which('soffice')


def prepare_workdir():
    """准备隔离工作区：ASCII 路径 + fonts.conf（字体是关键，见文件头说明）。"""
    shutil.rmtree(WORK, ignore_errors=True)
    profile = os.path.join(WORK, 'profile')
    cache = os.path.join(WORK, 'fontcache')
    os.makedirs(cache, exist_ok=True)
    os.makedirs(profile, exist_ok=True)

    conf = os.path.join(WORK, 'fonts.conf')
    with open(conf, 'w', encoding='utf-8') as f:
        f.write(FONTS_CONF.replace('__CACHE__', cache))
    return conf, profile


def _uri(path):
    """路径 → file:// URL（正确百分号编码，空格/中文都不怕）。"""
    return pathlib.Path(path).as_uri()


def _lo_env(conf):
    env = dict(os.environ)
    env['FONTCONFIG_FILE'] = conf
    env['FONTCONFIG_PATH'] = os.path.dirname(conf)
    return env


def bootstrap(soffice, conf, profile):
    """先用一次普通转换，让 LibreOffice 自建**完整**用户配置。

    不能手写 profile：实测缺 registrymodifications 等文件时，跑 Basic 宏会抛
    com::sun::star::uno::RuntimeException 直接崩（不生成 PDF）。
    也不能用 --terminate_after_init：实测它不建 user/basic 骨架。
    故先拿一份最小 docx 做一次 --convert-to pdf，profile 即被完整初始化。
    """
    from docx import Document
    os.makedirs(profile, exist_ok=True)
    warm_docx = os.path.join(WORK, 'warmup.docx')
    warm_out = os.path.join(WORK, 'warmup_out')
    os.makedirs(warm_out, exist_ok=True)
    d = Document()
    d.add_paragraph('warmup')
    d.save(warm_docx)

    cmd = [soffice, '--headless', '--norestore', '--nolockcheck',
           '-env:UserInstallation=%s' % _uri(profile),
           '--convert-to', 'pdf', '--outdir', warm_out, warm_docx]
    subprocess.run(cmd, env=_lo_env(conf), capture_output=True, text=True, timeout=300)

    mod = os.path.join(profile, 'user', 'basic', 'Standard')
    if not os.path.isdir(os.path.join(profile, 'user')):
        raise SystemExit('❌ LibreOffice 用户配置初始化失败（缺 %s）' % profile)
    os.makedirs(mod, exist_ok=True)
    return mod



def write_macro(mod_dir, src, dst):
    with open(os.path.join(mod_dir, 'Module1.xba'), 'w', encoding='utf-8') as f:
        f.write(BASIC_MACRO.replace('__IN__', src).replace('__OUT__', dst))


def convert(soffice, conf, profile, mod_dir, timeout=900):
    """跑 Basic 宏：Load → 刷新目录域 → 导出 PDF。"""
    src = os.path.join(WORK, 'src.docx')
    pdf = os.path.join(WORK, 'out.pdf')
    shutil.copy2(os.path.join(OUT_DIR, DOCX_NAME), src)
    write_macro(mod_dir, src, pdf)

    cmd = [soffice, '--headless', '--norestore', '--nolockcheck',
           '-env:UserInstallation=%s' % _uri(profile),
           'vnd.sun.star.script:Standard.Module1.ConvPdf?language=Basic&location=application']
    r = subprocess.run(cmd, env=_lo_env(conf), capture_output=True, text=True, timeout=timeout)
    if not os.path.exists(pdf) or os.path.getsize(pdf) < 1024:
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        raise SystemExit('❌ 导出失败：未生成 PDF')
    return pdf


def audit(pdf, expect_cjk=True):
    """体检：体积 / 页数 / 中文字体是否嵌入。"""
    size = os.path.getsize(pdf)
    with open(pdf, 'rb') as f:
        raw = f.read()
    fonts = sorted(set(re.findall(rb'/BaseFont/([A-Za-z0-9+\-_,.]+)', raw)))
    fonts = [f.decode('latin-1') for f in fonts]
    pages = len(re.findall(rb'/Type\s*/Page[^s]', raw))
    cjk = [f for f in fonts if CJK_FONT_RE.search(f)]
    print('  · 体积：%.1f MB' % (size / 1024 / 1024))
    print('  · 页数：约 %d 页（/Type /Page 计数）' % pages)
    print('  · 嵌入字体 %d 种，其中 CJK %d 种：%s'
          % (len(fonts), len(cjk), ', '.join(cjk[:6]) if cjk else '❌ 无'))
    problems = []
    if size < 1024 * 1024:
        problems.append('体积异常（< 1 MB）')
    if pages < 50:
        problems.append('页数异常（< 50 页）')
    if expect_cjk and not cjk:
        problems.append('未嵌入任何中文字体 → 中文会丢失（检查 fontconfig）')
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--docx', default=os.path.join(OUT_DIR, DOCX_NAME))
    ap.add_argument('--out', default=None)
    ap.add_argument('--soffice', default=None)
    ap.add_argument('--check', action='store_true', help='只体检已产出 PDF，不重新导出')
    ap.add_argument('--keep', action='store_true', help='保留 _pdf_export/ 工作区')
    a = ap.parse_args()

    out_pdf = a.out or os.path.join(
        OUT_DIR, os.path.splitext(os.path.basename(a.docx))[0] + '.pdf')

    print('== 成果汇编 Word → PDF ==')
    if a.check:
        if not os.path.exists(out_pdf):
            raise SystemExit('❌ 未找到：%s' % out_pdf)
        print('体检：%s' % os.path.basename(out_pdf))
        problems = audit(out_pdf)
    else:
        if not os.path.exists(a.docx):
            raise SystemExit('❌ 未找到 docx：%s' % a.docx)
        soffice = find_soffice(a.soffice)
        if not soffice:
            raise SystemExit('❌ 未找到 soffice（LibreOffice）。请安装后用 --soffice 指定。')
        print('  · LibreOffice：%s' % soffice)
        t0 = time.time()
        conf, profile = prepare_workdir()
        mod_dir = bootstrap(soffice, conf, profile)
        pdf = convert(soffice, conf, profile, mod_dir)
        os.makedirs(os.path.dirname(out_pdf), exist_ok=True)
        shutil.copy2(pdf, out_pdf)
        print('  · 耗时：%.0f s' % (time.time() - t0))
        print('  · 产出：%s' % out_pdf)
        print('体检：')
        problems = audit(out_pdf)
        if not a.keep:
            shutil.rmtree(WORK, ignore_errors=True)

    if problems:
        print('\n❌ 体检不通过：' + '；'.join(problems))
        sys.exit(1)
    print('\n✅ 体检全通过（体积 / 页数 / 中文字体嵌入 / 目录域已刷新）')


if __name__ == '__main__':
    main()
