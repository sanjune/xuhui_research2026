#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 _publish/ 成果站同步发布到 GitHub Pages 的 gh-pages 分支。

为什么要单独一个分支：
    仓库根目录含大量 docx/xlsx 报告、脚本与数据文件。若 Pages 直接发布
    main 根目录，等于把整个 197 个文件对外开成静态站点（含原始工单下载件）。
    gh-pages 分支只放 _publish/ 的产物，站点暴露面收敛到成果站本身。

用法：
    PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 scripts/publish_gh_pages.py
        # 先跑 build_publish_site.py 组装，再同步发布
    ... scripts/publish_gh_pages.py --no-build      # 跳过组装，直接发布现有 _publish/
    ... scripts/publish_gh_pages.py --dry-run       # 只做检查与差异预览，不提交不推送
    ... scripts/publish_gh_pages.py --set-source    # 额外尝试用 API 把 Pages 发布源切到 gh-pages

退出码：0 = 成功（含“无变化”）；1 = 断言失败或发布失败。
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(ROOT, "_publish")
BRANCH = "gh-pages"
REMOTE = "origin"
PAGES_URL = "https://sanjune.github.io/xuhui_research2026/"

# 绝不允许出现在发布分支里的类型（兜底断言，防止 _publish 被污染）
FORBIDDEN_EXT = (".pkl", ".xlsx", ".xls", ".docx", ".doc", ".py", ".db",
                 ".log", ".bak", ".off", ".env")
# 目录名按「整段精确匹配」，避免误伤报告标题（如「底部抬升小区热线数据分析报告.html」）
FORBIDDEN_DIRS = ("data", "scripts", "src", "tests", "cloud_private",
                  "热线数据", "徐汇各科室业务数据", "月度分析报告", "年度分析报告")
# 文件名按关键词匹配
FORBIDDEN_FILE_KEYS = ("9月复核工单下载", "未匹配纳统", "热线与纳统小区全量匹配表",
                       "复核工单下载")


def run(cmd, cwd=None, check=True, quiet=False):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        print(f"  ❌ 命令失败：{' '.join(cmd)}")
        print((p.stdout or "")[-1500:])
        print((p.stderr or "")[-1500:])
        sys.exit(1)
    if not quiet and p.stdout.strip():
        for line in p.stdout.strip().splitlines():
            print("     " + line)
    return p


def step(n, title):
    print(f"\n【{n}】{title}")


# ---------------------------------------------------------------- 1. 组装
def build():
    step(1, "组装发布目录 _publish/")
    script = os.path.join(ROOT, "scripts", "build_publish_site.py")
    run([sys.executable, script], cwd=ROOT)


def scan_forbidden(root):
    """返回 [(相对路径, 原因)] —— 同时用于 _publish 体检与工作树兜底复核。"""
    bad = []
    for dp, _dn, fns in os.walk(root):
        if f"{os.sep}.git" in dp:
            continue
        for fn in fns:
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, root)
            parts = rel.replace("\\", "/").split("/")
            if fn.lower().endswith(FORBIDDEN_EXT):
                bad.append((rel, "禁止的文件类型"))
            elif any(p in FORBIDDEN_DIRS for p in parts[:-1]):
                bad.append((rel, "位于禁止的目录"))
            elif any(k in parts[-1] for k in FORBIDDEN_FILE_KEYS):
                bad.append((rel, "命中禁止的文件名关键词"))
    return bad


# ------------------------------------------------------- 2. 产物体检
def audit():
    step(2, "发布产物体检")
    if not os.path.isdir(PUB):
        print(f"  ❌ 目录不存在：{PUB}（先跑 build_publish_site.py）")
        sys.exit(1)

    files = []
    for dp, _dn, fns in os.walk(PUB):
        for fn in fns:
            files.append(os.path.relpath(os.path.join(dp, fn), PUB))

    bad = scan_forbidden(PUB)
    if bad:
        print("  ❌ 产物含禁止发布的内容，已终止：")
        for rel, why in bad:
            print(f"       {rel}  ← {why}")
        sys.exit(1)

    html = [f for f in files if f.endswith(".html")]
    total = sum(os.path.getsize(os.path.join(PUB, f)) for f in files)
    print(f"  文件 {len(files)} 个（HTML {len(html)} 份）· {total / 1024 / 1024:.2f} MB")
    print(f"  ✅ 无禁止类型（{', '.join(FORBIDDEN_EXT[:6])} …）")
    for need in ("index.html", "课题成果总览.html"):
        if need not in files:
            print(f"  ❌ 缺少关键页：{need}")
            sys.exit(1)
    print("  ✅ 关键页齐备（index.html / 课题成果总览.html）")
    return files


# ------------------------------------------------- 3. 同步到 gh-pages
def sync(workdir, dry_run):
    step(3, f"同步到 {BRANCH} 分支")
    run(["git", "fetch", REMOTE, BRANCH], cwd=ROOT, check=False, quiet=True)
    has_remote = subprocess.run(["git", "rev-parse", "--verify", "-q",
                                 f"{REMOTE}/{BRANCH}"], cwd=ROOT,
                                capture_output=True).returncode == 0

    # 用工作树操作，绝不动 main 的工作区
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    subprocess.run(["git", "worktree", "prune"], cwd=ROOT, capture_output=True)
    base = f"{REMOTE}/{BRANCH}" if has_remote else "HEAD"
    run(["git", "worktree", "add", "--detach", workdir, base], cwd=ROOT, quiet=True)
    run(["git", "checkout", "-B", BRANCH], cwd=workdir, quiet=True)
    print(f"  基线：{base}（{'沿用远程分支' if has_remote else '新建孤儿分支'}）")

    # 清空 → 拷入（保留 .git）
    for name in os.listdir(workdir):
        if name == ".git":
            continue
        p = os.path.join(workdir, name)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    for name in os.listdir(PUB):
        src, dst = os.path.join(PUB, name), os.path.join(workdir, name)
        shutil.copytree(src, dst) if os.path.isdir(src) else shutil.copy2(src, dst)
    # .nojekyll：禁用 Jekyll，否则中文名/下划线目录可能被吞
    open(os.path.join(workdir, ".nojekyll"), "w").close()

    # 兜底再查一次（防止拷贝阶段引入）
    bad2 = scan_forbidden(workdir)
    if bad2:
        print("  ❌ 工作树出现禁止内容：")
        for rel, why in bad2:
            print(f"       {rel}  ← {why}")
        sys.exit(1)

    run(["git", "add", "-A"], cwd=workdir, quiet=True)
    changed = subprocess.run(["git", "status", "--porcelain"], cwd=workdir,
                             capture_output=True, text=True).stdout.strip()
    if not changed:
        print("  = 内容与远程一致，无需提交")
        return False
    n = len(changed.splitlines())
    print(f"  待提交变更：{n} 项")

    if dry_run:
        print("  [dry-run] 不提交、不推送")
        return False

    msg = ("chore: 发布成果站到 gh-pages（GitHub Pages 专用发布分支）\n\n"
           "仅含成果报告页与其依赖资源，不含脚本、docx/xlsx 数据文件与原始工单明细。\n"
           "由 scripts/build_publish_site.py + scripts/publish_gh_pages.py 生成。")
    run(["git", "commit", "-q", "-m", msg], cwd=workdir, quiet=True)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=workdir,
                          capture_output=True, text=True).stdout.strip()
    run(["git", "push", REMOTE, f"{BRANCH}:{BRANCH}"], cwd=workdir)
    print(f"  ✅ 已推送 {BRANCH} @ {head}")
    return True


# --------------------------------------------- 4. 切换 Pages 发布源
def set_source():
    step(4, "把 Pages 发布源切到 gh-pages")
    tok = subprocess.run(["security", "find-internet-password", "-s", "github.com", "-w"],
                         capture_output=True, text=True).stdout.strip()
    if not tok:
        print("  ⚠️ 钥匙串里取不到 GitHub 凭据，跳过")
        return
    import json
    import urllib.error
    import urllib.request

    api = "https://api.github.com/repos/sanjune/xuhui_research2026/pages"
    req = urllib.request.Request(api, method="PUT",
                                data=json.dumps({"source": {"branch": BRANCH, "path": "/"}}).encode(),
                                headers={"Authorization": f"Bearer {tok}",
                                         "Accept": "application/vnd.github+json",
                                         "X-GitHub-Api-Version": "2022-11-28",
                                         "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30)
        print("  ✅ 发布源已切换")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        if e.code == 403:
            print("  ⚠️ 凭据无 Pages 权限（403 Resource not accessible by personal access token）")
            print("     → 手动切换：仓库 Settings → Pages → Build and deployment")
            print("       Source 选 “Deploy from a branch”，Branch 选 gh-pages / (root)，Save")
        else:
            print(f"  ⚠️ HTTP {e.code}：{body[:200]}")


def cleanup(workdir):
    subprocess.run(["git", "worktree", "remove", "--force", workdir],
                   cwd=ROOT, capture_output=True)
    subprocess.run(["git", "worktree", "prune"], cwd=ROOT, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-build", action="store_true", help="跳过组装，发布现有 _publish/")
    ap.add_argument("--dry-run", action="store_true", help="只检查，不提交不推送")
    ap.add_argument("--set-source", action="store_true", help="尝试用 API 切换 Pages 发布源")
    a = ap.parse_args()

    print("=" * 68)
    print("发布成果站到 GitHub Pages（gh-pages 分支）")
    print("=" * 68)
    if not a.no_build and not a.dry_run:
        build()
    audit()

    workdir = tempfile.mkdtemp(prefix="_ghpages_")
    shutil.rmtree(workdir)
    try:
        pushed = sync(workdir, a.dry_run)
    finally:
        cleanup(workdir)

    if a.set_source and not a.dry_run:
        set_source()

    step(5, "结果")
    cfg = subprocess.run(["git", "config", "--get", "remote.origin.url"],
                         cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"  仓库：{cfg}")
    print(f"  站点：{PAGES_URL}")
    print(f"  分支：{BRANCH}{'（本次有更新）' if pushed else '（无变化）'}")
    print("  提示：Pages 发布源须为 gh-pages / (root)，改完报告重跑本脚本即可覆盖发布。")


if __name__ == "__main__":
    main()
