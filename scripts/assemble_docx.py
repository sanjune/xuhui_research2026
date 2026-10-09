#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组装《徐汇区物业投诉治理数字化分析课题（一期）成果汇编》Word 文档。

用法：
  PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/assemble_docx.py

依赖：
  assets/docx_figs/manifest.json   —— 由 export_echarts_figs.py 生成
  assets/docx_figs/<报告名>/*.png  —— 图表 PNG
  词云图/*.png                     —— 13 街镇词云
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
os.chdir(ROOT)

from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt, RGBColor  # noqa: E402

from html2docx import (H1, H2, TEXT_W, _clean_text, add_body, add_bullet,  # noqa: E402
                       add_caption,
                       add_image, add_table_html, convert_report, load_figmap,
                       new_document, set_cell, shade)
import pandas as pd  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

OUT_DIR = os.path.join(ROOT, '交付物')
OUT = os.path.join(OUT_DIR,
                   '徐汇区数据赋能下的住宅小区治理与物业服务质量提升探索项目课题成果汇编.docx')
MANIFEST = json.load(open('assets/docx_figs/manifest.json', encoding='utf-8'))
FIG_USED = []


# ------------------------------------------------------------------ 通用
def chapter(doc, no, title):
    doc.add_page_break()
    doc.add_heading('第 %s 章　%s' % (no, title), level=1)


def part(doc, title):
    doc.add_page_break()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(200)
    r = p.add_run(title)
    r.font.size = Pt(24)
    r.font.bold = True
    r.font.name = '宋体'
    r.font.color.rgb = RGBColor(0x1A, 0x3A, 0x5F)
    r.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')


def conv(doc, stem, fig_prefix, base=1):
    # 优先用无头 Chrome 渲染后的完整 DOM（部分表格数据由页面 JS 运行时填充）
    rendered = os.path.join(ROOT, '_rendered', stem + '.html')
    fp = rendered if os.path.exists(rendered) else os.path.join(ROOT, stem + '.html')
    if not os.path.exists(fp):
        add_body(doc, '［报告缺失：%s］' % stem, indent=False)
        return
    figmap = load_figmap(MANIFEST, stem)
    stats = {}
    used = convert_report(doc, fp, figmap, base=base, fig_prefix=fig_prefix,
                          on_image=lambda cid: FIG_USED.append(cid), stats=stats)
    print('    %-34s 图 %-3d 表 %-4d 卡片 %-4d %s'
          % (stem, len(used), stats['tables'], stats['cards'],
             '(rendered)' if fp == rendered else ''))


def read_xls(fp, **kw):
    """按字符串读取（keep_default_na=False），避免长数字 ID 变科学计数法。"""
    return pd.read_excel(fp, dtype=str, keep_default_na=False, **kw)


def table_from_df(doc, df, max_rows=None, headers=None, widths=None):
    d = df if max_rows is None else df.head(max_rows)
    heads = headers or [str(c) for c in d.columns]
    t = doc.add_table(rows=1, cols=len(heads))
    t.style = 'Table Grid'
    n = len(heads)
    fs = 9 if n <= 8 else (8 if n <= 13 else 7)
    for i, h in enumerate(heads):
        set_cell(t.rows[0].cells[i], h, bold=True, color=(255, 255, 255), align='center', size=fs)
        shade(t.rows[0].cells[i], '1A3A5F')
    for ri, (_, row) in enumerate(d.iterrows()):
        cells = t.add_row().cells
        for i, col in enumerate(d.columns):
            v = row[col]
            v = '' if (v is None or (not isinstance(v, str) and pd.isna(v))) else v
            set_cell(cells[i], _clean_text(str(v)), align='center', size=fs)
            if ri % 2 == 1:
                shade(cells[i], 'F4F6F9')
    return t


def add_toc(doc):
    p = doc.add_paragraph()
    r = p.add_run()
    b = OxmlElement('w:fldChar'); b.set(qn('w:fldCharType'), 'begin')
    it = OxmlElement('w:instrText'); it.set(qn('xml:space'), 'preserve')
    it.text = 'TOC \\o "1-3" \\h \\z \\u'
    sp = OxmlElement('w:fldChar'); sp.set(qn('w:fldCharType'), 'separate')
    tt = OxmlElement('w:t'); tt.text = '（在 Word 中右键此区域 → 更新域，即可生成目录）'
    en = OxmlElement('w:fldChar'); en.set(qn('w:fldCharType'), 'end')
    for e in (b, it, sp, tt, en):
        r._r.append(e)


# ------------------------------------------------------------------ 卷首
TITLE_MAIN = '徐汇区数据赋能下的住宅小区治理与物业服务质量提升探索项目课题'


def add_cover(doc):
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(TITLE_MAIN); r.font.size = Pt(26); r.font.bold = True
    r.font.name = '宋体'; r.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    r.font.color.rgb = RGBColor(0x1A, 0x3A, 0x5F)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('成果汇编'); r.font.size = Pt(14)
    r.font.name = '宋体'; r.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    for _ in range(6):
        doc.add_paragraph()
    for line in ['博彦泓智科技（上海）有限公司',
                 '编制时间：2026 年 10 月']:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(line); r.font.size = Pt(12); r.font.name = '宋体'
        r.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
        r.font.color.rgb = RGBColor(0x44, 0x44, 0x44)


def add_editorial(doc):
    doc.add_page_break()
    doc.add_heading('编制说明', level=1)
    for t in [
        '本汇编是徐汇区数据赋能下的住宅小区治理与物业服务质量提升探索项目的成果全集，系统收录项目研究'
        '产出的全部分析报告、数据资产清单与图集，均属于徐汇区住房保障和房屋管理局，供项目验收、'
        '课题成果归档与后续深化研究使用。',
        '一、收录范围。汇编收录课题核心成果十七项，按「课题总览—数据基础与方法—现状与趋势—深度专项—'
        '专题分析—结论建议」六篇组织；技术过程文档（过程会议纪要、版本更新记录、词云词表审核清单）'
        '属内部编制资料，不列入对外成果。',
        '二、数据来源。基础数据为徐汇区 12345 热线物业类投诉工单，时间跨度 2024 年 1 月至 2026 年 8 月，'
        '共 66,812 件；业务数据涉及纳统小区、电梯、修缮、失信、底部抬升、征收、拆房、测绘等九类。',
        '三、统计口径。2026 年统计期统一为 1-8 月，同比一律为同期口径（2026 年 1-8 月 vs 2025 年 1-8 月）；'
        '2025 年全年同比保留（2025 年 vs 2024 年），两者标签严格区分。投诉密度统一按「件/千户」计。'
        '纳统小区口径以区房管局纳统名单为唯一基准。详细口径见附录 A。',
        '四、图表说明。正文图表由分析系统按数据实时渲染后导出，与线上成果站展示一致；'
        '图表下方标注编号（如「图 7-3」表示第 7 章第 3 图）。附录清单为全量数据摘录，'
        '完整版以随附的 Excel 附件为准。',
        '五、随附交付物。本汇编配套 4 份 Excel 全量清单附件：高风险小区评分全量清单、投诉去重建议清单、'
        '热线与纳统小区全量匹配表、纳统匹配候选与未匹配清单。',
    ]:
        add_body(doc, t)


# ------------------------------------------------------------------ 手写章节
def ch1(doc):
    chapter(doc, '1', '课题背景、目标与任务')
    add_body(doc, '物业投诉是 12345 市民服务热线中诉求量最大、涉及面最广的类别之一，直接反映住宅小区的'
                  '管理服务水平与居民生活品质。徐汇区作为中心城区，住宅小区类型多样，既有成片新建商品房小区，'
                  '也有大量建于上世纪的老旧公房与售后公房，物业管理诉求集中、成因复杂。')
    add_body(doc, '传统物业监管主要依赖个案处置与月度台账，存在「数据分散、口径不一、预警滞后、'
                  '成效难衡量」等问题：投诉数据掌握在热线系统，房屋与物业企业数据分散在多个业务部门，'
                  '缺乏小区粒度的关联底座；投诉量升降缺乏归因，无法区分治理成效与统计口径变化；'
                  '对高风险小区缺少前瞻识别手段。')
    add_body(doc, '本课题以 12345 热线物业类投诉工单为切入点，目标有三：一是打通多源数据，'
                  '建立以纳统小区为基准的小区级数据底座；二是构建从「态势监测—风险预警—根因剖析—'
                  '成效追踪」的完整分析链路；三是形成可复制的分析模型与治理建议，支撑物业监管从'
                  '被动响应向主动治理转变。')


def ch2(doc):
    chapter(doc, '2', '数据范围与统计口径')
    add_body(doc, '一、数据范围。基础数据集为徐汇区 12345 热线物业类投诉工单 66,812 件，'
                  '时间跨度 2024 年 1 月至 2026 年 8 月。其中 2024 年 29,468 件、2025 年 23,618 件、'
                  '2026 年 1-8 月 13,726 件。数据集含工单编号、受理时间、诉求内容、小区名称、街道、'
                  '物业公司、十四类问题分类等 21 个字段。')
    add_body(doc, '二、统计期口径。2026 年统计期统一为 1-8 月。同比分析一律采用同期口径，'
                  '即 2026 年 1-8 月与 2025 年 1-8 月对比；2025 年全年同比（2025 年与 2024 年对比）'
                  '作为独立标签保留，两者不得混用。')
    add_body(doc, '三、统计单元口径。全量口径按热线工单中的小区名称直接统计，覆盖 1,374 个小区，'
                  '适用于总量、趋势、街镇与类别分析。纳统口径以区房管局纳统小区名单为基准，'
                  '经名称归并后参与风险评分等分析，统计单元为纳统小区。两套口径的适用边界'
                  '在各章中分别注明，不交叉换算。')
    add_body(doc, '四、投诉密度口径。投诉密度＝投诉量 ÷ 户数 × 1000，单位「件/千户」。'
                  '户数取自小区档案，工单数据本身不含户数字段。')
    add_body(doc, '五、问题分类。按市局十四类标准分类：停车管理、房屋维修、邻里纠纷、房屋违规使用、'
                  '业主大会/业委会、消防管理、群租管理、物业安保、旧住房改造、清洁卫生、物业收费、'
                  '物业服务态度、房屋交易纠纷、其他。')


def ch16(doc):
    chapter(doc, '16', '主要结论')
    for t in [
        '一、投诉总量持续下降，但降幅收窄。2025 年全年投诉 23,618 件，较 2024 年的 29,468 件下降 19.9%；'
        '2026 年 1-8 月投诉 13,726 件，较 2025 年同期下降 13.1%，减少 2,072 件。降幅由近两成收窄至一成三，'
        '总量仍处下降通道，但改善动能减弱。',
        '二、月度走势出现转正信号。2026 年 1-7 月各月同比持续为负，8 月单月同比首次转正（+2.8%），'
        '需警惕下半年反弹风险，建议将 9-12 月列为重点监控期。',
        '三、街镇分化明显。13 个街镇中，长桥、枫林路、康健新村等降幅居前，'
        '部分街镇同比持平或上升。投诉密度方面，老城区街道显著高于全区平均水平，'
        '直管公房与老旧小区集中区域的治理压力更大。',
        '四、问题结构存在逆势上升类别。在总量下降的背景下，房屋维修类、物业服务态度类投诉'
        '同比上升，属于「总量降、结构升」的重点问题，需专项攻坚。',
        '五、高风险小区呈集中分布。以反扣分评分制对纳统小区评级，红色等级与橙色等级小区'
        '在部分街镇高度集中，呈现明显的地域聚集特征，适宜以街镇为单位整体施策。',
        '六、治理成效可量化追踪。对纳入追踪范围的小区按三年投诉走势分类，'
        '多数小区实现显著改善，同时存在持续恶化与改善后反弹两类需重点干预的情形，'
        '说明治理成效并非一劳永逸，需建立动态回访机制。',
        '七、数据质量是分析的前提。三个数据批次的字段结构与字段命名存在差异，'
        '跨年度对比前必须完成字段映射与口径统一。',
    ]:
        add_body(doc, t)


def ch17(doc):
    chapter(doc, '17', '治理建议与下一步')
    add_body(doc, '一、建立日工单红线与动态预警机制。以历史同期为基准设定单日投诉量红线，'
                  '超限自动提示，缩短从诉求产生到介入处置的响应时间。')
    add_body(doc, '二、重点压降同比上升街镇。对同比持平或上升的街镇开展专题分析，'
                  '结合街镇画像定位问题类别与热点小区，实行「一镇一策」。')
    add_body(doc, '三、高风险小区分级销号。按风险等级差异化配置监管资源，'
                  '红色等级小区列入重点督办、逐户销号，橙色等级小区纳入常态化跟踪。')
    add_body(doc, '四、底部抬升小区深化攻坚。对投诉量处于低位抬升状态的小区，'
                  '重点核查物业服务质量与设施设备状况，防止零星诉求演变为集中投诉。')
    add_body(doc, '五、逆势上升类别专项治理。针对房屋维修、物业服务态度等同比上升类别，'
                  '分别制定维修响应时限规范与服务态度考核办法。')
    add_body(doc, '六、密度治理聚焦老城区与直管公房。以「件/千户」为统一标尺跨街镇比较，'
                  '对高密度区域优先安排修缮计划与物业企业督导。')
    add_body(doc, '七、区属国资物业企业专项督导。对管理小区数量多、投诉集中度高的区属国资物业企业，'
                  '建立服务质量定期通报机制。')
    add_body(doc, '八、秋冬季季节性治理。针对 10-12 月可能出现的防冻保暖、管道维修等季节性诉求，'
                  '提前部署设施排查与应急值守。')
    add_body(doc, '九、下一步工作。持续更新数据底座，按月滚动更新分析结论；'
                  '将本课题形成的分析模型固化为常态化监测工具；结合治理实践反馈，'
                  '迭代优化风险评分权重与追踪门槛。')


# ------------------------------------------------------------------ 附录
def appx_a_b_c(doc):
    doc.add_page_break()
    doc.add_heading('附录 A　统计口径说明', level=1)
    df = pd.DataFrame([
        ['数据周期', '2024 年 1 月 — 2026 年 8 月'],
        ['工单总量', '66,812 件（2024 年 29,468 / 2025 年 23,618 / 2026 年 1-8 月 13,726）'],
        ['2026 年统计期', '统一为 1-8 月'],
        ['同比口径', '同期口径：2026 年 1-8 月 vs 2025 年 1-8 月；全年同比独立标注'],
        ['全量口径', '按热线工单小区名称统计，覆盖 1,374 个小区'],
        ['纳统口径', '以区房管局纳统小区名单为基准，统计单元为纳统小区'],
        ['投诉密度', '投诉量 ÷ 户数 × 1000，单位「件/千户」'],
        ['问题分类', '市局十四类标准分类'],
        ['重复投诉判定', '按精确重复、催办、高频、文本相似四重策略逐月独立判定'],
    ], columns=['项目', '口径说明'])
    table_from_df(doc, df, widths=[3.2, 11.2])

    doc.add_page_break()
    doc.add_heading('附录 B　关键数字速查表', level=1)
    df = pd.DataFrame([
        ['工单总量（三年）', '66,812 件'],
        ['2024 年投诉量', '29,468 件'],
        ['2025 年投诉量', '23,618 件（同比 -19.9%）'],
        ['2026 年 1-8 月投诉量', '13,726 件（同比 -13.1%，减少 2,072 件）'],
        ['2026 年 8 月单月', '同比 +2.8%（当年首次转正）'],
        ['覆盖热线小区数', '1,374 个'],
        ['纳统小区数', '993 个'],
        ['街道数', '13 个'],
        ['问题类别数', '14 类'],
        ['高风险参评小区数', '772 个'],
        ['红色等级小区数', '254 个'],
        ['治理追踪小区数', '390 个'],
        ['底部抬升小区数', '84 个（可匹配 78 个）'],
    ], columns=['指标', '数值'])
    table_from_df(doc, df, widths=[5.0, 9.4])

    doc.add_page_break()
    doc.add_heading('附录 C　十四类问题定义', level=1)
    cats = ['停车管理', '房屋维修', '邻里纠纷', '房屋违规使用', '业主大会/业委会', '消防管理',
            '群租管理', '物业安保', '旧住房改造', '清洁卫生', '物业收费', '物业服务态度',
            '房屋交易纠纷', '其他']
    df = pd.DataFrame([[i + 1, c] for i, c in enumerate(cats)], columns=['序号', '问题类别'])
    table_from_df(doc, df, widths=[1.8, 12.6])


def appx_d_e_f(doc):
    doc.add_page_break()
    doc.add_heading('附录 D　高风险小区评分清单（摘录前 100 名）', level=1)
    add_body(doc, '完整清单（全部参评小区）见随附附件 1《高风险小区评分全量清单.xlsx》。', indent=False)
    try:
        df = read_xls('高风险小区预警清单.xlsx')
        keep = [c for c in ['小区名称', '街道', '物业公司', '投诉总量', '2026年1-8月',
                            '同比增长率%', '重复投诉率%', '风险得分', '风险等级'] if c in df.columns]
        table_from_df(doc, df[keep], max_rows=100)
    except Exception as e:
        add_body(doc, '［读取失败：%s］' % e, indent=False)

    doc.add_page_break()
    doc.add_heading('附录 E　投诉去重建议清单（摘录）', level=1)
    add_body(doc, '完整清单（逐月识别明细）见随附附件 2《2026年1-8月投诉去重建议清单.xlsx》。', indent=False)
    try:
        html = open('2026年1-8月投诉去重建议清单.html', encoding='utf-8').read()
        soup = BeautifulSoup(html, 'lxml')
        for p in soup.select('[id^=panel-]'):
            label = p.get('id', '').replace('panel-m', '') + '月'
            tbs = p.find_all('table')
            if not tbs:
                continue
            doc.add_heading('%s　处置建议清单（摘录前 10 条）' % label, level=2)
            t = tbs[-1]
            rows = []
            for tr in t.find_all('tr'):
                cells = [c.get_text(' ', strip=True) for c in tr.find_all(['th', 'td'])]
                if any(cells):
                    rows.append(cells)
            if not rows:
                continue
            head = rows[0]
            nd = pd.DataFrame(rows[1:11], columns=head)
            table_from_df(doc, nd)
    except Exception as e:
        add_body(doc, '［读取失败：%s］' % e, indent=False)

    doc.add_page_break()
    doc.add_heading('附录 F　交付物与过程成果清单', level=1)
    add_body(doc, '本项目交付成果分为三类：', indent=False)
    add_body(doc, '① 本成果汇编（正文）；', indent=False)
    add_body(doc, '② 随附电子附件 4 份；', indent=False)
    add_body(doc, '③ 过程成果报告 34 份（月度 19 份、年度 15 份）。', indent=False)
    add_body(doc, '全部文件存放于交付物目录，以下逐项列出。'
                  '另有 2 份早期版本汇编作为历史版本留档于 _archive/ 子目录，不作为交付版本。',
             indent=False)
    doc.add_heading('一、随附电子附件（4 份）', level=2)
    df = pd.DataFrame([
        ['附件 1', '高风险小区评分全量清单.xlsx', '772 个参评纳统小区 × 22 项风险指标，含风险等级与得分'],
        ['附件 2', '2026年1-8月投诉去重建议清单.xlsx', '1-8 月逐月重复投诉识别明细与处置建议'],
        ['附件 3', '词云清单.xlsx', '13 个街镇诉求主题词 Top24 及补位候选词表'],
        ['附件 4', '交付物清单.xlsx', '本次交付全部文件目录（含本汇编、附件与过程成果报告）'],
    ], columns=['编号', '文件名称', '内容说明'])
    table_from_df(doc, df, widths=[1.6, 5.6, 7.4])

    doc.add_heading('二、过程成果报告（34 份）', level=2)
    rep = []
    for sub, label in [('月度分析报告', '月度分析报告'), ('年度分析报告/街道', '年度分析报告 · 街镇'),
                       ('年度分析报告/集团', '年度分析报告 · 集团')]:
        d = os.path.join(OUT_DIR, sub)
        if not os.path.isdir(d):
            rep.append('［未找到目录：%s］' % sub)
            continue
        files = sorted(f for f in os.listdir(d)
                       if f.lower().endswith(('.docx', '.doc', '.pdf')) and not f.startswith('.'))
        rep.append((label, files, d))
    for item in rep:
        if isinstance(item, str):
            add_body(doc, item, indent=False)
            continue
        label, files, d = item
        doc.add_heading('%s（%d 份）' % (label, len(files)), level=3)
        df = pd.DataFrame([[i + 1, f, '%.0f KB' % (os.path.getsize(os.path.join(d, f)) / 1024)]
                           for i, f in enumerate(files)],
                          columns=['序号', '文件名称', '文件大小'])
        table_from_df(doc, df, widths=[1.6, 10.6, 2.2])


def appx_g(doc):
    doc.add_page_break()
    doc.add_heading('附录 G　13 街镇诉求主题词云图集', level=1)
    add_body(doc, '以下词云基于各街镇 2026 年 1-8 月投诉工单诉求内容，按案件级归并后统计，'
                  '每镇展示权重最高的主题词。', indent=False)
    names = ['漕河泾', '长桥', '徐家汇', '田林', '枫林路', '斜土路', '龙华',
             '康健新村', '天平路', '湖南路', '虹梅路', '凌云路', '华泾镇']
    for i, n in enumerate(names, 1):
        fp = os.path.join(ROOT, '词云图', n + '.png')
        if os.path.exists(fp):
            doc.add_heading('%s（图 G-%d）' % (n, i), level=2)
            add_image(doc, fp, width_cm=TEXT_W)


# ------------------------------------------------------------------ 主流程
def main():
    doc = new_document()
    add_cover(doc)
    add_editorial(doc)

    doc.add_page_break()
    doc.add_heading('目　录', level=1)
    add_toc(doc)

    part(doc, '第一篇　课题总览')
    ch1(doc)
    ch2(doc)
    chapter(doc, '3', '成果体系总览')
    conv(doc, '课题成果总览', '3')

    part(doc, '第二篇　数据基础与方法')
    chapter(doc, '4', '多源数据清洗与关联分析')
    conv(doc, '多源数据清洗与关联分析报告', '4')
    chapter(doc, '5', '数据质量优化专项')
    conv(doc, '数据质量优化专项报告', '5')
    chapter(doc, '6', '投诉去重识别方法论')
    conv(doc, '投诉去重识别方法论说明', '6')

    part(doc, '第三篇　现状与趋势分析')
    chapter(doc, '7', '投诉量下降数据报告')
    conv(doc, '12345投诉量下降数据报告', '7')
    chapter(doc, '8', '街镇专项分析')
    conv(doc, '街镇专项分析报告', '8')
    chapter(doc, '9', '1-8 月工单综合分析与目标测算')
    conv(doc, '徐汇区1-8月工单综合分析与目标测算', '9')

    part(doc, '第四篇　深度专项分析')
    chapter(doc, '10', '高风险小区预警清单')
    conv(doc, '高风险小区预警清单', '10')
    chapter(doc, '11', '物业投诉根因分析')
    conv(doc, '物业投诉根因分析报告', '11')
    chapter(doc, '12', '治理效果追踪分析')
    conv(doc, '治理效果追踪分析报告', '12')
    chapter(doc, '13', '底部抬升小区热线数据专项')
    conv(doc, '底部抬升小区热线数据分析报告', '13')

    part(doc, '第五篇　专题分析')
    chapter(doc, '14', '重点问题专题分析')
    conv(doc, '重点问题专题分析报告（5份）', '14')
    chapter(doc, '15', '数据分析月报合集')
    conv(doc, '数据分析月报合集', '15')

    part(doc, '第六篇　结论与建议')
    ch16(doc)
    ch17(doc)

    part(doc, '附　录')
    appx_a_b_c(doc)
    appx_d_e_f(doc)
    appx_g(doc)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    doc.save(OUT)

    from docx import Document
    d = Document(OUT)
    paras = [p for p in d.paragraphs if p.text.strip()]
    heads = [p for p in paras if p.style.name == 'Heading 1']
    print('\n=== 汇编生成完成 ===')
    print('  段落 %d | 标题1 %d | 表格 %d | 内嵌图 %d | 文件 %.1f MB'
          % (len(paras), len(heads), len(d.tables), len(d.inline_shapes),
             os.path.getsize(OUT) / 1024 / 1024))
    print('  输出 → %s' % OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
