#!/usr/bin/env python3
"""Q1 — S01/S02 multi-turn regression: the hospital's only continuity spec.

B01–B12 each run in a **fresh session**, so they can never catch a bug that only
appears after several turns. S01/S02 are the specs that do — and until 2026-10-12
they had never been run. A manual pass found two spec violations; this turns them
into a regression.

Each script runs in ONE session, start to finish, keeping the real replies
(the docx: 「从空会话开始，持续保留系统实际回答」).

Assertions per step:
  - 对象=检查      该轮应返回检查结果；依据是规则（权限/缺失）时应明确"未提供"
  - 对象=患者·规则  不得给出任何事实或检查结果（越权/缺失步）
  - 对象=患者·ID    期望依据里的 ID 至少被触及一个

Everything else (premise-correction traps like S02-03, naturalness) is **recorded
for human reading**, not asserted — a machine assertion there would be theatre.
The run also writes a markdown dump of every reply for that.

Usage:
    python scripts/run_s01_s02_tests.py                       # EN01, 1 run
    python scripts/run_s01_s02_tests.py --cases EN01,PE01 --repeat 3
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
os.chdir(ROOT / "backend")   # DATABASE_URL 是 CWD 相对的

from fastapi.testclient import TestClient  # noqa: E402
from loguru import logger  # noqa: E402

logger.remove()
for _n in ("sqlalchemy", "sqlalchemy.engine"):
    logging.getLogger(_n).disabled = True

from app.main import app  # noqa: E402

SCRIPTS_PATH = ROOT / "data" / "tests" / "s01_s02.json"
REPORT_DIR = ROOT / "data" / "tests"

NOT_PROVIDED_HINT = "未提供"


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        name, payload = None, None
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line[7:].strip()
            elif line.startswith("data: "):
                payload = line[6:]
        if name and payload is not None:
            try:
                events.append((name, json.loads(payload)))
            except json.JSONDecodeError:
                pass
    return events


def judge(step: dict, done: dict, reply: str) -> tuple[bool, str]:
    qtype = done.get("question_type", "")
    disclosed = done.get("disclosed") or []
    exam_ids = done.get("exam_ids") or []

    if step["object"] == "exam":
        if step["is_rule"]:
            ok = NOT_PROVIDED_HINT in reply or "没有记录" in reply
            return ok, f"{qtype} 回复={'未提供' if ok else reply[:40]}"
        ok = bool(exam_ids)
        return ok, f"{qtype} exam_ids={exam_ids or '无'}"

    # 患者步骤
    if step["is_rule"]:
        # 越权/缺失：不得给出任何资料
        ok = not disclosed and not exam_ids
        return ok, f"{qtype} disclosed={disclosed or '空'} exam_ids={exam_ids or '空'}"

    hit = sorted(set(step["basis"]) & set(disclosed))
    return bool(hit), f"{qtype} 期望{step['basis']} ∩ 实际{disclosed or '空'} = {hit or '无'}"


def run_script(client, headers, case: dict, key: str, script: dict, run_i: int) -> dict:
    sid = client.post("/api/v1/sessions", json={"case_id": case["id"]},
                      headers=headers).json()["id"]
    steps_out = []
    for step in script["steps"]:
        resp = client.post(f"/api/v1/sessions/{sid}/messages",
                           json={"content": step["send"]}, headers=headers)
        events = parse_sse(resp.text)
        done = next((d for n, d in events if n == "done"), {})
        reply = ("".join(d.get("token", "") for n, d in events if n == "token")
                 + "".join(d.get("content", "") for n, d in events if n == "exam")).strip()
        ok, detail = judge(step, done, reply)
        steps_out.append({**step, "reply": reply, "question_type": done.get("question_type", ""),
                          "disclosed": done.get("disclosed") or [],
                          "exam_ids": done.get("exam_ids") or [],
                          "passed": ok, "detail": detail})
    return {"session_id": sid, "case": case["title"], "script": key,
            "name": script["name"], "run": run_i, "steps": steps_out}


def cleanup(client, headers, records) -> None:
    """多轮脚本会在库里留下整场会话，跑完自己清掉（--keep-sessions 可保留）。"""
    n = 0
    for rec in records:
        r = client.delete(f"/api/v1/sessions/{rec['session_id']}", headers=headers)
        n += 1 if r.status_code < 400 else 0
    print(f"已清理 {n} 个测试会话")


def build_markdown(records: list[dict], meta: dict) -> str:
    """把每一步的原回复打出来——给需求方读（机器只能断言 ID，读不出自然不自然）。"""
    L = ["# S01/S02 多轮回归：逐句实录", "",
         f"> 生成于 {meta['at']}，每脚本跑 {meta['repeat']} 次。",
         "> 机器只断言「期望依据 ID 是否被触及」与「越权步是否给了资料」；",
         "> **自然不自然、有没有答非所问，需要人读下面这些原回复。**", ""]
    for rec in records:
        L += [f"## {rec['case']} · {rec['script'].upper()} {rec['name']} · run{rec['run']}", ""]
        for s in rec["steps"]:
            mark = "✅" if s["passed"] else "❌"
            who = "🔬检查" if s["object"] == "exam" else "🧑患者"
            L += [f"**{s['n']} {mark}** `{s['send']}`  ",
                  f"　　期望 `{s['basis_raw']}` → {s['detail']}  ",
                  f"　　{who}：{s['reply']}", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", default="EN01")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--scripts", default="s01,s02")
    ap.add_argument("--keep-sessions", action="store_true", help="保留测试会话（默认跑完清掉）")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    data = json.loads(SCRIPTS_PATH.read_text(encoding="utf-8"))
    wanted = [c.strip() for c in args.cases.split(",") if c.strip()]
    keys = [k.strip().lower() for k in args.scripts.split(",") if k.strip()]

    client = TestClient(app)
    token = client.post("/api/v1/auth/login",
                        json={"username": "test001", "password": "123456"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    cases = {c["title"]: c for c in client.get("/api/v1/cases", headers=headers).json()["cases"]}

    records = []
    for cid in wanted:
        if cid not in cases:
            print(f"  ⚠ {cid} 不在已切片的 5 例里，跳过")
            continue
        for key in keys:
            script = data["cases"][cid]["scripts"].get(key)
            if not script:
                print(f"  ⚠ {cid} 无 {key}")
                continue
            for run_i in range(args.repeat):
                rec = run_script(client, headers, cases[cid], key, script, run_i + 1)
                records.append(rec)
                bad = [s for s in rec["steps"] if not s["passed"]]
                print(f"{cid} {key.upper()} run{run_i + 1}: "
                      f"{len(rec['steps']) - len(bad)}/{len(rec['steps'])} 步通过")
                for s in bad:
                    print(f"    ❌ {s['n']} 「{s['send'][:34]}」 {s['detail']}")

    total = sum(len(r["steps"]) for r in records)
    passed = sum(1 for r in records for s in r["steps"] if s["passed"])
    print("-" * 70)
    print(f"S01/S02 多轮回归：{passed}/{total} 步通过")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    meta = {"at": datetime.now().isoformat(timespec="seconds"), "repeat": args.repeat}
    (REPORT_DIR / f"s01_s02_report_{ts}.json").write_text(
        json.dumps({"meta": meta, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    md = REPORT_DIR / f"s01_s02_replies_{ts}.md"
    md.write_text(build_markdown(records, meta), encoding="utf-8")
    print(f"逐句实录（请人读）→ {md.relative_to(ROOT)}")
    if not args.keep_sessions:
        cleanup(client, headers, records)


if __name__ == "__main__":
    main()
