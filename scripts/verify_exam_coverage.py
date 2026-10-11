#!/usr/bin/env python3
"""检查模块验收：逐项核对"学生申请检查 → 系统给出对应资料"是否成立。

不是单元测试，是**对需求的逐条核对**。对每一例、每一个检查项、每一个子项，
用该项自己的名字构造一次申请，走**真实 HTTP 接口**（登录 → 建会话 → SSE），然后核对：

  C1 路由    这次申请被判成 `exam`，交给检查模块（不是患者）
  C2 命中    命中的是**申请的那一项**，不是别的项
  C3 忠实    返回的正文**逐字来自该病例的 result**，且保持原顺序——没有编造、没有串项
  C4 完整    申请整项时应返回整条 result；申请子项时只返回该子项的片段
  C5 未提供  病例没有该项结果时，明确说"未提供"，绝不编数值、不说"正常"
  C6 越界    exam 数据里不含诊断/治疗/评分内容（权限边界）

用法：
    python scripts/verify_exam_coverage.py
"""

import json
import logging
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# DATABASE_URL 是 CWD 相对的，必须切到 backend/ 才能连到真库（见 CLAUDE.md 的 CWD 陷阱）
os.chdir(ROOT / "backend")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.message import Message  # noqa: E402

PUNCT = re.compile(r"[\s，,。.；;：:、！!？?（）()【】\[\]“”\"'‘’～~\-—_/／]+")
NOT_PROVIDED_MARK = "未提供"


def norm(text: str) -> str:
    return PUNCT.sub("", text or "").lower()


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


def body_of(content: str) -> str:
    """去掉「【项名 · 子项名】」标题行，只留正文。"""
    return content.split("\n", 1)[-1].strip() if "\n" in content else ""


def ask(client, headers, case_id: int, text: str) -> dict:
    sid = client.post("/api/v1/sessions", json={"case_id": case_id}, headers=headers).json()["id"]
    resp = client.post(f"/api/v1/sessions/{sid}/messages", json={"content": text}, headers=headers)
    events = parse_sse(resp.text)
    done = next((d for n, d in events if n == "done"), {})
    content = "".join(d.get("content", "") for n, d in events if n == "exam")
    return {"session_id": sid, "done": done, "content": content, "body": body_of(content)}


def main() -> None:
    logging.disable(logging.INFO)
    sys.stdout.reconfigure(encoding="utf-8")

    client = TestClient(app)
    token = client.post(
        "/api/v1/auth/login", json={"username": "test001", "password": "123456"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    raw_cases = json.loads((ROOT / "data" / "tests" / "behavior_tests.json").read_text(encoding="utf-8"))
    case_ids = list(raw_cases["cases"].keys())

    api_cases = {c["title"]: c["id"] for c in client.get("/api/v1/cases", headers=headers).json()["cases"]}

    checks: Counter = Counter()
    failures: list[str] = []
    used = []
    total = 0

    def record(code: str, ok: bool, detail: str) -> None:
        nonlocal total
        total += 1
        checks[code] += 1
        if not ok:
            failures.append(f"[{code}] {detail}")

    for case_id in sorted(case_ids):
        db_case = json.loads((ROOT / "data" / "cases" / f"{case_id.lower()}.exam.json").read_text(encoding="utf-8"))
        db_id = api_cases[case_id]

        # ── C6 权限边界：exam 数据里不得有诊断/治疗/评分内容 ──────────
        blob = json.dumps(db_case, ensure_ascii=False)
        leaked = [k for k in ("diagnosis", "treatment_plan", "differential", "\"D01\"", "\"T01\"") if k in blob]
        record("C6", not leaked, f"{case_id} exam 数据里出现越界内容 {leaked}")

        for eid, item in db_case["exams"].items():
            label = item["label"]
            result = item.get("result")
            # 学生按 B 模块的方式直接申请整项
            send = f"请提供“{label}”的文字检查结果。"
            got = ask(client, headers, db_id, send)
            used.append(got["session_id"])
            done = got["done"]

            # C1 路由到检查模块
            record("C1", done.get("question_type") == "exam",
                   f"{case_id} {eid}「{send[:24]}」被判成 {done.get('question_type')!r} 而非 exam")

            # C2 命中的是这一项
            record("C2", eid in (done.get("exam_ids") or []),
                   f"{case_id} {eid}「{label}」命中 {(done.get('exam_ids') or [])}")

            body = got["body"]
            if not result:
                # C5 未提供项：必须明说未提供，且不给任何数值
                record("C5", NOT_PROVIDED_MARK in body,
                       f"{case_id} {eid} 未提供项却回答：{body[:60]!r}")
                record("C3", re.search(r"\d", body) is None,
                       f"{case_id} {eid} 未提供项里出现了数值：{body[:60]!r}")
            else:
                # C3 正文逐字来自 result（去标点后应是 result 的子串，且保序）
                record("C3", norm(body) in norm(result),
                       f"{case_id} {eid} 正文不是原文子串：{body[:60]!r}")
                # C4 整项申请 → 应返回完整 result
                record("C4", norm(body) == norm(result),
                       f"{case_id} {eid} 整项申请只返回了部分：{body[:60]!r}")

            # ── 子项级：用子项名申请，应只返回该子项 ──────────────
            for sub in item.get("subitems") or []:
                frags = sub.get("result_fragments") or []
                # 用**别名**构造申请，而不是子项名——医院给的分组名（如"其他部位检查"）
                # 本来就不在别名表里，拿它当申请语是验收脚本自己写错了。
                alias = (sub.get("aliases") or [None])[0]
                if not alias:
                    continue
                send = f"请做一下“{alias}”"
                got = ask(client, headers, db_id, send)
                used.append(got["session_id"])
                done = got["done"]
                key = f"{eid}.{sub['key']}"
                body = got["body"]

                record("C1", done.get("question_type") == "exam",
                       f"{case_id} {key}「{send}」被判成 {done.get('question_type')!r}")
                if not frags:
                    # 伞形子项：问它返回整包，这是设计如此
                    record("C4", norm(body) == norm(result or ""),
                           f"{case_id} {key} 伞形子项未返回整包：{body[:60]!r}")
                else:
                    record("C2", key in (done.get("subitem_keys") or []),
                           f"{case_id} {key}「{alias}」命中了 {(done.get('subitem_keys') or [])}")
                    # C3：返回的正文应当**正好**是该子项声明的那些片段。
                    # 注意不能要求它是 result 的"连续子串"——一个子项可能拥有多段不连续的
                    # 结果（中间夹着别的子项），那时正文正确地跳过中间那段，就不是连续子串了。
                    expected = norm("".join(frags))
                    record("C3", bool(body) and norm(body) == expected,
                           f"{case_id} {key} 正文与声明的片段不符：{body[:60]!r} ≠ {frags}")
                    # 只返回该子项：正文不应包含别的子项的片段
                    others = [f for o in (item.get("subitems") or [])
                              if o["key"] != sub["key"] for f in (o.get("result_fragments") or [])]
                    bleed = [f for f in others if norm(f) and norm(f) in norm(body)]
                    record("C4", not bleed,
                           f"{case_id} {key} 带出了别的子项的内容：{bleed}")

    # ── 清理测试会话 ──────────────────────────────────────────────
    db = SessionLocal()
    db.query(Message).filter(Message.session_id.in_(used)).delete(synchronize_session=False)
    from app.models.session import Session as SessionModel
    db.query(SessionModel).filter(SessionModel.id.in_(used)).delete(synchronize_session=False)
    db.commit()
    db.close()

    names = {
        "C1": "路由到检查模块", "C2": "命中申请的那一项", "C3": "正文逐字来自病例原文",
        "C4": "只给申请的内容", "C5": "未提供项明确说明", "C6": "无诊断/治疗越界",
    }
    print(f"\n{'核对项':<26}{'通过':<10}{'合计'}")
    print("-" * 50)
    for code in ("C1", "C2", "C3", "C4", "C5", "C6"):
        n = checks[code]
        bad = len([f for f in failures if f.startswith(f"[{code}]")])
        print(f"{names[code]:<24}{n - bad:<10}{n}")
    print("-" * 50)

    if failures:
        print(f"\n不通过 {len(failures)} 处：")
        for f in failures[:40]:
            print("  " + f)
        if len(failures) > 40:
            print(f"  …另有 {len(failures) - 40} 处")
    else:
        print("\n全部核对项通过 ✅")
    print(f"\n共发起 {len(used)} 次真实接口调用（已清理）")


if __name__ == "__main__":
    main()
