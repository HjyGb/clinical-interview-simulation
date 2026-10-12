#!/usr/bin/env python3
"""Extract the scoring rubric (R01–R14) from the docx text dump.

Two sources, both machine-regular (verified across all 30 cases on 2026-10-12):

  1. Per-case A3 page「病例评分依据」— the case-specific **2-point anchor** for each item:

         R04 必要检查选择 | 申请与当前任务相符的关键项目：… | E01、E02、E03
         关键错误，单独复核 仅凭深龋就承诺必须根管或必然能保髓；以抗生素替代龋病处理

  2. Front-matter section「R14评分：共同1分／0分行为锚点」— the **1/0-point anchors shared**
     by all cases, plus the global rules (measured, not invented).

Input : data/raw/_docx.txt
Output: data/staging/<case>.rubric.new.json   (every case in the docx)
        data/scoring/rubric_common.json       (1/0 anchors + global rules)
        data/tests/rubric_gaps.md             (anomalies, for the hospital)

`evidence` / `judge` are NOT taken from the docx — the docx has no such fields. They are
derived from the design analysis in docs/scoring-system-design.md §1/§7 (which item reads
the conversation vs. the submitted report; which can be decided by pure code). They are
attached here so the whole 14-item framework is one machine-readable object.

Usage:
    python scripts/extract_rubric.py
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCX_TEXT = ROOT / "data" / "raw" / "_docx.txt"
STAGING_DIR = ROOT / "data" / "staging"
SCORING_DIR = ROOT / "data" / "scoring"
GAP_REPORT = ROOT / "data" / "tests" / "rubric_gaps.md"

SECTION = re.compile(r"^\[\d+\]\s+([A-Z]{2}\d{2})\s+(A\d|B\d)\s")
A3_HEADER = re.compile(r"^\[\d+\]\s+([A-Z]{2}\d{2})\s+A3\s+病例评分依据")
GLOBAL_HEADER = re.compile(r"^\[\d+\]\s+0*4\s+R14评分[:：]共同1分")
DRAFT_HEADER = re.compile(r"^\[\d+\]\s+R评分草案")
R_ROW = re.compile(r"^(R\d{2})\s+(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*$")
GLOBAL_ROW = re.compile(r"^(R\d{2})\s+(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*$")
CRITICAL = re.compile(r"^关键错误[，,]\s*单独复核\s*(.*)$")
DIFFICULTY = re.compile(r"开发集[｜|]\s*合成教学设定[｜|]\s*(.+?)\s*$")

# ── 设计分析得出的元数据（见 docs/scoring-system-design.md §1、§7）──────────
# evidence: 该条的证据主要来自 对话 / 最终作答
# judge   : code = 纯 Python 可判（读披露轨迹、检查申请轨迹）；llm = 需要语义判断
ITEM_META = {
    "R01": ("主诉与病程询问",           "dialogue", "code"),
    "R02": ("鉴别症状及危险征象询问",   "dialogue", "code"),
    "R03": ("诊疗史、用药和全身风险",   "dialogue", "code"),
    "R04": ("必要检查选择",             "dialogue", "code"),
    "R05": ("检查结果解释与边界",       "dialogue", "llm"),
    "R06": ("诊断与部位/确定性",        "report",   "llm"),
    "R07": ("诊断理由",                 "report",   "llm"),
    "R08": ("鉴别诊断分析",             "report",   "llm"),
    "R09": ("近期处理和安全优先",       "report",   "llm"),
    "R10": ("阶段计划与复评",           "report",   "llm"),
    "R11": ("病情及计划解释",           "dialogue", "llm"),
    "R12": ("注意事项与安全告知",       "dialogue", "llm"),
    "R13": ("担忧、偏好与理解核查",     "dialogue", "llm"),
    "R14": ("尊重表达与术语使用",       "dialogue", "llm"),
}
ALL_ITEMS = [f"R{i:02d}" for i in range(1, 15)]


def _refs(field: str) -> list[str]:
    return [p.strip() for p in re.split(r"[、,，]", field) if p.strip()]


def parse_cases(lines: list[str]) -> tuple[dict[str, dict], list[dict]]:
    """Parse every A3 page into a per-case rubric."""
    cases: dict[str, dict] = {}
    anomalies: list[dict] = []
    current: str | None = None
    body: list[str] = []

    def flush() -> None:
        if current is None or not body:
            return
        rows = {}
        critical_raw = ""
        extra, unparsed = [], []
        title, difficulty = "", ""
        seen_table = False
        for i, line in enumerate(body):
            if DIFFICULTY.match(line) and not difficulty:
                difficulty = DIFFICULTY.match(line).group(1)
                continue
            if i == 0 and not R_ROW.match(line):
                title = line            # A3 页第一行是中文标题（含诊断，仅元数据）
                continue
            m = CRITICAL.match(line)
            if m:
                critical_raw = m.group(1).strip()
                continue
            if R_ROW.match(line):
                seen_table = True
                rid, name, anchor, ref = R_ROW.match(line).groups()
                if rid in rows:
                    anomalies.append({"case": current, "kind": "duplicate_item", "detail": rid})
                rows[rid] = {"name": name.strip(), "anchor": anchor.strip(), "refs": _refs(ref)}
                continue
            if line.startswith("<TABLE>") or line.startswith("</TABLE>"):
                continue
            if "参照ID" in line and "达到2分" in line:
                continue
            if line.startswith("R14开发草案"):
                continue
            if line.startswith("评分证据须引用") or line.startswith("审核留白"):
                continue
            if seen_table:
                extra.append(line)      # 表后、留白前的补充规则（如 SU05 的安全优先例）
            else:
                unparsed.append(line)

        items = []
        for rid in ALL_ITEMS:
            meta = ITEM_META[rid]
            row = rows.get(rid)
            if row is None:
                anomalies.append({"case": current, "kind": "missing_item", "detail": rid})
                items.append({"id": rid, "name": meta[0], "anchor": None,
                              "refs": [], "evidence": meta[1], "judge": meta[2]})
                continue
            if row["name"] != meta[0]:
                anomalies.append({"case": current, "kind": "name_mismatch",
                                  "detail": f"{rid}: docx「{row['name']}」≠ 预期「{meta[0]}」"})
            items.append({"id": rid, "name": row["name"], "anchor": row["anchor"],
                          "refs": row["refs"], "evidence": meta[1], "judge": meta[2]})

        if len(rows) != 14:
            anomalies.append({"case": current, "kind": "item_count",
                              "detail": f"解析到 {len(rows)} 条 R 行（应为 14）"})
        if not critical_raw:
            anomalies.append({"case": current, "kind": "missing_critical", "detail": "缺少「关键错误」行"})
        for line in unparsed:
            anomalies.append({"case": current, "kind": "unparsed_line", "detail": line})

        cases[current] = {
            "case_id": current,
            "schema_version": "1.0",
            "source": {
                "doc": "Oral_Agent_SP_Development_Cases30_v2.docx",
                "page": "A3 病例评分依据",
            },
            "title": title,
            "title_note": "含诊断，仅作教师元数据；绝不进患者侧或学员界面",
            "difficulty": difficulty,
            "scale": {"per_item": 2, "items": 14, "raw_max": 28,
                      "note": "开发草案，无官方及格线；权重待专家讨论（医生批注）"},
            "items": items,
            # 拆成单条错误：医院用「；」分隔多个关键错误。原文另存，split 有误时可回退。
            "critical_errors": [e.strip() for e in re.split(r"[；;]", critical_raw) if e.strip()],
            "critical_errors_raw": critical_raw,
            "extra_rules": extra,
        }

    for raw in lines:
        line = raw.strip()
        m = A3_HEADER.match(line)
        if m:
            flush()
            current = m.group(1)
            body = []
            continue
        if SECTION.match(line) and not A3_HEADER.match(line):
            flush()
            current, body = None, []
            continue
        if current is not None and line:
            body.append(line)
    flush()
    return cases, anomalies


def parse_global(lines: list[str]) -> tuple[dict, list[dict]]:
    """Parse the front-matter 1/0-point anchors + global rules."""
    anomalies: list[dict] = []
    rows: list[dict] = []
    notes: list[str] = []
    special: list[str] = []

    mode = None
    found_draft = found_anchors = False
    for raw in lines:
        line = raw.strip()
        if GLOBAL_HEADER.match(line):
            mode = "anchors"
            found_anchors = True
            continue
        if DRAFT_HEADER.match(line):
            mode = "notes"
            found_draft = True
            continue
        if SECTION.match(line):
            mode = None
            continue
        if not line or mode is None:
            continue

        if mode == "notes":
            notes.append(line)
            continue

        m = GLOBAL_ROW.match(line)
        if m:
            rid, name, partial, zero = m.groups()
            rows.append({"id": rid, "name": name.strip(),
                         "partial_1": partial.strip(), "zero_0": zero.strip()})
            continue
        if line.startswith("<TABLE>") or line.startswith("</TABLE>"):
            continue
        if "1分：部分完成" in line:
            continue
        if line.startswith("每例A3页列完整"):
            continue
        if line.startswith("通用说明"):
            notes.append(line)
            continue
        if re.match(r"^SU\d{2}", line):
            special.append(line)          # 单例特殊规则（目前只有 SU05）
            continue
        anomalies.append({"case": "GLOBAL", "kind": "unparsed_line", "detail": line})

    ids = [r["id"] for r in rows]
    if ids != ALL_ITEMS:
        anomalies.append({"case": "GLOBAL", "kind": "item_count",
                          "detail": f"共同锚点解析到 {len(rows)} 条（应为 14），ID={ids}"})
    # 防"正则不匹配 → 静默跳过"：两个册前区块必须都找到，否则明说
    # （2026-10-12 就踩过一次：DRAFT_HEADER 多写一个 \d+ 导致整块规则被丢弃且不报错）
    if not found_draft:
        anomalies.append({"case": "GLOBAL", "kind": "section_missing",
                          "detail": "未找到册前「R评分草案」规则块"})
    if not found_anchors:
        anomalies.append({"case": "GLOBAL", "kind": "section_missing",
                          "detail": "未找到册前「R14评分：共同1分／0分行为锚点」块"})

    return {
        "schema_version": "1.0",
        "source": {
            "doc": "Oral_Agent_SP_Development_Cases30_v2.docx",
            "page": "册前「R14评分：共同1分／0分行为锚点」",
        },
        "scale": {"per_item": 2, "items": 14, "raw_max": 28,
                  "note": "开发草案，无官方及格线；权重待专家讨论"},
        "items": rows,
        "global_notes": notes,
        "special_case_rules": special,
        "item_meta": {rid: {"name": m[0], "evidence": m[1], "judge": m[2]}
                      for rid, m in ITEM_META.items()},
    }, anomalies


def build_report(cases: dict[str, dict], anomalies: list[dict]) -> str:
    lines = [
        "# R01–R14 评分锚点提取异常清单",
        "",
        f"> 生成于 {date.today().isoformat()}。来源：`data/raw/_docx.txt` 的 A3 页与册前共同锚点表。",
        ">",
        "> `evidence` / `judge` 两列不是文档里有的字段，是我们按设计分析附上的",
        "> （见 `docs/scoring-system-design.md`），用于区分「读对话 / 读作答」以及「代码判 / LLM 判」。",
        "",
        "## 汇总",
        "",
        f"- 提取到 **{len(cases)}** 例的逐例锚点（docx 共 30 例）。",
        f"- 异常 **{len(anomalies)}** 条。",
        "",
    ]
    if anomalies:
        lines += ["| 病例 | 类型 | 详情 |", "|---|---|---|"]
        for a in anomalies:
            lines.append(f"| {a['case']} | `{a['kind']}` | {a['detail'].replace('|', chr(92) + '|')} |")
        lines.append("")
    else:
        lines += ["无异常。", ""]

    lines += ["## 逐例锚点长度（字符数，供人工抽查）", "",
              "| 病例 | 难度 | 逐项锚点字符数 R01…R14 | 关键错误条数 |", "|---|---|---|---|"]
    for cid, c in cases.items():
        lens = " ".join(str(len(it["anchor"] or "")) for it in c["items"])
        lines.append(f"| {cid} | {c['difficulty']} | {lens} | {len(c['critical_errors'])} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if not DOCX_TEXT.exists():
        print(f"Error: {DOCX_TEXT} not found")
        sys.exit(1)

    lines = DOCX_TEXT.read_text(encoding="utf-8").split("\n")
    cases, anomalies = parse_cases(lines)
    common, common_anomalies = parse_global(lines)
    anomalies.extend(common_anomalies)

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    SCORING_DIR.mkdir(parents=True, exist_ok=True)
    GAP_REPORT.parent.mkdir(parents=True, exist_ok=True)

    for cid, data in cases.items():
        (STAGING_DIR / f"{cid.lower()}.rubric.new.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (SCORING_DIR / "rubric_common.json").write_text(
        json.dumps(common, ensure_ascii=False, indent=2), encoding="utf-8")
    GAP_REPORT.write_text(build_report(cases, anomalies), encoding="utf-8")

    print(f"Wrote {len(cases)} rubric files to {STAGING_DIR.relative_to(ROOT)}/, "
          f"{len(common['items'])} common anchors to {SCORING_DIR.relative_to(ROOT)}/rubric_common.json, "
          f"report to {GAP_REPORT.relative_to(ROOT)}")
    if anomalies:
        print(f"  ⚠ {len(anomalies)} anomalies:")
        for a in anomalies:
            print(f"    - {a['case']} {a['kind']}: {a['detail'][:70]}")
    else:
        print("  no anomalies")


if __name__ == "__main__":
    main()
