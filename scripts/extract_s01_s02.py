#!/usr/bin/env python3
"""Extract the hospital's S01/S02 multi-turn scripts from the docx text dump.

These are the ONLY multi-turn specs the hospital gives (B01–B12 are each run in a
fresh session, so they can never catch a continuity bug). They were never run until
2026-10-12, when a manual pass found two spec violations — see
docs/simulation-quality-plan.md §1.

Source shape (B3 page of each case):

    [21] S01  常规路径
    01  患者｜请说说这次为什么来，哪里不舒服、多久了？  [H01]
    ...
    10  患者｜目前表现更支持牙髓能恢复；…  [P03]

The leading 患者｜/检查｜ is the **module under test**, not the speaker — step 12's
input is a sentence the *student* says. Getting this backwards is easy and changes
what the test means.

Input : data/raw/_docx.txt
Output: data/tests/s01_s02.json

Usage:
    python scripts/extract_s01_s02.py
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCX_TEXT = ROOT / "data" / "raw" / "_docx.txt"
OUT_PATH = ROOT / "data" / "tests" / "s01_s02.json"

SECTION = re.compile(r"^\[\d+\]\s+([A-Z]{2}\d{2})\s+(A\d|B\d)\s")
SCRIPT_HEAD = re.compile(r"^\[\d+\]\s+(S\d{2})\s+(.+?)\s*$")
STEP = re.compile(r"^(\d{2})\s+(患者|检查)｜\s*(.+?)\s+\[([^\]]+)\]\s*$")
ID_RE = re.compile(r"^[A-Z]{1,2}\d{2}$")
# 「依据」里不是 ID 的写法（权限/缺失规则 等）
RULE_HINT = re.compile(r"规则|权限|缺失|错误|安全")

OBJECT_MAP = {"患者": "patient", "检查": "exam"}


def parse_steps(text: str) -> list[dict]:
    """Parse one S-script body into steps.

    `basis` is the ID list when the 依据 names IDs; `is_rule` marks steps whose
    依据 is a rule ("权限/缺失规则") rather than a fact — those assert *withholding*.
    """
    steps = []
    for line in text:
        m = STEP.match(line)
        if not m:
            continue
        n, obj, send, basis_raw = m.groups()
        ids = [p.strip() for p in re.split(r"[、,，]", basis_raw) if ID_RE.match(p.strip())]
        steps.append({
            "n": n,
            "object": OBJECT_MAP[obj],
            "send": send.strip(),
            "basis": ids,
            "basis_raw": basis_raw.strip(),
            "is_rule": bool(RULE_HINT.search(basis_raw)),
        })
    return steps


def parse(lines: list[str]) -> dict[str, dict]:
    cases: dict[str, dict] = {}
    current_case: str | None = None
    in_b3 = False
    current_script: dict | None = None
    body: list[str] = []
    expect_title = False

    def flush_script() -> None:
        nonlocal current_script, body
        if current_script and current_case:
            steps = parse_steps(body)
            if steps:
                key = current_script["id"].lower()          # s01 / s02
                cases[current_case].setdefault("scripts", {})[key] = {
                    "name": current_script["name"],
                    "steps": steps,
                }
        current_script, body = None, []

    for raw in lines:
        line = raw.strip()
        sec = SECTION.match(line)
        if sec:
            flush_script()
            case_id, kind = sec.group(1), sec.group(2)
            in_b3 = kind == "B3"
            current_case = case_id if in_b3 else None
            if in_b3:
                cases.setdefault(case_id, {"title": "", "scripts": {}})
            expect_title = in_b3
            continue
        if not in_b3 or current_case is None:
            continue
        if expect_title:
            expect_title = False
            cases[current_case]["title"] = line
            continue

        head = SCRIPT_HEAD.match(line)
        if head:
            flush_script()
            current_script = {"id": head.group(1), "name": head.group(2).strip()}
            continue
        if current_script is not None:
            body.append(line)

    flush_script()
    return {cid: c for cid, c in cases.items() if c["scripts"]}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if not DOCX_TEXT.exists():
        print(f"Error: {DOCX_TEXT} not found")
        sys.exit(1)

    cases = parse(DOCX_TEXT.read_text(encoding="utf-8").split("\n"))
    out = {
        "source": "data/raw/Oral_Agent_SP_Development_Cases30_v2.docx",
        "extracted_at": date.today().isoformat(),
        "note": (
            "S01/S02 多轮脚本。步骤行首的「患者｜/检查｜」是**被测模块**，不是说话人。"
            "'basis' 是规范化后的 ID 列表；'is_rule' 为真表示该步依据是规则（权限/缺失），"
            "断言的是**不得给出资料**。"
        ),
        "cases": cases,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(len(s["steps"]) for c in cases.values() for s in c["scripts"].values())
    print(f"Wrote {OUT_PATH.relative_to(ROOT)}: {len(cases)} 例, {total} 步")
    for cid, c in cases.items():
        parts = [f"{k}={len(v['steps'])}步" for k, v in c["scripts"].items()]
        print(f"  {cid}: {' '.join(parts)}  「{c['title']}」")
    missing = [cid for cid, c in cases.items() if set(c["scripts"]) != {"s01", "s02"}]
    if missing:
        print(f"  ⚠ 脚本不齐（缺 S01 或 S02）：{missing}")


if __name__ == "__main__":
    main()
