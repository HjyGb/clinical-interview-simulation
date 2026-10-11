#!/usr/bin/env python3
"""M2 spike — measure how well the lite model maps a student question to fact IDs.

Standalone: does not touch the backend, the DB, or the generation model.
Ground truth is the hospital docx's own B-test `依据` field, extracted into
data/tests/behavior_tests.json.

Scoring is recall-first: a missed fact means the patient cannot answer a
question it should be able to answer. Extra facts are reported separately —
the disclosure gate trims those downstream.

Usage:
    python scripts/spike_fact_selector.py                 # all 5 sliced cases
    python scripts/spike_fact_selector.py --cases EN01
    python scripts/spike_fact_selector.py --repeat 3
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from loguru import logger  # noqa: E402

from agent.fact_selector import ERROR_QUESTION_TYPE, OPEN_QUESTION_DEFAULT, select_facts  # noqa: E402
from app.config import settings  # noqa: E402

CASES_DIR = ROOT / "data" / "cases"
TESTS_PATH = ROOT / "data" / "tests" / "behavior_tests.json"
REPORT_DIR = ROOT / "data" / "tests"

# B06 的「依据」写的是"以本例 H01–H07 为准"，语义是"整个事实基础不得被推翻"，
# 而不是"这句话在问这几条事实"。用 ID 命中率评价它没有意义，单列出来看行为。
BASIS_SEMANTICS_EXCEPTION = {"B06"}

EMPTY_SETUP = "无；空会话。"


def build_history(case_data: dict, setup: str) -> str:
    """Reconstruct the conversation context a test implies.

    The opening statement is always the patient's first message; `前情` adds
    the prior exchange when the test has one.
    """
    lines = [f"患者：{case_data.get('opening', '')}"]
    if setup and setup.strip() != EMPTY_SETUP:
        lines.append(setup.replace(" → ", "\n"))
    return "\n".join(lines)


def effective_facts(result: dict) -> list[str]:
    """What the disclosure gate would actually allow this turn.

    Mirrors the planned gate: an open question with no explicit picks expands to
    the scripted H01–H04; meta allows nothing.
    """
    if result["question_type"] == "meta":
        return []
    if result["asked_facts"]:
        return list(result["asked_facts"])
    if result["question_type"] == "open":
        return list(OPEN_QUESTION_DEFAULT)
    return []


async def run_one(sem: asyncio.Semaphore, case_id: str, case_data: dict, test: dict) -> dict:
    async with sem:
        started = time.monotonic()
        try:
            result = await select_facts(
                test["send"],
                case_data,
                conversation_history=build_history(case_data, test.get("setup", "")),
            )
            error = None
        except Exception as e:  # noqa: BLE001 — spike must survive any failure
            result = {"question_type": "ERROR", "asked_facts": [], "reason": str(e)[:200]}
            error = str(e)[:200]
        elapsed = time.monotonic() - started

    # 上游故障必须计入失败。否则一次全账户欠费会显示成"100% 通过（全部 unknown）"。
    if result["question_type"] == ERROR_QUESTION_TYPE:
        error = error or result.get("reason") or "selector failed"

    expected = list(test.get("basis", []))
    got = effective_facts(result)

    missing = [f for f in expected if f not in got]
    extra = [f for f in got if f not in expected]

    if error:
        # 调用失败一律判不通过——它没有测出任何东西
        passed = False
    elif not expected:
        # 期望"什么都不选"（如 B08 越权请求）
        passed = not got
    else:
        passed = not missing

    return {
        "case_id": case_id,
        "test_id": test["id"],
        "name": test["name"],
        "send": test["send"],
        "expected": expected,
        "got": got,
        "question_type": result["question_type"],
        "asked_facts_raw": result["asked_facts"],
        "missing": missing,
        "extra": extra,
        "exact": sorted(got) == sorted(expected),
        "passed": passed,
        "scored": test["id"] not in BASIS_SEMANTICS_EXCEPTION,
        "reason": result.get("reason", ""),
        "error": error,
        "seconds": round(elapsed, 2),
    }


def print_report(rows: list[dict]) -> None:
    print()
    print("=" * 108)
    print(f"{'用例':<7}{'测试':<6}{'类型':<10}{'期望依据':<26}{'实际选中':<26}{'漏选':<12}{'多选':<10}{'判定'}")
    print("-" * 108)
    for r in rows:
        verdict = "通过" if r["passed"] else "不通过"
        if not r["scored"]:
            verdict = "（不计分）"
        print(
            f"{r['case_id']:<7}{r['test_id']:<6}{r['question_type']:<10}"
            f"{'、'.join(r['expected']) or '（空）':<26}"
            f"{'、'.join(r['got']) or '（空）':<26}"
            f"{'、'.join(r['missing']) or '-':<12}"
            f"{'、'.join(r['extra']) or '-':<10}"
            f"{verdict}"
        )
    print("=" * 108)


def print_summary(rows: list[dict]) -> None:
    scored = [r for r in rows if r["scored"]]
    passed = [r for r in scored if r["passed"]]

    total_out = sum(1 for r in rows if r["extra"])
    errors = [r for r in rows if r["error"]]

    print()
    print(f"计分测试：{len(passed)}/{len(scored)} 通过 "
          f"({100 * len(passed) / len(scored):.1f}%)" if scored else "无计分测试")
    print(f"完全一致（集合相同）：{sum(1 for r in rows if r['exact'])}/{len(rows)}")
    print(f"存在多选（过度披露倾向）的测试：{total_out}/{len(rows)}")
    print(f"调用失败：{len(errors)}")

    print()
    print("按测试项汇总（跨 5 例）：")
    by_test: dict[str, list[dict]] = {}
    for r in rows:
        by_test.setdefault(r["test_id"], []).append(r)
    for test_id in sorted(by_test):
        group = by_test[test_id]
        ok = sum(1 for r in group if r["passed"])
        flag = "  ← 依据语义特殊，不计分" if test_id in BASIS_SEMANTICS_EXCEPTION else ""
        print(f"  {test_id}  {ok}/{len(group)} 通过{flag}")

    print()
    print("失败明细：")
    failures = [r for r in scored if not r["passed"]]
    if not failures:
        print("  （无）")
    for r in failures:
        print(f"  [{r['case_id']} {r['test_id']}] 漏选 {r['missing']} | 期望 {r['expected']} 实得 {r['got']}"
              f" | 类型={r['question_type']} | 问句：{r['send'][:50]}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", help="comma-separated case ids (default: all in behavior_tests.json)")
    parser.add_argument("--tests", help="comma-separated test ids, e.g. B11,B12 (default: all)")
    parser.add_argument("--repeat", type=int, default=1, help="runs per test (default 1)")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--verbose", action="store_true", help="show agent debug logs")
    args = parser.parse_args()

    # 默认只留 warning 以上：逐条 DEBUG 会把报告淹掉
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.verbose else "WARNING")

    tests_doc = json.loads(TESTS_PATH.read_text(encoding="utf-8"))
    wanted = set(args.cases.split(",")) if args.cases else set(tests_doc["cases"])
    wanted_tests = set(args.tests.split(",")) if args.tests else None

    # 只测患者对象（B09/B10 是检查模块，本阶段不覆盖）
    jobs: list[tuple[str, dict, dict]] = []
    for case_id, case_block in tests_doc["cases"].items():
        if case_id not in wanted:
            continue
        patient_path = CASES_DIR / f"{case_id.lower()}.patient.json"
        if not patient_path.exists():
            print(f"Warning: {patient_path.name} not found, skipping {case_id}")
            continue
        case_data = json.loads(patient_path.read_text(encoding="utf-8"))
        for test in case_block["tests"]:
            if test["object"] != "patient":
                continue
            if wanted_tests and test["id"] not in wanted_tests:
                continue
            for _ in range(args.repeat):
                jobs.append((case_id, case_data, test))

    print(f"模型：{settings.llm_model_lite}（lite, temperature=0）")
    print(f"测试：{len(jobs)} 条（{len(wanted)} 例 × 患者对象测试 × repeat={args.repeat}）")
    print("运行中...")

    sem = asyncio.Semaphore(args.concurrency)
    rows = await asyncio.gather(*(run_one(sem, cid, cd, t) for cid, cd, t in jobs))

    print_report(rows)
    print_summary(rows)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = REPORT_DIR / f"spike_report_{stamp}.json"
    out_path.write_text(
        json.dumps({
            "generated_at": stamp,
            "model": settings.llm_model_lite,
            "repeat": args.repeat,
            "results": rows,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n明细已写入 {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
