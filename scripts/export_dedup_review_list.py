# -*- coding: utf-8 -*-
"""
导出「当月复核工单 · 重复工单清单」
==================================

读入外部复核工单表，按项目四重策略（dedup_monthly.py）判定重复，
把「复核结论」「去重清单」「重复组明细」三张工作表写回该 xlsx（原 sheet1 数据不动）。

清单的核心是回答「哪几条工单是同一件重复投诉」：
用并查集把互相构成重复关系的工单聚成「重复组」，每组给出组号、组内条数、
关联原件编号（组内最早受理、建议保留的那条）与各组员的诉求摘要。

【表外首单溯源】（v2.9.0）
复核表只有当月工单，但本月工单正文常带系统引用块
「【最近派发的工单编号：X，工单内容：…】」，指向**更早的原始首单**。
若首单不在本月，则：
    1) 从工单主库 data/merged_cleaned.pkl（2024-01～2026-08）反查该编号，
       把它的受理时间/小区/街道/物业公司/类别/诉求摘要补成清单里的一行；
    2) 递归沿引用块继续上溯（默认 ≤3 层），把「前几个」历史工单一并列进来；
    3) 非本月行用**琥珀色块**标记；工单库查不到的用**灰色块**标记（未收录）。
补入行只作溯源，**不参与**本月重复判定，分母与重复数一律不动。

【引用块文本比对兜底】（v2.11.0）
引用块的「工单编号」位可能被写坏（例：`【最近办结的工单编号:反黑，工单内容:…】`，
编号位被填成了文字），或写法缺「号」字（`【重新交办，关联工单20260822223850】`）——
前者按编号永远抓不到，后者已由放宽后的 ORDER_REF_RE 覆盖。
对「按编号一个都没抓到」的组，改用引用块**正文片段**回主库比对：
限同一小区、受理时间更早，取时间最接近的一笔（取多个偏移的 40 字指纹，
避开块头编号位的差异）。仍然只作溯源，判定口径不动。

【清单口径】（v2.10.0）
去重清单是**工单级**明细，回答「这条工单与哪条重复」。三类行：
    1) 本月被判重复的工单（复核对象，白底／组斑马底）
    2) 本月**未被判重复**、但与该重复组同属一案的首件（**浅绿色块**，
       标记为「保留件·未判重复」）——它是本组的合并归集对象，仅供比对，
       与判定无关，不改变任何计数
    3) 表外历史首单溯源行（琥珀／灰底色块）
新增「重复对象」列：逐行写明本行与组内哪条构成重复（实务上即「合并至建议保留件」），
无需再跨表查「重复组明细」。

【S2 纳入系统标记「重复来电」】（v2.12.0）
S2 在原「催单/催办/重新交办/相同事项 + 反复搭配」之外，新增第 ③ 支判据：
**本单正文段含系统自动标记「重复来电」**（话务平台直接打在本单上的标签，
属最明确的重复信号）。匹配前先剥离系统引用块，避免把引用块内转载的
历史原文措辞误当成本单标记。口径源＝scripts/dedup_monthly.py :: S2_SYS_MARKS。
影响（9 月复核表 1,516 条）：重复 600 → 609（39.6% → 40.2%），高 500 → 517，S2 271 → 295。

归并关系（仅用于「成组」，不改动任何判定口径）：
    1) S1 完全一致   同 (小区, 内容原文)
    2) S3 同类高频   同 (小区, 十四类) 且条数 ≥ FREQ_THRESHOLD
    3) S4 文本相似   余弦 ≥0.6 且受理时间间隔 ≤90 天的相似对
    4) 引用关系     正文出现「工单编号：X」且 X 在本表内（催单/补充类指向首单）

用法：
    PYTHONPATH=~/.workbuddy/binaries/python/vendor /usr/bin/python3 \
        scripts/export_dedup_review_list.py --xlsx "/path/to/表.xlsx"
"""
import argparse
import os
import re
import sys
from collections import Counter, defaultdict

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dedup_monthly as D  # noqa: E402
from dedup_review_external import (  # noqa: E402
    ORDER_REF_RE, QUOTED_BLOCK_RE, analyze_external, strip_quoted)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST_PKL = os.path.join(ROOT, "data", "merged_cleaned.pkl")

HEAD_FILL = PatternFill("solid", fgColor="1D4ED8")
HEAD_FONT = Font(color="FFFFFF", bold=True, size=11)
HIGH_FONT = Font(color="B91C1C", bold=True)
MID_FONT = Font(color="B45309")
GROUP_FILLS = [PatternFill("solid", fgColor="EEF2FF"),
               PatternFill("solid", fgColor="F8FAFC")]
ORIG_FONT = Font(color="1D4ED8", bold=True)
HIST_FILL = PatternFill("solid", fgColor="FDE68A")      # 非本月历史工单
UNRES_FILL = PatternFill("solid", fgColor="E5E7EB")     # 表外未收录
HIST_FONT = Font(color="92400E", bold=True)
PRESERVE_FILL = PatternFill("solid", fgColor="DCFCE7")  # 本月保留件（未判重复，仅比对）
PRESERVE_FONT = Font(color="166534", bold=True)
OTHER_FILL = PatternFill("solid", fgColor="E0F2FE")     # 同组其他未判重复工单
OTHER_FONT = Font(color="075985", bold=True)

SUMMARY_LEN = 60
MAX_DEPTH = 3           # 沿引用块最多上溯层数（首单 + 前序）
MAX_HIST = 12           # 单组最多补入的历史工单行数

# 【引用块文本比对兜底】（v2.11.0）
# 引用块是系统把上一笔工单原文机械转载进来的，因此块内长片段与主库原文逐字相同。
# 当块头的「工单编号」位被写坏（如写成「反黑」）或写法缺「号」字时，
# 按编号抓不到被引用件，改用正文片段回主库比对定位。
BLOCK_FIND_RE = re.compile(r"【([^【】]{40,})】")
CONTENT_MARK = "工单内容"
TEXT_MATCH_OFFSETS = (20, 0, 40)    # 指纹在块内正文的取位（避开块头的编号差异）
TEXT_MATCH_LEN = 40                 # 单个指纹长度（规范化后字符数）
TEXT_MATCH_MIN = 24                 # 命中所需的最短长度


# ─────────────────────── 工单主库（表外历史工单） ───────────────────────

def load_history_db(pkl: str = HIST_PKL) -> pd.DataFrame:
    """加载工单主库，按 order_id 建索引（用于反查表外首单）。"""
    m = pd.read_pickle(pkl)
    m["order_id"] = m["order_id"].astype(str)
    m["t"] = pd.to_datetime(m["accept_time"], errors="coerce")
    m = m.drop_duplicates("order_id").set_index("order_id", drop=False)
    return m


def presumed_date(oid: str):
    """工单编号前 8 位＝受理日期（主库一致率 95.5%），用于未收录工单的推定时间。"""
    if len(oid) >= 8 and oid[:8].isdigit():
        try:
            return pd.Timestamp(f"{oid[:4]}-{oid[4:6]}-{oid[6:8]}")
        except Exception:
            return pd.NaT
    return pd.NaT


def trace_history(ext_refs: dict, db, in_table: set, cur_month: str,
                  max_depth: int = MAX_DEPTH, cap: int = MAX_HIST):
    """沿引用块向上追溯表外工单。

    ext_refs: {表外编号: [引用它的表内编号, ...]}
    返回 (items, unresolved)；items 按受理时间升序（最早的在前）。
    """
    items, unresolved, seen = [], [], set()
    # depth=1（被本月工单直接引用的首单）也要带上「引用来源」，
    # 否则「引用来源」列在首单层全为空，无法看出这条是被哪笔本月工单引出来的
    queue = [(oid, 1, (ext_refs.get(oid) or [""])[0]) for oid in ext_refs]
    while queue:
        oid, depth, frm = queue.pop(0)
        if oid in seen or depth > max_depth:
            continue
        seen.add(oid)
        if oid in in_table:                 # 本表内工单已是清单行，无需补入
            continue
        if oid not in db.index:
            unresolved.append({
                "oid": oid, "depth": depth, "frm": frm,
                "t": presumed_date(oid),
                "month": cur_month if oid[:6] == cur_month.replace("-", "") else "",
            })
            continue
        r = db.loc[oid]
        items.append({
            "oid": oid, "depth": depth, "frm": frm, "t": r["t"],
            "community": r["community_name"] or "", "street": r["street"] or "",
            "property": r["property_company"] or "", "category": r["category_14"] or "",
            "content": str(r["content"] or ""),
        })
        if depth < max_depth:
            for tgt in ORDER_REF_RE.findall(str(r["content"] or "")):
                if tgt not in seen:
                    queue.append((tgt, depth + 1, oid))

    items.sort(key=lambda x: (pd.isna(x["t"]), x["t"]))
    unresolved.sort(key=lambda x: (pd.isna(x["t"]), x["t"]))
    if len(items) + len(unresolved) > cap:
        items, unresolved = items[:cap], []
    return items, unresolved


# ────────────────── 引用块文本比对（编号抓不到时的兜底） ──────────────────

def _norm_text(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def quote_fingerprints(txt: str):
    """从正文的引用块里提取「内容指纹」，用于回主库比对定位被引用工单。

    取块内「工单内容:」之后的正文（无该标记则取整块），去掉空白后
    从若干偏移处各截一段。多取几个偏移是为了避开块头「工单编号」位的差异
    （例如 9 月单写「工单编号:反黑」、主库原文写「工单编号:20260727234206」）。
    """
    out = []
    for m in BLOCK_FIND_RE.finditer(txt or ""):
        b = m.group(1)
        k = b.rfind(CONTENT_MARK)
        seg = b[k + len(CONTENT_MARK):] if k >= 0 else b
        seg = _norm_text(seg.lstrip("：:，,、 "))
        if len(seg) < TEXT_MATCH_MIN + max(TEXT_MATCH_OFFSETS):
            continue
        for off in TEXT_MATCH_OFFSETS:
            fp = seg[off:off + TEXT_MATCH_LEN]
            if len(fp) >= TEXT_MATCH_MIN and fp not in out:
                out.append(fp)
    return out


def make_norm_indexer(db):
    """按小区懒加载「规范化正文」清单：[(order_id, 规范化正文, 受理时间)]。"""
    cache = {}

    def get(community):
        if community not in cache:
            sub = db[db["community_name"] == community]
            cache[community] = [
                (str(r["order_id"]), _norm_text(str(r["content"] or "")), r["t"])
                for _, r in sub.iterrows()]
        return cache[community]

    return get


def recover_ref_by_text(txt, community, before_t, get_rows):
    """编号缺失/写坏时，用引用块正文片段回主库反查被引用的上一笔工单。

    限定「同一小区 + 受理时间更早」，取时间最接近（即最近的上一笔）的那条。
    """
    fps = quote_fingerprints(txt)
    if not fps or get_rows is None:
        return None
    best = None
    for oid, nc, t in get_rows(community):
        if pd.isna(t) or (pd.notna(before_t) and t >= before_t):
            continue
        if any(fp in nc for fp in fps) and (best is None or t > best[1]):
            best = (oid, t)
    return best


# ─────────────────────────── 重复组聚类 ───────────────────────────

def _find(par, x):
    while par[x] != x:
        par[x] = par[par[x]]
        x = par[x]
    return x


def _union(par, a, b):
    ra, rb = _find(par, a), _find(par, b)
    if ra != rb:
        par[ra] = rb


def summary(text, n=SUMMARY_LEN):
    """诉求摘要：剥离系统引用块后截断；若整条就是引用块则回退原文。"""
    s = strip_quoted(text or "")
    if not s.strip():
        s = text or ""
    s = re.sub(r"\s+", " ", s).strip()
    # 引用块常被插在句首/句尾，剥离后会剩下一个孤零零的标点，一并清掉
    s = s.lstrip("，,。、；;：:）)】} ")
    return s[:n]


def build_groups(res, db=None, cur_month="", get_rows=None):
    """把重复工单按「同一问题」聚成组。

    返回 (rows 组级列表, assign 行索引→组信息 dict)。
    db/cur_month 提供时，同步追溯每组「表外历史首单」。
    get_rows 提供时，对「引用块编号抓不到」的组启用文本比对兜底。
    """
    d, sets = res["_d"], res["_sets"]
    par = {i: i for i in d.index}
    links = []          # (i, j, 关系标签)

    # 1) S1 完全一致
    work = d[d["content"] != ""]
    for _, g in work.groupby(["community_name", "content"], sort=False):
        if len(g) < 2:
            continue
        idx = list(g.sort_values("t").index)
        links += [(idx[0], k, "S1完全一致") for k in idx[1:]]
    # 2) S3 同类高频
    for _, g in d.groupby(["community_name", "category_14"], sort=False):
        if len(g) < D.FREQ_THRESHOLD:
            continue
        idx = list(g.sort_values("t").index)
        links += [(idx[0], k, "S3同类高频") for k in idx[1:]]
    # 3) S4 文本相似
    for p in res["_s4_pairs"]:
        links.append((p["ai"], p["bi"], "S4文本相似"))
    # 4) 引用关系（催单/补充类正文里指向首单）
    oid2idx = {str(v): i for i, v in d["order_id"].items()}
    for i, txt in d["content"].items():
        for tgt in set(ORDER_REF_RE.findall(txt or "")):
            j = oid2idx.get(tgt)
            if j is not None and j != i:
                links.append((i, j, "引用首单"))

    for i, j, _ in links:
        _union(par, i, j)

    members = defaultdict(list)
    for i in d.index:
        members[_find(par, i)].append(i)

    rel_of_root = defaultdict(set)
    for i, j, lab in links:
        rel_of_root[_find(par, i)].add(lab)

    REL_ORDER = ["S1完全一致", "S3同类高频", "S4文本相似", "引用首单"]
    union_set = sets["union"]
    in_table = set(oid2idx)

    def oid(i):
        v = d.at[i, "order_id"]
        return str(v) if pd.notna(v) else ""

    rows = []
    for root, mem in members.items():
        mem = sorted(mem, key=lambda i: (pd.isna(d.at[i, "t"]), d.at[i, "t"], i))
        dup_mem = [i for i in mem if i in union_set]
        if not dup_mem:                     # 该组没有任何工单被判重复，跳过
            continue
        # 组内成员引用到「本表之外」的工单编号（复核表只有当月复核单，首单常不在表内）
        ext = defaultdict(list)             # 表外编号 → 引用它的表内编号
        for i in mem:
            for tgt in ORDER_REF_RE.findall(d.at[i, "content"] or ""):
                if tgt not in oid2idx and oid(i) not in ext[tgt]:
                    ext[tgt].append(oid(i))
        ext = dict(ext)

        # 引用块编号抓不到时的兜底：改用块内正文片段回主库比对定位被引用件。
        # 只在「本组没有任何表外编号」且「该工单引用的不是本表内工单」时才尝试，
        # 避免与既有的按编号溯源重复或互相干扰。
        recovered = set()
        if get_rows is not None and not ext:
            for i in mem:
                txt = d.at[i, "content"] or ""
                if any(t in oid2idx for t in ORDER_REF_RE.findall(txt)):
                    continue            # 引用的是本表内工单，无需表外溯源
                hit = recover_ref_by_text(txt, d.at[i, "community_name"],
                                          d.at[i, "t"], get_rows)
                if hit:
                    ext[hit[0]] = [oid(i)]
                    recovered.add(hit[0])
                    break

        single = len(mem) == 1
        orig = mem[0]
        rels = [r for r in REL_ORDER if r in rel_of_root[root]]
        if single:
            rel_txt = ("催办/重复标记｜首单不在本表"
                       if ext else "催办/重复标记｜无引用首单")
        else:
            rel_txt = "+".join(rels) if rels else "同组（未标注关系）"

        hist, unres = ([], [])
        if db is not None and ext:
            hist, unres = trace_history(ext, db, in_table, cur_month)

        rows.append({
            "members": mem,
            "dup_members": dup_mem,
            "other_members": [i for i in mem if i not in union_set and i != orig],
            "orig": None if single else orig,       # 单条组无组内保留件
            "size": len(mem),
            "dup_cnt": len(dup_mem),
            "rels": rel_txt,
            "ext_refs": list(ext),
            "text_refs": recovered,
            "hist": hist,
            "unres": unres,
            "n_ext": len(hist) + len(unres),
            "community": d.at[orig, "community_name"],
            "street": d.at[orig, "street"],
            "category": d.at[orig, "category_14"],
            "property": d.at[orig, "property_company"],
            "t": d.at[orig, "t"],
            "orig_oid": ("" if single else oid(orig)),
            "orig_summary": ("" if single else summary(d.at[orig, "content"])),
            "dup_oids": "、".join(oid(i) for i in dup_mem),
            "other_oids": "、".join(oid(i) for i in [x for x in mem
                                                     if x not in union_set and x != orig]),
            "priority": "高" if any(i in sets["high"] for i in mem) else "中",
        })

    # 排序与 v2.8.0 一致（组号不得漂移）：条数降序 → 小区 → 首单时间
    rows.sort(key=lambda r: (-r["size"], str(r["community"]), r["t"]))
    assign = {}
    for n, r in enumerate(rows, 1):
        r["gid"] = f"G{n:03d}"
        for pos, i in enumerate(r["members"], 1):
            assign[i] = {"gid": r["gid"], "size": r["size"], "pos": pos,
                         "rels": r["rels"], "orig": r["orig"],
                         "single": r["size"] == 1, "ext_refs": r["ext_refs"]}
    return rows, assign


# ─────────────────────────── 清单行 ───────────────────────────

def _hist_role(depth):
    """表外工单的组内角色：depth=1 为本月工单直接引用的首单，更深为前序工单。"""
    return "表外首单" if depth == 1 else f"表外前序·{depth-1}级"


def build_rows(res, rows_g, cur_month):
    """清单行＝ 表内被判重复的工单 + 该组「表外历史首单」溯源行，按时间轴统一排序。"""
    d, sets = res["_d"], res["_sets"]
    sim, freq = res["_order_sim"], res["_freq"]
    union, high = sets["union"], sets["high"]

    # 系统标记「重复来电」（与 S2 同口径：剥离引用块后只看本单正文段），
    # 用于在「复核建议」里点明命中原因——这条比关键词推断更硬，复核人一眼可信
    _c = d["content"].fillna("").astype(str)
    _cand = _c.index[_c.str.contains(D.S2_SYS_RE, regex=True, na=False)]
    sys_hit = {i for i in _cand if D.S2_SYS_RE.search(D._head_text(_c[i]))}
    res["_sys_hit"] = sys_hit      # 供 main 统计用（"_" 前缀字段不写入 JSON）

    out = []
    for grp in rows_g:
        gid = grp["gid"]
        hist, unres = grp.get("hist") or [], grp.get("unres") or []
        n_hist = len(hist) + len(unres)

        # 全组时间轴：表外历史 → 本月全部成员（均按受理时间升序）。
        # 「组内序号」＝该工单在整条案件时间轴上的位次（含未判重复的同簇工单与表外工单），
        # 故 max(组内序号) ＝ 组内条数 ＋ 表外历史条数；清单只列被判重复的行。
        all_mem = sorted(grp["members"],
                         key=lambda i: (pd.isna(d.at[i, "t"]), d.at[i, "t"], i))
        timeline = []
        for h in hist:
            timeline.append(("hist", h, h["t"]))
        for u in unres:
            timeline.append(("unres", u, u["t"]))
        for i in all_mem:
            timeline.append(("cur", i, d.at[i, "t"]))
        timeline.sort(key=lambda x: (pd.isna(x[2]), x[2],
                                     0 if x[0] == "hist" else (1 if x[0] == "unres" else 2)))
        keep_oid = ""
        if grp["orig"] is None:             # 单条组：建议保留＝表外首单
            keep_oid = "、".join(
                f"（表外·{h['t']:%Y-%m}）{h['oid']}" if pd.notna(h["t"]) else f"（表外）{h['oid']}"
                for h in hist) or "、".join(f"（表外）{x}" for x in grp["ext_refs"]) or "—"
        else:
            keep_oid = grp["orig_oid"]

        for pos, (kind, obj, tt) in enumerate(timeline, 1):
            if kind == "cur":
                r = d.loc[obj]
                t = r["t"]
                to = grp["t"] if grp["orig"] is not None else pd.NaT
                days = int((t - to).days) if (pd.notna(t) and pd.notna(to)) else None
                com, cat = r["community_name"], r["category_14"]
                n = freq.get((com, cat))
                if obj not in union:
                    # 组内未被判重复的同案工单：出行供比对（色块 + 角色名区分两类）——
                    #   「保留件·未判重复」  ＝组内最早，即本组建议保留件（合并归集对象）
                    #   「同组其他·未判重复」＝同组更晚的未判重复工单（如 S3 高频组的旁证）
                    is_keep = grp["orig"] is not None and obj == grp["orig"]
                    if is_keep:
                        role = "保留件·未判重复"
                        tgt = (f"本组 {grp['dup_cnt']} 条重复工单均指向本件"
                               + (f"；另有表外引用 {len(grp['ext_refs'])} 个编号"
                                  if grp["ext_refs"] else ""))
                        advice = "保留件—未判重复，仅作同组比对，不纳入去重判定"
                    else:
                        role = "同组其他·未判重复"
                        tgt = (f"{grp['orig_oid']}（本组首单·建议保留）"
                               if grp["orig"] is not None
                               else "、".join(grp["ext_refs"]) or "—")
                        advice = "同组其他—未判重复，仅作同组比对，不纳入去重判定"
                    out.append({
                        "组号": gid, "组内条数": grp["size"], "表外历史条数": n_hist,
                        "组内序号": pos, "组内角色": role,
                        "工单归属": f"本月（{cur_month}）·保留件", "引用来源": "",
                        "工单编号": str(r["order_id"]),
                        "重复对象": tgt,
                        "受理时间": t.strftime("%Y-%m-%d %H:%M") if pd.notna(t) else "",
                        "小区": com, "街道": r["street"],
                        "物业公司": r["property_company"], "类别（十四类）": cat,
                        "建议保留工单": keep_oid,
                        "保留件受理时间": (t.strftime("%Y-%m-%d %H:%M")
                                           if pd.notna(t) else ""),
                        "间隔天数": None, "组内关系": grp["rels"],
                        "命中策略": "—（未判重复）",
                        "同类频次": int(n) if n else None,
                        "文本相似度": round(sim[obj], 2) if obj in sim else None,
                        "优先级": grp["priority"],
                        "诉求摘要": summary(r["content"]),
                        "保留件诉求摘要": summary(r["content"]),
                        "复核建议": advice,
                        "_p": 0 if grp["priority"] == "高" else 1, "_seq": pos,
                    })
                    continue
                if grp["size"] == 1:
                    role = "仅有此单（本月复核）"
                elif obj == grp["orig"]:
                    role = "保留件（本月最早）" if n_hist else "保留件（组内最早）"
                else:
                    role = "重复件"
                # 「重复对象」＝本行与组内哪条构成重复 → 实务上即合并至建议保留件
                if obj == grp["orig"]:
                    tgt = (f"（表外）{hist[0]['oid']}（表外首单·建议合并至该件）"
                           if n_hist else
                           "（本件为组内最早，但自身亦被判重复；案件首单不在本表）")
                elif grp["orig"] is not None:
                    tgt = f"{grp['orig_oid']}（本组首单·建议合并至该件）"
                    if grp["other_members"]:
                        tgt += f"；同组另有 {len(grp['other_members'])} 条未判重复"
                else:
                    tgt = f"{keep_oid}（表外首单·建议合并至该件）"
                tags = [k.upper() for k in ("s1", "s2", "s3", "s4") if obj in sets[k]]
                out.append({
                    "组号": gid, "组内条数": grp["size"], "表外历史条数": n_hist,
                    "组内序号": pos, "组内角色": role,
                    "工单归属": f"本月（{cur_month}）", "引用来源": "",
                    "工单编号": str(r["order_id"]),
                    "重复对象": tgt,
                    "受理时间": t.strftime("%Y-%m-%d %H:%M") if pd.notna(t) else "",
                    "小区": com, "街道": r["street"], "物业公司": r["property_company"],
                    "类别（十四类）": cat,
                    "建议保留工单": keep_oid,
                    "保留件受理时间": (to.strftime("%Y-%m-%d %H:%M")
                                       if pd.notna(to) else ""),
                    "间隔天数": days, "组内关系": grp["rels"],
                    "命中策略": "+".join(tags),
                    "同类频次": int(n) if n else None,
                    "文本相似度": round(sim[obj], 2) if obj in sim else None,
                    "优先级": "高" if obj in high else "中",
                    "诉求摘要": summary(r["content"]),
                    "保留件诉求摘要": (summary(d.at[grp["orig"], "content"])
                                       if grp["orig"] is not None else ""),
                    "复核建议": (("重复投诉—核实合并"
                                  + ("（系统标记「重复来电」）" if obj in sys_hit else ""))
                                 if obj in sets["s1"] | sets["s2"] | sets["s3"]
                                 else "文本相似—核实合并"),
                    "_p": 0 if grp["priority"] == "高" else 1, "_seq": pos,
                })
            elif kind == "hist":
                h = obj
                # 该件是靠「引用块文本比对」而非「编号」定位到的，标注出来便于复核
                by_text = h["oid"] in (grp.get("text_refs") or set())
                frm = f"{h['frm']}（引用块文本比对定位）" if (by_text and h["frm"]) else h["frm"]
                out.append({
                    "组号": gid, "组内条数": grp["size"], "表外历史条数": n_hist,
                    "组内序号": pos,
                    "组内角色": f"{_hist_role(h['depth'])}·{h['t']:%Y-%m}" if pd.notna(h["t"])
                                else _hist_role(h["depth"]),
                    "工单归属": (f"非本月（{h['t']:%Y-%m}）" if pd.notna(h["t"])
                                 else "非本月"), "引用来源": frm,
                    "工单编号": h["oid"],
                    "重复对象": ((f"本件为该案原始件，被"
                                  f"{'本月工单' if h['depth'] == 1 else '上一级表外工单'}"
                                  f" {h['frm']} 引用")
                                 if h["frm"] else "本件为该案原始件（被本组工单引用）"),
                    "受理时间": h["t"].strftime("%Y-%m-%d %H:%M") if pd.notna(h["t"]) else "",
                    "小区": h["community"], "街道": h["street"],
                    "物业公司": h["property"], "类别（十四类）": h["category"],
                    "建议保留工单": "—（本条为表外原始件）",
                    "保留件受理时间": "", "间隔天数": None,
                    "组内关系": (f"被{'本月工单' if h['depth'] == 1 else '上一级表外工单'}引用"
                                 f"（表外溯源{'·文本比对' if by_text else ''}）"),
                    "命中策略": "—（表外工单）", "同类频次": None, "文本相似度": None,
                    "优先级": grp["priority"],
                    "诉求摘要": summary(h["content"]),
                    "保留件诉求摘要": "",
                    "复核建议": "非本月工单—仅溯源，不纳入本月去重判定",
                    "_p": 0 if grp["priority"] == "高" else 1, "_seq": pos,
                })
            else:
                u = obj
                out.append({
                    "组号": gid, "组内条数": grp["size"], "表外历史条数": n_hist,
                    "组内序号": pos,
                    "组内角色": (f"{_hist_role(u['depth'])}·未收录"
                                 if u["depth"] == 1 else f"表外前序·{u['depth']-1}级（未收录）"),
                    "工单归属": ("本月·未收录" if u["month"] else "非本月·未收录"),
                    "引用来源": u["frm"],
                    "工单编号": u["oid"],
                    "重复对象": (f"本件为该案原始件（工单库未收录），被本月工单 {u['frm']} 引用"
                                 if u["frm"] else
                                 "本件为该案原始件（工单库未收录）"),
                    "受理时间": (f"{u['t']:%Y-%m-%d}（编号推定）"
                                 if pd.notna(u["t"]) else ""),
                    "小区": "", "街道": "", "物业公司": "", "类别（十四类）": "",
                    "建议保留工单": "—（工单库未收录）",
                    "保留件受理时间": "", "间隔天数": None,
                    "组内关系": (f"被{'本月工单' if u['depth'] == 1 else '上一级表外工单'}引用"
                                 "（表外溯源）"),
                    "命中策略": "—（表外工单）", "同类频次": None, "文本相似度": None,
                    "优先级": grp["priority"],
                    "诉求摘要": "", "保留件诉求摘要": "",
                    "复核建议": "表外工单—工单库未收录，无法核对",
                    "_p": 0 if grp["priority"] == "高" else 1, "_seq": pos,
                })

    df = pd.DataFrame(out)
    df = (df.sort_values(["_p", "组内条数", "组号", "_seq"],
                         ascending=[True, False, True, True])
            .drop(columns=["_p", "_seq"]).reset_index(drop=True))
    return df


def build_group_sheet(rows_g):
    """一组一行：直接看「哪几条工单是同一件重复投诉」，并给出表外首单溯源。"""
    out = []
    for r in rows_g:
        single = r["orig"] is None
        hist, unres = r.get("hist") or [], r.get("unres") or []

        def _f(x):
            return f"（表外·{x['t']:%Y-%m}）{x['oid']}" if pd.notna(x["t"]) else f"（表外）{x['oid']}"

        keep = (("、".join(_f(x) for x in hist) or "—") if single else r["orig_oid"])
        if single and not hist and r["ext_refs"]:
            keep = "、".join(f"（表外）{x}" for x in r["ext_refs"])
        first_h = hist[0] if hist else None
        detail = "｜".join(
            f"{h['t']:%Y-%m-%d} {h['oid']}"
            f"{'（' + h['community'] + '）' if h['community'] else ''}"
            for h in hist[:5]
            if pd.notna(h["t"])) + ("｜…" if len(hist) > 5 else "")
        if unres:
            detail = (detail + "｜" if detail else "") + \
                     "、".join(f"{u['oid']}（未收录）" for u in unres[:3])
        out.append({
            "组号": r["gid"],
            "组内条数": r["size"],
            "重复条数": r["dup_cnt"],
            "表外历史条数": len(hist) + len(unres),
            "组内关系": r["rels"],
            "小区": r["community"],
            "街道": r["street"],
            "类别（十四类）": r["category"],
            "物业公司": r["property"],
            "建议保留工单": keep,
            "保留件受理时间": (f"{first_h['t']:%Y-%m-%d %H:%M}"
                          if single and first_h and pd.notna(first_h["t"])
                          else ("" if single or pd.isna(r["t"])
                                else r["t"].strftime("%Y-%m-%d %H:%M"))),
            "保留件诉求摘要": ("" if single else r["orig_summary"]),
            "表外首单编号": (first_h["oid"] if first_h
                        else (unres[0]["oid"] if unres else "")),
            "表外首单受理时间": (f"{first_h['t']:%Y-%m-%d %H:%M}"
                           if first_h and pd.notna(first_h["t"]) else ""),
            "表外工单摘要": detail,
            "重复工单编号": r["dup_oids"],
            "同组其他编号（未判重复）": (
                r["other_oids"] or
                ("—（组内除「建议保留工单」外无其他工单）" if not single
                 else ("—（单条组，组内仅本件；首件见表外溯源）"
                       if (hist or unres) else
                       "—（单条组，组内仅本件，正文无可溯源引用）"))),
            "组内优先级": r["priority"],
        })
    return pd.DataFrame(out)


# ─────────────────────────── 写盘 ───────────────────────────

def _attr_fill(v):
    s = str(v or "")
    if "未收录" in s:
        return UNRES_FILL
    if s.startswith("非本月"):
        return HIST_FILL
    return None


def write_sheet(wb, name, df, freeze="A2", widths=None, stripe_col=None,
                mark_col="工单归属", role_col="组内角色"):
    if name in wb.sheetnames:
        del wb[name]
    ws = wb.create_sheet(name)
    for j, col in enumerate(df.columns, 1):
        c = ws.cell(row=1, column=j, value=col)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")
    cols = list(df.columns)
    i_p = cols.index("优先级") + 1 if "优先级" in cols else None
    i_g = cols.index(stripe_col) + 1 if stripe_col and stripe_col in cols else None
    i_m = cols.index(mark_col) + 1 if mark_col in cols else None
    i_r = cols.index(role_col) + 1 if role_col in cols else None
    fills = {}
    seen = []
    for i, (_, row) in enumerate(df.iterrows(), 2):
        for j, col in enumerate(cols, 1):
            v = row[col]
            cell = ws.cell(row=i, column=j, value=None if pd.isna(v) else v)
            # 编号类字段锁定文本格式，避免 Excel/读表工具把 14 位编号当数字
            if "编号" in col or "工单" in col:
                cell.number_format = "@"
        if i_p and row["优先级"] == "高":
            ws.cell(row=i, column=i_p).font = HIGH_FONT
        if i_g and row.get("组内条数", 1) and row["组内条数"] >= 2:
            gid = row[stripe_col]
            if gid not in fills:
                fills[gid] = GROUP_FILLS[len(seen) % 2]
                seen.append(gid)
            fill = fills[gid]
            for j in range(1, len(cols) + 1):
                ws.cell(row=i, column=j).fill = fill
            ws.cell(row=i, column=i_g).font = Font(bold=True)
        # 本月未判重复的同组工单（仅比对）：色块覆盖组斑马底纹
        if i_r:
            _rs = str(row.get(role_col, ""))
            _f = (PRESERVE_FILL, PRESERVE_FONT) if "保留件·未判重复" in _rs else (
                 (OTHER_FILL, OTHER_FONT) if "同组其他·未判重复" in _rs else (None, None))
            if _f[0] is not None:
                for j in range(1, len(cols) + 1):
                    ws.cell(row=i, column=j).fill = _f[0]
                ws.cell(row=i, column=i_r).font = _f[1]
                if i_m:
                    ws.cell(row=i, column=i_m).font = _f[1]
        # 表外历史/未收录工单：色块覆盖组斑马底纹
        if i_m:
            fv = _attr_fill(row[mark_col])
            if fv is not None:
                for j in range(1, len(cols) + 1):
                    ws.cell(row=i, column=j).fill = fv
                ws.cell(row=i, column=i_m).font = (Font(color="6B7280", bold=True)
                                                   if fv is UNRES_FILL else HIST_FONT)
                if i_r:
                    ws.cell(row=i, column=i_r).font = (Font(color="6B7280")
                                                       if fv is UNRES_FILL else HIST_FONT)
    ws.freeze_panes = freeze
    ws.auto_filter.ref = f"A1:{get_column_letter(len(df.columns))}{len(df) + 1}"
    for j, col in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(j)].width = (widths or {}).get(col, 14)
    return ws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--sheet", default="sheet1")
    ap.add_argument("--strip-quote", action="store_true",
                    help="按剥离引用块口径出清单（默认原样口径）")
    ap.add_argument("--out", default=None, help="另存路径（默认就地写回）")
    ap.add_argument("--hist-pkl", default=HIST_PKL, help="表外首单反查用的工单主库")
    ap.add_argument("--no-history", action="store_true", help="不补入表外历史工单")
    args = ap.parse_args()

    res = analyze_external(args.xlsx, args.sheet, strip_quote=args.strip_quote)
    d0 = res["_d"]
    cur_month = d0["t"].dt.strftime("%Y-%m").mode()[0]
    db = None if args.no_history else load_history_db(args.hist_pkl)
    get_rows = None if args.no_history else make_norm_indexer(db)

    rows_g, assign = build_groups(res, db=db, cur_month=cur_month, get_rows=get_rows)
    df = build_rows(res, rows_g, cur_month)
    nq = int(d0["content"].str.contains(QUOTED_BLOCK_RE, na=False).sum())

    # 系统标记「重复来电」：按 S2 同口径统计（正文段＝剥离引用块后），
    # 供复核结论表展示「有多少条是靠系统标记判出来的」；数值由 build_rows 落回 res
    sys_hit = res.get("_sys_hit") or set()
    n_sys, n_sys_dup = len(sys_hit), len(sys_hit & res["_sets"]["union"])
    n_sys_raw = int(d0["content"].fillna("").astype(str)
                    .str.contains(D.S2_SYS_RE, regex=True, na=False).sum())

    # ── 表外溯源统计 ──
    n_grp_ext = sum(1 for r in rows_g if r["ext_refs"])
    n_grp_ext_multi = sum(1 for r in rows_g if r["ext_refs"] and r["size"] > 1)
    n_grp_text = sum(1 for r in rows_g if r.get("text_refs"))
    n_text_oid = len({x for r in rows_g for x in (r.get("text_refs") or set())})
    hist_all = [h for r in rows_g for h in r.get("hist") or []]
    unres_all = [u for r in rows_g for u in r.get("unres") or []]
    n_hist_row = len(hist_all) + len(unres_all)
    n_hist_oid = len({h["oid"] for h in hist_all} | {u["oid"] for u in unres_all})
    n_hist_tab = int(df["工单归属"].str.contains("非本月|未收录").sum())
    n_keep_row = int((df["组内角色"] == "保留件·未判重复").sum())
    n_other_row = int((df["组内角色"] == "同组其他·未判重复").sum())
    n_month_row = int(df["工单归属"].str.startswith(f"本月（{cur_month}）").sum())
    n_dup_row = n_month_row - n_keep_row - n_other_row
    mo = Counter(f"{h['t']:%Y-%m}" for h in hist_all if pd.notna(h["t"]))
    mo_txt = " / ".join(f"{k}:{v} 条" for k, v in sorted(mo.items(), reverse=True))
    earliest = min((h["t"] for h in hist_all if pd.notna(h["t"])), default=pd.NaT)

    # ── 复核结论表 ──
    strip_res = analyze_external(args.xlsx, args.sheet, strip_quote=True)
    size_dist = Counter(r["size"] for r in rows_g)
    dist_txt = " / ".join(f"{k}条:{v}组" for k, v in sorted(size_dist.items()))
    n_multi = sum(v for k, v in size_dist.items() if k >= 2)
    marks = [
        ("复核对象", os.path.basename(args.xlsx)),
        ("工单总条数", res["total"]),
        ("判定重复工单数", res["total_dup"]),
        ("重复率", f"{res['dup_rate']}%"),
        ("　高优先级", res["high"]),
        ("　中优先级", res["mid"]),
        ("策略一 S1 完全重复", f"{res['s1']} 条 / {res['s1_groups']} 组"),
        ("策略二 S2 催办重发", f"{res['s2']} 条"),
        ("　其中系统标记「重复来电」", f"{n_sys_raw} 条含该词 → {n_sys} 条位于本单正文段"
                                     f"（其余 {n_sys_raw - n_sys} 条仅在转载引用块内，不计）；"
                                     f"{n_sys_dup} 条并入重复判定"),
        ("策略三 S3 同小区同类高频", f"{res['s3']} 条 / {res['s3_groups']} 组"),
        ("策略四 S4 文本相似", f"{res['s4_orders']} 条 / {res['s4_pairs']} 对"),
        ("", ""),
        ("【去重清单构成】", "工单级明细，逐行回答「这条与哪条重复」"),
        ("　本月被判重复", f"{n_dup_row} 行（复核对象）"),
        ("　本月保留件·未判重复", f"{n_keep_row} 行（浅绿底，本组合并归集对象，仅作比对）"),
        ("　同组其他·未判重复", f"{n_other_row} 行（浅蓝底，同组更晚的未判重复工单）"),
        ("　表外历史溯源", f"{n_hist_row} 行（琥珀／灰底，不纳入本月判定）"),
        ("　清单合计", f"{len(df)} 行"),
        ("重复对象列", "逐行写明本行与组内哪条构成重复，即「建议合并至该件」；"
                      "表外行则写明被哪笔本月工单引用"),
        ("", ""),
        ("【重复组聚类】", "把互相构成重复关系的工单聚为同一「组」"),
        ("重复组数", f"{len(rows_g)} 组（其中 ≥2 条的组 {n_multi} 组）"),
        ("组规模分布", dist_txt),
        ("组内关系（并集）", "S1完全一致 / S3同类高频 / S4文本相似 / 引用首单"),
        ("组号怎么读", "组号相同＝同一件重复投诉；组内按受理时间排序，"
                       "最早的为案件首单（若首单不在本月，即为琥珀色行）"),
        ("组内角色", "表外首单／表外前序（琥珀·灰色块）／保留件·未判重复（浅绿，仅比对）／"
                     "同组其他·未判重复（浅蓝，仅比对）／保留件（本月最早）／重复件／仅有此单"),
        ("组内条数口径", "＝本月表内该组工单数（含保留件与未判重复的同簇工单）；"
                        "表外历史工单另计于「表外历史条数」列"),
        ("组内序号口径", "该工单在整条案件时间轴上的位次（含未判重复的同簇工单与表外工单），"
                        "故 max(组内序号) ＝ 组内条数 ＋ 表外历史条数"),
        ("单条组（组内条数=1）", "只命中催办/重复用语，无需同组配对（S1/S3/S4 都要求配对工单）；"
                                "其首件不在本表（复核表只有当月复核单），已从工单库按「引用编号」"
                                "或「引用块正文比对」反查补入清单；两者都无着落的才会只剩 1 行"),
        ("", ""),
        ("【表外首单溯源】", "本月工单正文引用块指向更早首单时，自动回溯补入清单"),
        ("含表外引用的重复组", f"{n_grp_ext} 组（其中组内 ≥2 条 {n_grp_ext_multi} 组）"),
        ("补入清单的历史工单", f"{n_hist_row} 行 / {n_hist_oid} 个编号"
                               f"（清单表中合计 {n_hist_tab} 行非本月）"),
        ("　已定位", f"{len(hist_all)} 行（受理时间取工单库实际值）"),
        ("　未收录", f"{len(unres_all)} 行（受理时间按编号前 8 位推定，已标注）"),
        ("　引用块文本比对补入", f"{n_grp_text} 组 / {n_text_oid} 个编号"
                              "（引用块编号位写坏或缺「号」字时，改用块内正文片段"
                              "回主库比对定位，限同小区、受理时间更早，取最近一笔）"),
        ("历史首单月份分布", mo_txt or "—"),
        ("最早历史首单", f"{earliest:%Y-%m-%d}" if pd.notna(earliest) else "—"),
        ("溯源层数上限", f"≤{MAX_DEPTH} 层（首单 → 前序工单，单组最多 {MAX_HIST} 行）"),
        ("溯源层级含义", "「表外首单」＝被本月工单直接引用；「表外前序·N 级」＝被上一级表外工单"
                        "引用而来，级次越高时间越早"),
        ("色块图例", "浅绿底＝本月「保留件·未判重复」（本组合并归集对象，仅比对）；"
                     "浅蓝底＝「同组其他·未判重复」；"
                     "琥珀底＝非本月历史工单（仅溯源，不纳入本月重复判定）；"
                     "灰底＝表外未收录；同组同底色＝同一件重复投诉"),
        ("", ""),
        ("【口径对照】剥离引用块后", f"{strip_res['total_dup']} 条 / {strip_res['dup_rate']}%"),
        ("含系统引用块的工单", f"{nq} 条（{nq/res['total']*100:.1f}%）"),
        ("", ""),
        ("判定规则", "S1 同小区+内容完全一致（组内保留最早1条）"),
        ("", "S2 内容命中「催单/催办/重新交办/相同事项」，或「反复+来电/催/投诉/反映」搭配，"
             "或本单正文段含系统标记「重复来电」（匹配前先剥离系统引用块）"),
        ("", "S3 同小区+同十四类 ≥3 条（组内保留1条）"),
        ("", "S4 同小区内 jieba+TF-IDF 余弦 ≥0.6 且受理时间间隔 ≤90 天"),
        ("", "合并：四策略取并集；高 = S1∪S2∪S3频次≥4组的超额工单"),
        ("分词/向量化", "jieba 0.42.1 + numpy 版 TF-IDF（与历史月度同口径）"),
        ("口径来源", "scripts/dedup_monthly.py（《投诉去重识别方法论说明》四重策略）"),
        ("表外溯源来源", "data/merged_cleaned.pkl（2024-01～2026-08，66,812 条工单主库）"),
    ]
    concl = pd.DataFrame(marks, columns=["指标", "数值 / 说明"])
    # 街道分布沿用「本月被判重复工单」口径：保留件行的工单归属带「·保留件」后缀，
    # 用精确匹配即自然排除，保证与既有报告的同名指标口径一致
    st = df[df["工单归属"] == f"本月（{cur_month}）"].groupby("街道").size() \
        .sort_values(ascending=False)
    blank = pd.DataFrame([("", "")], columns=["指标", "数值 / 说明"])
    dist = pd.DataFrame(
        [("【重复工单街道分布】", "仅统计本月被判重复的工单（不含保留件与表外溯源行）"),]
        + [(k, int(v)) for k, v in st.items()],
        columns=["指标", "数值 / 说明"])
    concl = pd.concat([concl, blank, dist], ignore_index=True)

    # ── 重复组明细表：一组一行，直接看「哪几条是同一件投诉」──
    gdf = build_group_sheet(rows_g)

    wb = load_workbook(args.xlsx)
    write_sheet(wb, "复核结论", concl, widths={"指标": 30, "数值 / 说明": 62})
    write_sheet(wb, "去重清单", df, stripe_col="组号", widths={
        "组号": 8, "组内条数": 9, "表外历史条数": 11, "组内序号": 9, "组内角色": 20,
        "工单归属": 20, "引用来源": 20, "工单编号": 20, "重复对象": 46,
        "受理时间": 17, "小区": 20, "街道": 14, "物业公司": 24, "类别（十四类）": 15,
        "建议保留工单": 24, "保留件受理时间": 17, "间隔天数": 9, "组内关系": 24,
        "命中策略": 12, "同类频次": 9, "文本相似度": 10, "优先级": 7,
        "诉求摘要": 46, "保留件诉求摘要": 46, "复核建议": 26})
    write_sheet(wb, "重复组明细", gdf, stripe_col="组号", mark_col=None,
                widths={
        "组号": 8, "组内条数": 9, "重复条数": 9, "表外历史条数": 11, "组内关系": 24,
        "小区": 20, "街道": 14, "类别（十四类）": 15, "物业公司": 24,
        "建议保留工单": 30, "保留件受理时间": 17, "保留件诉求摘要": 46,
        "表外首单编号": 20, "表外首单受理时间": 17, "表外工单摘要": 60,
        "重复工单编号": 40, "同组其他编号（未判重复）": 26, "组内优先级": 10})

    out = args.out or args.xlsx
    wb.save(out)
    print(f"✔ 已写入「复核结论」+「去重清单」({len(df)} 行)+「重复组明细」({len(gdf)} 行) → {out}")
    print(f"  工作表: {wb.sheetnames}")
    print(f"  重复 {res['total_dup']}/{res['total']} = {res['dup_rate']}% | "
          f"高 {res['high']} / 中 {res['mid']}")
    print(f"  重复组 {len(rows_g)} 组（≥2 条 {n_multi} 组）| 组规模 {dist_txt}")
    print(f"  清单构成: 本月被判重复 {n_dup_row} 行 + 保留件·未判重复 {n_keep_row} 行"
          f" + 同组其他·未判重复 {n_other_row} 行 + 表外溯源 {n_hist_row} 行 = {len(df)} 行")
    print(f"  表外溯源: {n_grp_ext} 组含表外引用 → 补入 {n_hist_row} 行"
          f"（已定位 {len(hist_all)} / 未收录 {len(unres_all)}，{n_hist_oid} 个编号）")
    print(f"  文本比对兜底: {n_grp_text} 组 / {n_text_oid} 个编号")
    print(f"  历史首单月份: {mo_txt} | 最早 {earliest:%Y-%m-%d}"
          if pd.notna(earliest) else "  历史首单月份: —")
    print(f"  街道分布 Top6: {dict(list(st.items())[:6])}")


if __name__ == "__main__":
    main()
