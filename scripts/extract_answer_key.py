#!/usr/bin/env python3
"""Extract the hidden teacher reference answer (D/DD/T/G) from the docx text dump.

Why: the scoring module needs a machine-readable reference answer. It must never be
hand-copied — medical content has to trace back to the hospital's own words, verbatim
(see docs/scoring-system-design.md §4). So we parse the docx, we do not rewrite it.

Source block: each case's A2 page, after the marker line `[21] 教师参考草案（隐藏）`:

    D01 诊断 36深龋，36可复性牙髓炎
    D02 理由 短暂刺激痛且无自发、夜间痛，冷测可恢复，叩诊阴性，配合深龋影；…
    DD01 症状性不可复性牙髓炎 本例缺少持续冷痛、自发和夜间痛；…
    T01 近期 …            T02 确定性/条件性处理 …     T03 复评维护 …
    G01 病情与计划解释 …   G02 注意与求助 …
    医学依据 K01、K02、K03（全册末尾列出）

Format is machine-regular (verified across all 30 cases on 2026-10-12): the label token
after the ID never contains a space, so `ID <label> <content>` splits cleanly.

Input : data/raw/_docx.txt
Output: data/staging/<case>.answer.new.json   (every case in the docx)
        data/tests/answer_key_gaps.md         (anomalies, for the hospital)

Never silently drops a line: anything that does not parse is reported, not skipped
(project rule: failures must look like failures).

Usage:
    python scripts/extract_answer_key.py
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCX_TEXT = ROOT / "data" / "raw" / "_docx.txt"
STAGING_DIR = ROOT / "data" / "staging"
GAP_REPORT = ROOT / "data" / "tests" / "answer_key_gaps.md"

HIDDEN_MARKER = "教师参考草案（隐藏）"
SECTION = re.compile(r"^\[\d+\]\s+([A-Z]{2}\d{2})\s+(A\d|B\d)\s")

# Order matters only for readability: D vs DD cannot collide (`\d` never matches `D`).
ENTRY = re.compile(r"^(D\d{2}|DD\d{2}|T\d{2}|G\d{2})\s+(\S+)\s+(.+)$")
BASIS = re.compile(r"^医学依据\s*(.+)$")

# 固定槽位 → 输出结构。医院在 30 例里用同一套编号。
DIAGNOSIS, DIAG_REASON = "D01", "D02"
PLAN_SLOTS = {"T01": "immediate", "T02": "definitive", "T03": "review"}
COMM_SLOTS = {"G01": "explain", "G02": "warn"}
PLAN_LABELS = {"immediate": "近期处理", "definitive": "确定性/条件性处理", "review": "复评维护"}
COMM_LABELS = {"explain": "病情与计划解释", "warn": "注意与求助"}

# 反推的五项答卷（2026-10-12 定），把"学员填什么"直接映射到参考答案 ID。
# 用机器可读的方式把这份对应关系钉在数据里，避免以后靠记忆。
ANSWER_SHEET = {
    "diagnosis": DIAGNOSIS,
    "reason": DIAG_REASON,
    "differential": "DD*",
    "immediate_plan": "T01",
    "staged_plan": "T02+T03",
}


def parse(lines: list[str]) -> tuple[dict[str, dict], list[dict]]:
    """Return ({case_id: answer}, [anomaly, …]) parsed from the docx text lines."""
    cases: dict[str, dict] = {}
    anomalies: list[dict] = []

    current_case: str | None = None
    in_hidden = False
    entries: list[dict] = []
    basis_raw = ""
    unparsed: list[str] = []

    def flush() -> None:
        """Close the hidden block in progress and structure it."""
        nonlocal entries, basis_raw, unparsed
        if current_case is None or not (entries or basis_raw or unparsed):
            entries, basis_raw, unparsed = [], "", []
            return

        by_id = {e["id"]: e for e in entries}

        # 重复 ID 是数据错误，必须报出来
        for eid in {e["id"] for e in entries}:
            if sum(1 for e in entries if e["id"] == eid) > 1:
                anomalies.append({"case": current_case, "kind": "duplicate_id", "detail": eid})

        out: dict = {
            "case_id": current_case,
            "schema_version": "1.0",
            "source": {
                "doc": "Oral_Agent_SP_Development_Cases30_v2.docx",
                "page": "A2 教师参考草案（隐藏）",
            },
            "diagnosis": _slot(by_id, DIAGNOSIS, "诊断"),
            "diagnosis_reason": _slot(by_id, DIAG_REASON, "理由"),
            "differentials": [
                {"id": e["id"], "label": e["label"], "reason": e["content"]}
                for e in entries
                if e["id"].startswith("DD")
            ],
            "plan": {
                key: _slot(by_id, tid, PLAN_LABELS[key])
                for tid, key in PLAN_SLOTS.items()
            },
            "communication_reference": {
                key: _slot(by_id, gid, COMM_LABELS[key])
                for gid, key in COMM_SLOTS.items()
            },
            # 直接抓 K## 编号，别按分隔符切：原文里混着「及」「；补充XXX《…》」「（全册末尾列出）」
            # 之类的非编号文字（如 "K01、K02、K03（全册末尾列出）"、"K17及ADA《Oral…》"）。
            "evidence_basis": re.findall(r"K\d{2}", basis_raw),
            "evidence_basis_raw": basis_raw,
            "answer_sheet": ANSWER_SHEET,
        }

        # ── 异常检测：缺槽位 / 缺鉴别 / 未解析行 ──────────────────────
        required = [DIAGNOSIS, DIAG_REASON, *PLAN_SLOTS, *COMM_SLOTS]
        for rid in required:
            if rid not in by_id:
                anomalies.append({"case": current_case, "kind": "missing_entry", "detail": rid})
        if not out["differentials"]:
            anomalies.append({"case": current_case, "kind": "no_differential", "detail": "缺少 DD*"})
        if not basis_raw:
            anomalies.append({"case": current_case, "kind": "missing_basis", "detail": "缺少「医学依据」行"})
        for line in unparsed:
            anomalies.append({"case": current_case, "kind": "unparsed_line", "detail": line})

        cases[current_case] = out
        entries, basis_raw, unparsed = [], "", []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        sec = SECTION.match(line)
        if sec:
            flush()
            in_hidden = False
            current_case = sec.group(1) if sec.group(2) == "A2" else None
            continue

        if HIDDEN_MARKER in line:
            in_hidden = True
            continue

        if not in_hidden or current_case is None:
            continue

        m = BASIS.match(line)
        if m:
            basis_raw = m.group(1).strip()
            continue

        m = ENTRY.match(line)
        if m:
            entries.append({"id": m.group(1), "label": m.group(2).strip(), "content": m.group(3).strip()})
        else:
            unparsed.append(line)

    flush()
    return cases, anomalies


def _slot(by_id: dict[str, dict], slot_id: str, fallback_label: str) -> dict:
    """Return {id,label,content}; a missing slot is explicit, never None-named."""
    e = by_id.get(slot_id)
    if e is None:
        return {"id": slot_id, "label": fallback_label, "content": None}
    return {"id": e["id"], "label": e["label"], "content": e["content"]}


def build_report(cases: dict[str, dict], anomalies: list[dict]) -> str:
    lines = [
        "# 参考答案（D/DD/T/G）提取异常清单",
        "",
        f"> 生成于 {date.today().isoformat()}。来源：`data/raw/_docx.txt` 的 A2「教师参考草案（隐藏）」块。",
        ">",
        "> 提取是**确定性解析**，不是 LLM 改写——医学内容必须逐字来自医院原文。",
        "> 凡是解析不出来或结构不全的，一律**报错而非静默跳过**。",
        "",
        "## 汇总",
        "",
        f"- 提取到 **{len(cases)}** 例的隐藏参考答案（docx 共 30 例）。",
        f"- 异常 **{len(anomalies)}** 条。",
        "",
    ]
    if anomalies:
        lines += ["| 病例 | 类型 | 详情 |", "|---|---|---|"]
        for a in anomalies:
            detail = a["detail"].replace("|", "\\|")
            lines.append(f"| {a['case']} | `{a['kind']}` | {detail} |")
        lines.append("")
    else:
        lines += ["无异常。", ""]

    lines += ["## 逐例槽位完整性", "", "| 病例 | D01 | D02 | DD 数 | T01 | T02 | T03 | G01 | G02 | 医学依据 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for cid, c in cases.items():
        have = lambda key: "✅" if c.get(key) and c[key].get("content") else "❌"
        lines.append(
            f"| {cid} | {have('diagnosis')} | {have('diagnosis_reason')} | {len(c['differentials'])} "
            f"| {have('plan')} | {'✅' if c['plan']['definitive']['content'] else '❌'} "
            f"| {'✅' if c['plan']['review']['content'] else '❌'} "
            f"| {'✅' if c['communication_reference']['explain']['content'] else '❌'} "
            f"| {'✅' if c['communication_reference']['warn']['content'] else '❌'} "
            f"| {'✅' if c['evidence_basis_raw'] else '❌'} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if not DOCX_TEXT.exists():
        print(f"Error: {DOCX_TEXT} not found")
        sys.exit(1)

    cases, anomalies = parse(DOCX_TEXT.read_text(encoding="utf-8").split("\n"))

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    GAP_REPORT.parent.mkdir(parents=True, exist_ok=True)
    GAP_REPORT.write_text(build_report(cases, anomalies), encoding="utf-8")

    for cid, data in cases.items():
        path = STAGING_DIR / f"{cid.lower()}.answer.new.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {len(cases)} files to {STAGING_DIR.relative_to(ROOT)}/ and {GAP_REPORT.relative_to(ROOT)}")
    if anomalies:
        print(f"  ⚠ {len(anomalies)} anomalies:")
        for a in anomalies:
            print(f"    - {a['case']} {a['kind']}: {a['detail'][:70]}")
    else:
        print("  no anomalies")


if __name__ == "__main__":
    main()
