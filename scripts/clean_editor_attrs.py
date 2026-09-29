#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清除外部可视化编辑器回写进 HTML 的注入属性（幂等）。

■ 背景
外部编辑器（可视化 HTML 编辑器）打开并保存报告时，会把**渲染后 DOM 回写**进源文件，
给几乎每一个元素注入 `data-page-node-id="<21~22 位 nanoid>"`（少量还有 `data-dm-ref`）。
这些属性：

  1. 无任何运行时用途（纯编辑器内部节点映射）；
  2. 体积可观 —— 全站 4,508 处，约占数百 KB；
  3. **是「正则吞标签」事故的直接诱因**：`update_risk_report.py` 曾用 `\\S+?` 做前缀匹配，
     `\\S` 会匹配 `<` `>` `"` `=`，于是 `data-page-node-id="…">` 连同标签一起被吞进匹配范围、
     替换后又不补回 → `<p` 丢掉 `>`，**整句话在页面上完全不显示**（已修正则，但属性仍在）。

所以本脚本的定位是：**拆掉隐患引信**，而不是修复破损（清洗前实测：闭合标签带属性 0 处、
标签内混入正文 0 处，即当前无破损）。

■ 行为边界（刻意做窄）
- 只删除 `DROP_ATTRS` 列出的属性；**不改正文、不改样式、不改脚本、不减元素**；
- 属性删除只在**标签内部**进行（`<tag …>` 扫描），标签外的正文即便出现同名字符串也不动
  —— 例如《版本更新记录》用 `<code>&lt;p … data-page-node-id="…"&gt;</code>` 转义引用的
  事故示例文字，属正文，**必须保留**；
- 白名单 `TARGETS` 只含 4 份被编辑器回写过的报告，其它文件一概不碰。

■ 用法
    PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/clean_editor_attrs.py
    ... --dry-run      # 只报告不写盘
    ... --no-backup    # 跳过备份（默认备份到 _archive/）

■ 幂等性
连跑第二次应报告「0 处改动」。脚本自带四项自检（正文一致性 / 标签多重集一致 /
标签计数一致 / 残留为 0），任一不通过则不写盘。
"""
import os
import re
import sys
import shutil
import hashlib
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 只处理被编辑器回写过的这 4 份（《版本更新记录》只在正文里提到该属性名，不在名单内）
TARGETS = [
    "物业投诉根因分析报告.html",
    "高风险小区预警清单.html",
    "数据质量优化专项报告.html",
    "课题成果总览.html",
]

# 需要清除的编辑器注入属性（真实存在的只有这两个；新增需先实测确认非本项目自用）
DROP_ATTRS = ["data-page-node-id", "data-dm-ref"]

# 本项目脚本自用、**不可删**的 data-* 属性（写在这里是为了自检时留痕）
KEEP_ATTRS = ["data-target", "data-level", "data-bl-street", "data-risk-drawer"]

BACKUP_DIR = os.path.join(ROOT, "_archive")

TAG_RE = re.compile(r"<[a-zA-Z][^<>]*>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[\s\S]*?</\1>", re.I)
TAGNAME_RE = re.compile(r"</?([a-zA-Z][\w-]*)")


def attr_re(attr: str) -> re.Pattern:
    """匹配标签内的 ` name="…"` / ` name='…'` / ` name=value`（含前导空白）。"""
    return re.compile(
        r"\s+" + re.escape(attr) + r"""\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""",
        re.I,
    )


def clean_text(s: str):
    """返回 (清洗后文本, 各属性命中数)。"""
    hits = {a: 0 for a in DROP_ATTRS}
    res = [attr_re(a) for a in DROP_ATTRS]

    def _one_tag(tag: str) -> str:
        for a, r in zip(DROP_ATTRS, res):
            tag, n = r.subn("", tag)
            hits[a] += n
        return tag

    # 注意：re.sub 传函数时收到的是 Match 对象，必须取 group(0) 才是标签原文
    return TAG_RE.sub(lambda m: _one_tag(m.group(0)), s), hits


def visible_text(s: str) -> str:
    """粗略提取"正文"：去 script/style、去注释、去标签、压空白。用于前后一致性比对。"""
    s = SCRIPT_STYLE_RE.sub(" ", s)
    s = re.sub(r"<!--[\s\S]*?-->", " ", s)
    s = re.sub(r"<[^>]*>", " ", s)
    s = re.sub(r"&nbsp;", " ", s)
    return re.sub(r"\s+", "", s)


def main() -> int:
    dry = "--dry-run" in sys.argv
    backup = "--no-backup" not in sys.argv

    print("清洗编辑器注入属性" + ("（dry-run，不写盘）" if dry else ""))
    print("待删属性：" + " · ".join(DROP_ATTRS))
    print("保留属性（本项目自用）：" + " · ".join(KEEP_ATTRS))
    print("=" * 78)

    total_hits = 0
    total_saved = 0
    changed = 0
    failures = []

    for name in TARGETS:
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            print(f"  ⚠️ 跳过（不存在）：{name}")
            failures.append(f"{name}: 文件不存在")
            continue

        with open(path, encoding="utf-8") as f:
            raw = f.read()

        new, hits = clean_text(raw)
        n = sum(hits.values())
        total_hits += n

        # ---- 四项自检 ----
        checks = []
        checks.append(("正文一致", visible_text(raw) == visible_text(new)))
        checks.append(("标签多重集一致",
                       (lambda a, b: sorted(a) == sorted(b))(
                           TAGNAME_RE.findall(SCRIPT_STYLE_RE.sub(" ", raw)),
                           TAGNAME_RE.findall(SCRIPT_STYLE_RE.sub(" ", new)))))
        checks.append(("标签计数一致",
                       len(TAG_RE.findall(raw)) == len(TAG_RE.findall(new))))
        left = sum(len(attr_re(a).findall(new)) for a in DROP_ATTRS)
        checks.append(("残留为 0", left == 0))

        ok = all(v for _, v in checks)
        tag = "✅" if ok else "❌"
        detail = " ".join(f"{k}{'✓' if v else '✗'}" for k, v in checks)
        delta = len(raw.encode()) - len(new.encode())
        total_saved += delta

        print(f"{tag} {name}")
        print(f"     命中 {n} 处（" +
              " · ".join(f"{a} {c}" for a, c in hits.items() if c) + "）" +
              f"｜体积 {delta:+d} 字节  ({len(raw.encode())/1024:.0f}KB → {len(new.encode())/1024:.0f}KB)")
        print(f"     自检：{detail}")

        if not ok:
            failures.append(f"{name}: 自检未通过（{detail}）")
            continue
        if n == 0:
            print("     ↳ 已干净，无需改动")
            continue

        changed += 1
        if dry:
            continue

        if backup:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            bak = os.path.join(
                BACKUP_DIR,
                f"{os.path.splitext(name)[0]}.注入属性备份_"
                f"{datetime.datetime.now():%Y%m%d_%H%M}.html",
            )
            if not os.path.exists(bak):
                shutil.copy2(path, bak)
            print(f"     备份 → _archive/{os.path.basename(bak)}")

        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
        print(f"     已写回（md5 {hashlib.md5(new.encode()).hexdigest()[:10]}）")

    print("=" * 78)
    print(f"合计命中 {total_hits} 处 · 改动 {changed} 个文件 · 瘦身 {total_saved/1024:.0f} KB")
    if failures:
        print("❌ 存在未通过项：")
        for x in failures:
            print("   · " + x)
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
