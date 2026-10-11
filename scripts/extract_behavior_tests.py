#!/usr/bin/env python3
"""Extract B1/B2 behaviour tests from the hospital docx text dump into JSON.

The docx is the spec; this script turns it into data so tests are never
hand-copied (and can be re-extracted when all 30 cases are sliced).

Input : data/raw/_docx.txt          (text dump of Oral_Agent_SP_Development_Cases30_v2.docx)
Output: data/tests/behavior_tests.json

Each extracted test keeps the five authored fields verbatim:
    前情 setup / 发送 send / 预期 expect / 禁止 forbid / 依据 basis
`basis` is additionally normalised to an ID list (H01/P02/…) when it names IDs;
non-ID bases (权限/缺失规则, E01) are kept in `basis_raw` only.

Usage:
    python scripts/extract_behavior_tests.py            # the 5 sliced cases
    python scripts/extract_behavior_tests.py --all      # every case in the docx
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCX_TEXT = ROOT / "data" / "raw" / "_docx.txt"
OUT_PATH = ROOT / "data" / "tests" / "behavior_tests.json"

# 本阶段只切了这 5 例；--all 可扩展到 docx 里全部 30 例。
SLICED_CASES = ["EN01", "PE01", "PR01", "MU01", "SU01"]

CASE_HEADER = re.compile(r"^\[\d+\]\s+([A-Z]{2}\d{2})\s+([AB]\d)\s+(.+?)\s*$")
TEST_HEADER = re.compile(r"^\[\d+\]\s+(B\d{2})\s+(.+?)\s+\[(患者|检查模块)\]$")
# 标签后可能是空格（"前情 无"）或全角/半角冒号（"依据：H01"），两种都要吃掉
FIELD = re.compile(r"^(前情|发送|预期|禁止|依据)\s*[：:]?\s*(.*)$")

OBJECT_MAP = {"患者": "patient", "检查模块": "exam"}

# "依据：H01、H02  |  结果/错误证据：待运行记录" → "H01、H02"
BASIS_SPLIT = re.compile(r"\s*\|\s*")
ID_RE = re.compile(r"^[A-Z]\d{2}$")


def parse(lines: list[str], wanted: set[str]) -> dict:
    """Parse case blocks out of the docx text lines."""
    cases: dict[str, dict] = {}
    current_case: str | None = None
    current_test: dict | None = None
    current_field: str | None = None
    expect_title = False
    in_b_section = False

    def flush_test() -> None:
        """Close the test in progress and normalise its fields."""
        nonlocal current_test
        if current_test and current_case:
            raw = current_test.get("basis_raw", "").strip()
            # "H01、H02  |  结果/错误证据：待运行记录" → ID 列表
            ids = [p.strip() for p in re.split(r"[、,，]", raw.split("|")[0])] if raw else []
            current_test["basis"] = [i for i in ids if ID_RE.match(i)]
            current_test["basis_raw"] = raw
            for key in ("setup", "send", "expect", "forbid"):
                current_test[key] = current_test.get(key, "").strip()
            cases[current_case]["tests"].append(current_test)
        current_test = None
        current_field = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # A/B 区块边界：区块内最后一题（B06、B12）此前会被漏掉，所以任何区块头都要先收题。
        case_m = CASE_HEADER.match(line)
        if case_m:
            flush_test()
            case_id, section, _name = case_m.groups()
            if case_id in wanted and case_id not in cases:
                cases[case_id] = {"title": "", "tests": []}
            current_case = case_id if case_id in cases else None
            in_b_section = section in ("B1", "B2")
            expect_title = True
            continue

        # 紧跟区块头的第一行是中文标题（含诊断，仅作元数据，绝不进患者上下文）
        if expect_title:
            expect_title = False
            if current_case and not cases[current_case]["title"]:
                cases[current_case]["title"] = line
            continue

        if not in_b_section or not current_case:
            continue

        test_m = TEST_HEADER.match(line)
        if test_m:
            flush_test()
            test_id, name, obj = test_m.groups()
            current_test = {"id": test_id, "name": name.strip(), "object": OBJECT_MAP[obj]}
            continue

        field_m = FIELD.match(line)
        if field_m and current_test:
            field, value = field_m.groups()
            key = {"前情": "setup", "发送": "send", "预期": "expect",
                   "禁止": "forbid", "依据": "basis_raw"}[field]
            current_test[key] = value
            current_field = key
            continue

        # 折行的续行：接到上一个字段后面
        if current_test and current_field:
            current_test[current_field] = f"{current_test.get(current_field, '')} {line}".strip()

    flush_test()
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="extract every case, not just the sliced 5")
    args = parser.parse_args()

    if not DOCX_TEXT.exists():
        print(f"Error: {DOCX_TEXT} not found")
        sys.exit(1)

    lines = DOCX_TEXT.read_text(encoding="utf-8").split("\n")

    if args.all:
        wanted = {m.group(1) for m in (CASE_HEADER.match(l.strip()) for l in lines) if m}
    else:
        wanted = set(SLICED_CASES)

    cases = parse(lines, wanted)

    missing = wanted - set(cases)
    if missing:
        print(f"Warning: no B tests found for {sorted(missing)}")

    out = {
        "source": "data/raw/Oral_Agent_SP_Development_Cases30_v2.docx",
        "extracted_at": date.today().isoformat(),
        "note": "B1/B2 固定上下文测试。'basis' 是规范化后的 ID 列表，供断言使用；判定用 'expect'/'forbid' 原文。",
        "cases": cases,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    total = sum(len(c["tests"]) for c in cases.values())
    print(f"Wrote {OUT_PATH.relative_to(ROOT)}: {len(cases)} cases, {total} tests")
    for cid, c in cases.items():
        ids = " ".join(t["id"] for t in c["tests"])
        print(f"  {cid}: {len(c['tests'])} tests [{ids}]")


if __name__ == "__main__":
    main()
