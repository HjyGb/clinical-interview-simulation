#!/usr/bin/env python3
"""Sub-item trimming regression — asserts the exam module returns only what was asked for.

The B tests cannot cover this: B09 asks for a whole item, so it passes whether or not
sub-item trimming works. These tests come from a different spec — the docx's own
「实际返回」 lines, several of which state an explicit rule:

    相关子项请求仅返回该项结果，不可返回整个 E 项
    （如仅询问冷诊，不可同时返回叩诊结果）

Pure Python against the data in the DB — no LLM, so it is fast, free and deterministic.
(The LLM's only role here is deciding "is this an exam request at all", which B09/B10
already exercise through the full API.)

Usage:
    python scripts/run_exam_subitem_tests.py
"""

import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# DATABASE_URL 是 CWD 相对的，必须切到 backend/ 才连得到真库（见 CLAUDE.md 的 CWD 陷阱）
os.chdir(ROOT / "backend")

from app.database import SessionLocal  # noqa: E402
from app.services import case_service  # noqa: E402
from agent.exam_module import answer  # noqa: E402

TESTS_PATH = ROOT / "data" / "tests" / "exam_subitem_tests.json"


def main() -> None:
    logging.disable(logging.INFO)
    sys.stdout.reconfigure(encoding="utf-8")

    tests = json.loads(TESTS_PATH.read_text(encoding="utf-8"))["tests"]

    db = SessionLocal()
    by_title = {
        case_service.get_case_full(db, i)["title"]: case_service.get_case_full(db, i)["exam_data"]
        for i in range(1, 200)
        if case_service.get_case_full(db, i)
    }
    db.close()

    passed = 0
    rows = []
    for t in tests:
        case_id = t["case_id"]
        exam_data = by_title.get(case_id)
        if exam_data is None:
            rows.append((t, "病例未入库", [], []))
            continue

        result = answer(t["send"], exam_data)
        got_keys = result["subitem_keys"]
        # 只检查**正文**：标题行是「项名 · 子项名」，项名里本来就含别的子项的字
        # （如「36及对照牙冷测、叩诊 · 冷测」含"叩诊"），拿整段做文本断言会误报。
        body = result["content"].split("\n", 1)[-1]

        missing = [k for k in t["expect_subitems"] if k not in got_keys]
        leaked = [s for s in t.get("forbid_contains", []) if s in body]
        ok = not missing and not leaked
        passed += ok
        rows.append((t, "通过" if ok else "不通过", missing, leaked))

    print(f"\n{'用例':<7}{'发送':<24}{'期望子项':<26}{'实得子项':<26}{'判定'}")
    print("-" * 100)
    for t, verdict, missing, leaked in rows:
        exam_data = by_title.get(t["case_id"])
        got = answer(t["send"], exam_data)["subitem_keys"] if exam_data else []
        print(
            f"{t['case_id']:<7}{t['send']:<24}"
            f"{'、'.join(t['expect_subitems']) or '（整包）':<26}"
            f"{'、'.join(got) or '（整包）':<26}{verdict}"
        )

    print("-" * 100)
    print(f"子项裁剪测试：{passed}/{len(tests)} 通过 ({100 * passed / len(tests):.1f}%)")

    failures = [r for r in rows if r[1] != "通过"]
    if failures:
        print("\n失败明细：")
        for t, verdict, missing, leaked in failures:
            exam_data = by_title.get(t["case_id"])
            content = answer(t["send"], exam_data)["content"] if exam_data else ""
            print(f"  [{t['case_id']}] {t['send']}")
            if missing:
                print(f"     漏子项 {missing}")
            if leaked:
                print(f"     多返回了未申请的内容 {leaked}")
            print(f"     实际回答：{content[:90]}")
            print(f"     规则依据：{t['why']}")
    else:
        print("无失败项 ✅")


if __name__ == "__main__":
    main()
