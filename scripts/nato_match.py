# -*- coding: utf-8 -*-
"""纳统小区匹配（唯一口径源）
=============================

项目组 2026-09-28 决策：
  · 所有风险评估类报告（高风险小区预警、治理效果追踪）**按更新后的纳统小区
    （《纳统小区 (2026 更新版).xls》）统计，不在小区列表中的小区不做统计**。
  · 投诉数据仍按**热线数据表**口径统计（本模块只负责「小区范围」收窄，不碰投诉口径）。

本模块职责
----------
提供「热线工单里的小区名 → 纳统小区（2026 更新版）」的映射，供
`risk_scoring.py` / `governance_tracking.py` 等风险评估脚本统一调用。

匹配规则
--------
与项目既有匹配表（`热线与纳统小区全量匹配表.xlsx`）保持一致：
**主名 / 别名 精确匹配**（规范化后全等）。

规范化：去除首尾空白与内部空白、全角括号→半角、全角数字→半角。
（原匹配表 989/1374 命中率即由此规则得出，本模块须可复现该结果。）

用法
----
    import nato_match as NM
    nato = NM.load_nato()                 # 新版纳统小区（993 个）
    mp   = NM.build_map(hotline_names)    # 热线名 → nato_id / nato_name
    keep = NM.filter_communities(df, col="community_name")   # 只留纳统名单内
"""
from __future__ import annotations

import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NATO_XLS_NEW = os.path.join(ROOT, "徐汇各科室业务数据", "纳统小区 (2026 更新版).xls")
NATO_XLS_OLD = os.path.join(ROOT, "徐汇各科室业务数据", "纳统小区.xls")

# 新版纳统档案的列名（xlrd 读 .xls）
_COL_ID = "小区sectId"
_COL_NAME = "小区名称"
_COL_ALIAS = "小区别名"
_COL_STREET = "街道"
_COL_HOUSEHOLDS = "总户数"

# ─────────────────────────────────────────────────────────────
# 2026 更新版相对旧版的变动（经逐字段比对确认，2026-09-28）
#   全库仅 3 处：①「尚海湾二期」+「尚海湾豪庭」合并为「尚海湾豪庭小区（北区）」
#   （sectId 2208301215093189 复用，户数 2049+1595=3644 与新版一致）
#   ② 新增别名「宛南五村」 ③ 户数「广元路139弄」6→12
# 热线工单里仍会出现旧名，故按 sectId 补挂历史名称作为匹配键。
# ─────────────────────────────────────────────────────────────
_MERGED_INTO_2026 = {
    # 新版小区名（须与档案完全一致）: [该小区在 2026 版之前的曾用名/别名]
    "尚海湾豪庭小区（北区）": ["尚海湾二期", "尚海湾豪庭", "尚海湾豪庭（北区）"],
}


def _merged_extra_keys() -> dict:
    """把「曾用名」挂到新版档案行的匹配键上。返回 {规范化的新版名: [额外键]}"""
    return {norm(k): [norm(x) for x in v] for k, v in _MERGED_INTO_2026.items()}


def norm(s) -> str:
    """小区名规范化：去空白、全角括号/数字转半角、去除用于分隔的标点差异。"""
    if s is None:
        return ""
    t = str(s)
    if t.lower() in ("nan", "none"):
        return ""
    # 全角 → 半角（括号、数字、字母、空格）
    t = t.replace("（", "(").replace("）", ")")
    t = t.replace("　", " ")
    t = re.sub(r"[\uFF10-\uFF19]", lambda m: chr(ord(m.group()) - 0xFEE0), t)
    t = re.sub(r"[\uFF21-\uFF3A\uFF41-\uFF5A]", lambda m: chr(ord(m.group()) - 0xFEE0), t)
    t = re.sub(r"\s+", "", t)
    return t.strip()


def load_nato(version: str = "new") -> pd.DataFrame:
    """读取纳统小区档案。

    返回列：nato_id / nato_name / alias / street / households / keys（规范化匹配键集合）
    """
    path = NATO_XLS_NEW if version == "new" else NATO_XLS_OLD
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    import xlrd

    wb = xlrd.open_workbook(path)
    sh = wb.sheet_by_index(0)
    hdr = [str(sh.cell_value(0, c)).strip() for c in range(sh.ncols)]

    def col(name):
        return hdr.index(name) if name in hdr else None

    ci, ni, ai = col(_COL_ID), col(_COL_NAME), col(_COL_ALIAS)
    si, hi = col(_COL_STREET), col(_COL_HOUSEHOLDS)

    rows = []
    for r in range(1, sh.nrows):
        def cell(idx):
            if idx is None:
                return ""
            v = sh.cell_value(r, idx)
            if isinstance(v, float) and v == int(v):
                v = int(v)
            return str(v).strip()

        sid = cell(ci)
        name = cell(ni)
        if not name:
            continue
        alias = cell(ai)
        rows.append({
            "nato_id": sid,
            "nato_name": name,
            "alias": alias,
            "street": cell(si),
            "households": pd.to_numeric(cell(hi), errors="coerce") if hi is not None else None,
        })
    df = pd.DataFrame(rows)
    # 匹配键：主名 + 别名（拆多个别名，常见分隔符 / 、 , ; 空)+ 2026 版曾用名
    extra = _merged_extra_keys()
    keys = []
    for _, r in df.iterrows():
        ks = {norm(r["nato_name"])}
        for part in re.split(r"[/、,;；\s]+", str(r["alias"])):
            if norm(part):
                ks.add(norm(part))
        ks.update(extra.get(norm(r["nato_name"]), []))
        ks.discard("")
        keys.append(ks)
    df["keys"] = keys
    return df


def build_map(names, version: str = "new", streets=None) -> pd.DataFrame:
    """把热线小区名映射到纳统小区。

    names    : 热线侧小区名序列
    streets  : 可选，与 names 等长的街道序列（或 dict 名→街道）；用于同名小区消歧。
               传入时优先取「同街道」的候选，否则取档案顺序第一个。

    返回列：hotline_name / nato_id / nato_name / nato_street / matched / n_hits
    一个热线名若同时命中多个纳统小区，取「主名精确命中」优先。
    """
    nato = load_nato(version)
    key2rows: dict[str, list] = {}
    for i, r in nato.iterrows():
        for k in r["keys"]:
            key2rows.setdefault(k, []).append(i)

    names = list(names)
    if isinstance(streets, dict):
        st_list = [streets.get(nm, "") for nm in names]
    elif streets is not None:
        st_list = list(streets)
    else:
        st_list = [""] * len(names)

    out = []
    for pos, nm in enumerate(names):
        st = str(st_list[pos] or "").replace("街道", "").replace("镇", "").strip()
        k = norm(nm)
        hits = key2rows.get(k, [])
        if hits:
            exact = [i for i in hits if norm(nato.at[i, "nato_name"]) == k]
            pool = exact or hits
            if st and len(pool) > 1:      # 同名小区：按街道消歧
                same = [i for i in pool
                        if str(nato.at[i, "street"]).replace("街道", "").replace("镇", "").strip() == st]
                pool = same or pool
            i = pool[0]
            out.append({"hotline_name": nm, "nato_id": nato.at[i, "nato_id"],
                        "nato_name": nato.at[i, "nato_name"],
                        "nato_street": nato.at[i, "street"], "matched": True,
                        "n_hits": len(hits)})
        else:
            out.append({"hotline_name": nm, "nato_id": "", "nato_name": "",
                        "nato_street": "", "matched": False, "n_hits": 0})
    return pd.DataFrame(out)


def filter_communities(df: pd.DataFrame, col: str = "community_name",
                       version: str = "new", verbose: bool = False):
    """只保留能匹配到纳统名单的记录，并返回 (过滤后 df, 统计 dict)。

    注意：本函数只做「记录级」过滤（丢掉不在名单的小区），**不做聚合**。
    需要「按纳统小区统计」时请另用 `aggregate_key()` 生成的键聚合。
    """
    names = sorted(set(df[col].fillna("").astype(str).str.strip()) - {"", "无", "nan", "None"})
    mp = build_map(names, version)
    ok = set(mp.loc[mp["matched"], "hotline_name"])
    keep = df[df[col].fillna("").astype(str).str.strip().isin(ok)]
    stat = {
        "hotline_communities": len(names),
        "matched_communities": int(mp["matched"].sum()),
        "unmatched_communities": int((~mp["matched"]).sum()),
        "records_before": len(df),
        "records_after": len(keep),
        "records_dropped": len(df) - len(keep),
    }
    if verbose:
        print(f"[纳统过滤] 热线小区 {stat['hotline_communities']} → 命中 {stat['matched_communities']}"
              f"｜工单 {stat['records_before']:,} → {stat['records_after']:,}"
              f"（剔除 {stat['records_dropped']:,} 条，{stat['records_dropped']/max(1,stat['records_before'])*100:.1f}%）")
    return keep, stat, mp


def aggregate_key(df: pd.DataFrame, col: str = "community_name",
                  mp: pd.DataFrame | None = None, version: str = "new",
                  keep_id: bool = True) -> pd.DataFrame:
    """给 df 增加 `nato_community` 列（= 所属纳统小区名），用于按纳统小区聚合。

    - 命中多对一时，别名归并到主名小区
    - 未命中的记录 `nato_community` 为空 → 由调用方决定是否丢弃
    - keep_id=True 时同时增加 `nato_id`
    """
    if mp is None:
        names = sorted(set(df[col].fillna("").astype(str).str.strip()) - {"", "无", "nan", "None"})
        mp = build_map(names, version)
    m_name = dict(zip(mp["hotline_name"], mp["nato_name"]))
    df = df.copy()
    stripped = df[col].fillna("").astype(str).str.strip()
    df["nato_community"] = stripped.map(m_name).fillna("")
    if keep_id:
        m_id = dict(zip(mp["hotline_name"], mp["nato_id"]))
        df["nato_id"] = stripped.map(m_id).fillna("")
    return df


if __name__ == "__main__":
    nato = load_nato()
    print(f"纳统小区（2026 更新版）: {len(nato)} 个｜街道 {nato['street'].nunique()} 个")

    p = pd.read_pickle(os.path.join(ROOT, "data", "merged_cleaned.pkl"))
    names = sorted(set(p["community_name"].fillna("").astype(str).str.strip()) - {"", "无", "nan", "None"})
    mp = build_map(names)
    print(f"热线小区名 {len(names)} 个 → 命中 {int(mp['matched'].sum())}"
          f"｜未命中 {int((~mp['matched']).sum())}")
    multi = mp[mp["n_hits"] > 1]
    if len(multi):
        print(f"⚠️ 一名多小区（{len(multi)} 个）:")
        print(multi[["hotline_name", "nato_name", "nato_street", "n_hits"]].to_string(index=False))
