#!/usr/bin/env python3
"""M5 — behaviour-test regression: drive the whole chain and assert disclosure IDs.

This is the quantitative acceptance for the patient-simulation pipeline. For each
patient-object B test, for N repetitions, in a **fresh session** (the docx says
每项独立重置), it:

  1. creates a session (opening = data.opening, no LLM)
  2. seeds the test's 前情 as prior turns when present (前情 is role history)
  3. sends the test's 发送 through the real SSE endpoint
  4. asserts disclosed IDs == 依据

Ground truth is the hospital docx's own `依据` field (extracted into
data/tests/behavior_tests.json). B06 is excluded: its 依据 means "the whole fact
base must not be contradicted", not "these are the facts this sentence asks for",
so it is checked behaviourally, not by ID (see dev-plan M2 record).

Why ID assertion only, no keyword check: the "never leaks diagnosis" property is
enforced **structurally** (patient.json has no D/DD/T/G/R) and verified
**behaviourally** (B08 asserts the patient deflects). A keyword blacklist would
have to hardcode diagnosis terms — content in code, violating P3.

Usage:
    python scripts/run_behavior_tests.py                    # 5 cases × patient tests × 3 runs
    python scripts/run_behavior_tests.py --cases EN01 --repeat 1
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# DATABASE_URL 是 CWD 相对的（sqlite:///./data/app.db），必须切到 backend/ 才能连到真库，
# 否则会在仓库根目录凭空造一个空 app.db（见 CLAUDE.md 的 CWD 陷阱）。
os.chdir(ROOT / "backend")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.message import Message  # noqa: E402

# 静音 loguru：否则每个 LLM 调用的 DEBUG 会刷屏（逐条报告被淹没）
from loguru import logger  # noqa: E402

CASES_DIR = ROOT / "data" / "cases"
TESTS_PATH = ROOT / "data" / "tests" / "behavior_tests.json"
REPORT_DIR = ROOT / "data" / "tests"

EMPTY_SETUP = "无；空会话。"
BASIS_SEMANTICS_EXCEPTION = {"B06"}
TURN_RE = re.compile(r"(学员|患者)[：:]\s*(.*?)(?=\s*→\s*(?:学员|患者)[：:]|$)")


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        name = data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line[7:].strip()
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name:
            events.append((name, data or {}))
    return events


def seed_setup(session_id: int, setup: str) -> None:
    """Write the test's 前情 into the session as real prior turns."""
    turns = TURN_RE.findall(setup)
    if not turns:
        return
    db = SessionLocal()
    for speaker, content in turns:
        db.add(Message(
            session_id=session_id,
            role="student" if speaker == "学员" else "patient",
            content=content.strip(),
            round_num=0,
            intent="setup",
        ))
    db.commit()
    db.close()


def run_one(client: TestClient, headers: dict, case: dict, test: dict, run_i: int) -> dict:
    """One fresh session, one test, one run. Returns the assertion record."""
    sid = client.post("/api/v1/sessions", json={"case_id": case["id"]}, headers=headers).json()["id"]

    setup = test.get("setup", "")
    if setup.strip() and setup.strip() != EMPTY_SETUP:
        seed_setup(sid, setup)

    resp = client.post(f"/api/v1/sessions/{sid}/messages", json={"content": test["send"]}, headers=headers)
    events = parse_sse(resp.text)
    done = next((d for n, d in events if n == "done"), {})

    # 患者测试走 token 流；检查测试走 exam 事件（整段文本，不流式）
    answer = "".join(d.get("token", "") for n, d in events if n == "token")
    answer += "".join(d.get("content", "") for n, d in events if n == "exam")

    # 检查模块用 exam_ids 断言；患者用 disclosed 断言
    disclosed = done.get("exam_ids", []) if test["object"] == "exam" else done.get("disclosed", [])
    expected = list(test.get("basis", []))

    if test["id"] in BASIS_SEMANTICS_EXCEPTION:
        passed = None  # 不计分：用行为验收
        missing = extra = []
    else:
        missing = [i for i in expected if i not in disclosed]
        extra = [i for i in disclosed if i not in expected]
        passed = not missing

    return {
        "session_id": sid,
        "case_id": case["title"],
        "test_id": test["id"],
        "run": run_i,
        "expected": expected,
        "disclosed": disclosed,
        "missing": missing,
        "extra": extra,
        "passed": passed,
        "answer": answer,
    }


def cleanup(session_ids: list[int]) -> None:
    db = SessionLocal()
    db.query(Message).filter(Message.session_id.in_(session_ids)).delete(synchronize_session=False)
    from app.models.session import Session as SessionModel
    db.query(SessionModel).filter(SessionModel.id.in_(session_ids)).delete(synchronize_session=False)
    db.commit()
    db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", help="comma-separated case ids (default: all in behavior_tests.json)")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--keep-sessions", action="store_true", help="do not delete the test sessions afterwards")
    args = parser.parse_args()

    logging.disable(logging.INFO)
    sys.stdout.reconfigure(encoding="utf-8")
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    tests_doc = json.loads(TESTS_PATH.read_text(encoding="utf-8"))
    wanted = set(args.cases.split(",")) if args.cases else set(tests_doc["cases"])

    client = TestClient(app)
    token = client.post("/api/v1/auth/login", json={"username": "test001", "password": "123456"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    cases = {c["title"]: c for c in client.get("/api/v1/cases", headers=headers).json()["cases"]}

    rows = []
    for case_id in sorted(wanted):
        if case_id not in tests_doc["cases"]:
            print(f"Warning: {case_id} not in behavior_tests.json, skipping")
            continue
        if case_id not in cases:
            print(f"Warning: {case_id} not seeded in DB, skipping")
            continue
        case = cases[case_id]
        # 患者对象 + 检查模块对象都跑：B01–B08/B11/B12 是患者，B09/B10 是检查模块
        tests = list(tests_doc["cases"][case_id]["tests"])
        for test in tests:
            for run_i in range(args.repeat):
                rows.append(run_one(client, headers, case, test, run_i + 1))

    # ── Report ────────────────────────────────────────────────────
    scored = [r for r in rows if r["passed"] is not None]
    passed = [r for r in scored if r["passed"]]
    leaks = [r for r in rows if r["disclosed"] and not r["expected"]]

    print(f"\n{'用例':<6}{'测试':<6}{'期望依据':<22}{'3 次实际披露':<40}{'通过'}")
    print("-" * 90)
    by_key: dict = {}
    for r in rows:
        by_key.setdefault((r["case_id"], r["test_id"]), []).append(r)
    for (case_id, test_id) in sorted(by_key):
        group = by_key[(case_id, test_id)]
        runs = " | ".join("、".join(g["disclosed"]) or "空" for g in group)
        if group[0]["passed"] is None:
            verdict = "不计分"
        else:
            verdict = f"{sum(1 for g in group if g['passed'])}/{len(group)}"
        print(f"{case_id:<6}{test_id:<6}{'、'.join(group[0]['expected']) or '（空）':<22}{runs:<40}{verdict}")

    print("-" * 90)
    print(f"计分测试：{len(passed)}/{len(scored)} 通过 ({100 * len(passed) / len(scored):.1f}%)" if scored else "无计分测试")
    if leaks:
        print(f"⚠️ 越权请求却披露了事实（应披露为空）的测试：{len(leaks)}")
        for r in leaks:
            print(f"   [{r['case_id']} {r['test_id']}] disclosed={r['disclosed']}")
    else:
        print("越权/隐藏信息隔离（B08 等）全部守住了 ✅")

    failures = [r for r in scored if not r["passed"]]
    if failures:
        print(f"\n失败明细（{len(failures)} 条）：")
        for r in failures:
            print(f"   [{r['case_id']} {r['test_id']} run{r['run']}] 漏披露 {r['missing']} "
                  f"| 期望 {r['expected']} 实得 {r['disclosed']} | 问句：{r['answer'][:30]}")
    else:
        print("\n无失败项 ✅")

    # ── Snapshot + cleanup ────────────────────────────────────────
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = REPORT_DIR / f"behavior_test_report_{stamp}.json"
    out_path.write_text(json.dumps({
        "generated_at": stamp,
        "repeat": args.repeat,
        "results": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n明细已写入 {out_path.relative_to(ROOT)}")

    if not args.keep_sessions:
        cleanup([r["session_id"] for r in rows])
        print(f"已清理 {len(rows)} 个测试会话（用 --keep-sessions 保留）")


if __name__ == "__main__":
    main()
