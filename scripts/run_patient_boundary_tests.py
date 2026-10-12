#!/usr/bin/env python3
"""问患者「病历里没有的事」时，系统怎么处理。

**契约（2026-10-12 起，方案 A）**：医院原文（`_docx.txt:83`）要求
「问及未设定事实时标记 NEEDS_CASE_COMPLETION，**由控制器说明模拟资料不足**；
不能把病例缺失默认成患者否认或**患者记不清**」。
所以这类问句**不出患者台词**，改为系统说明（SSE `data_gap`，落库 `role="system"`）。

断言：
  🔴 `unknown` 轮次**必须**出现 data_gap 说明，且**不得有任何患者台词**
  🔴 其他轮次的患者台词里，不许出现对未设定事实的具体说法
  ⚪ 只报告：路由分布。`exam` 那类是**已知的判别不稳**（问"你做没做过"却去要检查结果）

> 旧版检查「患者有没有把不知道说成没有」——方案 A 之后这一点**结构性地成立**了：
> 患者根本不说话，也就无从断言。所以检查改成验「系统有没有正确标记」。

Usage:
    python scripts/run_patient_boundary_tests.py --case EN01 --repeat 3
"""

import argparse
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from fastapi.testclient import TestClient  # noqa: E402
from loguru import logger  # noqa: E402

logger.remove()
for _n in ("sqlalchemy", "sqlalchemy.engine"):
    logging.getLogger(_n).disabled = True

from app.main import app  # noqa: E402

# 探针：问的都是 EN01 病历里**没有**的事。
# `forbidden` 是「对未设定事实下断言」的说法——只在**非 unknown** 路由下才可能命中
# （判成 meta 时患者仍会说话，那时才需要这一层）。按人称/时间锚定，避免误伤
# 「我没太注意有没有拍过」这种选择疑问。
PROBES = [
    {"send": "你以前拍过牙片或者片子吗？", "topic": "拍片",
     "forbidden": ["我没拍过", "没有拍过片", "我没拍片子", "以前没拍过", "从来没拍过"]},
    {"send": "你平时喝酒吗？", "topic": "饮酒",
     "forbidden": ["我不喝酒", "我从来不喝", "我滴酒不沾", "我不怎么喝酒", "平时不怎么喝酒"]},
    {"send": "你家里人有没有类似的牙齿问题？", "topic": "家族史",
     "forbidden": ["家里没人有", "家人没有", "没有家族史", "家族里没有"]},
    {"send": "你最近有没有便血？", "topic": "便血",
     "forbidden": ["没有便血", "我不便血", "从来没便血"]},
    {"send": "你平时工作压力大吗？", "topic": "压力",
     "forbidden": ["我没压力", "压力不大", "没什么压力"]},
]


def parse_all(text: str) -> dict:
    ev = {"gap": None, "patient": "", "qtype": None, "disclosed": [], "exam_ids": []}
    for block in text.split("\n\n"):
        nm = pl = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                nm = line[7:].strip()
            elif line.startswith("data: "):
                pl = line[6:]
        if not nm or pl is None:
            continue
        try:
            d = json.loads(pl)
        except json.JSONDecodeError:
            continue
        if nm == "data_gap":
            ev["gap"] = d.get("message", "")
        elif nm == "token":
            ev["patient"] += d.get("token", "")
        elif nm == "done":
            ev["qtype"] = d.get("question_type")
            ev["disclosed"] = d.get("disclosed") or []
            ev["exam_ids"] = d.get("exam_ids") or []
    return ev


def judge(probe: dict, ev: dict) -> tuple[bool, str]:
    qtype = ev["qtype"] or "?"
    if qtype == "unknown":
        if not ev["gap"]:
            return False, f"{qtype} 但没有 data_gap 说明"
        if ev["patient"].strip():
            return False, f"{qtype} 患者不该说话，却说了：{ev['patient'][:40]}"
        return True, f"{qtype} → 系统说明（患者未发声）"
    hits = [f for f in probe["forbidden"] if f in ev["patient"]]
    if hits:
        return False, f"{qtype} 患者对未设定事实下了断言：{hits}"
    return True, f"{qtype} 患者未就未设定事实作断言"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="EN01")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--keep-sessions", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    client = TestClient(app)
    token = client.post("/api/v1/auth/login",
                        json={"username": "test001", "password": "123456"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    cases = {c["title"]: c for c in client.get("/api/v1/cases", headers=headers).json()["cases"]}
    if args.case not in cases:
        print(f"{args.case} 不在已切片病例里")
        sys.exit(1)

    rows, sessions = [], []
    for run_i in range(args.repeat):
        for probe in PROBES:
            sid = client.post("/api/v1/sessions", json={"case_id": cases[args.case]["id"]},
                              headers=headers).json()["id"]
            sessions.append(sid)
            resp = client.post(f"/api/v1/sessions/{sid}/messages",
                               json={"content": probe["send"]}, headers=headers)
            ev = parse_all(resp.text)
            ok, detail = judge(probe, ev)
            rows.append({**probe, "run": run_i + 1, "reply": ev["patient"],
                         "gap": ev["gap"], "qtype": ev["qtype"] or "",
                         "disclosed": ev["disclosed"], "exam_ids": ev["exam_ids"],
                         "detail": detail, "passed": ok})

    print(f"未设定事实的处理 · {args.case} · {len(PROBES)} 探针 × {args.repeat} 次\n")
    for r in rows:
        mark = "✅" if r["passed"] else "❌"
        print(f"{mark} [{r['topic']}] {r['send']}\n    {r['qtype']:9} {r['detail']}")

    passed = sum(1 for r in rows if r["passed"])
    dist = Counter(r["qtype"] for r in rows)
    print("-" * 70)
    print(f"未设定事实的处理：{passed}/{len(rows)} 通过")
    print("路由分布：" + "  ".join(f"{k}×{v}" for k, v in dist.most_common()))
    wild = [r for r in rows if r["qtype"] == "exam"]
    if wild:
        print(f"⚠ 有 {len(wild)}/{len(rows)} 条被路由给检查模块"
              f"（问患者「做没做过」却去要检查结果）——已知判别不稳，见 simulation-quality-plan.md")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "data" / "tests" / f"patient_boundary_report_{ts}.json"
    out.write_text(json.dumps({"case": args.case, "rows": rows}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"明细 → {out.relative_to(ROOT)}")

    if not args.keep_sessions:
        for sid in sessions:
            client.delete(f"/api/v1/sessions/{sid}", headers=headers)
        print(f"已清理 {len(sessions)} 个测试会话")
    sys.exit(0 if passed == len(rows) else 1)


if __name__ == "__main__":
    main()
