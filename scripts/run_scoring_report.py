#!/usr/bin/env python3
"""P5/P6 — 生成一份完整的 R14 评分报告，供人眼审核。

用一份合成对话 + 三种学员作答（良 / 空 / 半），跑完整链路：
R01–R04 代码判定 + R05–R14 LLM 判定 + 安全通道 + NE/NA，然后打印报告。

这是给人看的（dev-plan「你测：读评分报告，判断评分合不合理」），不是回归测试——
自动断言在 run_scoring_deterministic_tests.py / run_scoring_llm_tests.py 里。

Usage:
    python scripts/run_scoring_report.py --case EN01 --report good
    python scripts/run_scoring_report.py --case EN01 --report empty
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

import logging  # noqa: E402

from loguru import logger  # noqa: E402

logger.remove()
for _n in ("sqlalchemy", "sqlalchemy.engine"):
    logging.getLogger(_n).disabled = True
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from scoring.runner import score_session  # noqa: E402

TRANSCRIPT = [
    {"role": "student", "content": "您好，我是今天的接诊医生。请问您这次是哪里不舒服？", "round_num": 1},
    {"role": "patient", "content": "（患者叙述本次就诊的起因与经过）", "round_num": 1},
    {"role": "student", "content": "这种情况持续多久了？有没有加重？", "round_num": 2},
    {"role": "patient", "content": "（患者补充时间与变化）", "round_num": 2},
    {"role": "student", "content": "请提供相关检查的结果。", "round_num": 3},
    {"role": "exam", "content": "（本例资料中记录的检查结果）", "round_num": 3},
    {"role": "student", "content": "我先跟您说一下目前主要是什么问题，以及我们打算怎么处理；", "round_num": 4},
    {"role": "student", "content": "具体方案还要看治疗中的实际情况，现在不能给您打包票。", "round_num": 4},
    {"role": "student", "content": "您刚才提到的那点担心我听明白了，这个顾虑是合理的。", "round_num": 5},
    {"role": "student", "content": "如果出现某些情况请及时来复诊，不要拖。", "round_num": 5},
]


def load(case_id: str, kind: str) -> dict:
    return json.loads((ROOT / "data" / "cases" / f"{case_id.lower()}.{kind}.json")
                      .read_text(encoding="utf-8"))


def build_report(answer_key: dict, mode: str) -> dict:
    if mode == "empty":
        return {}
    full = {
        "primary_diagnosis": answer_key["diagnosis"]["content"],
        "diagnosis_reason": answer_key["diagnosis_reason"]["content"],
        "differential_diagnosis": "；".join(
            f"{d['label']}：{d['reason']}" for d in answer_key.get("differentials", [])),
        "immediate_plan": (answer_key["plan"]["immediate"] or {}).get("content") or "",
        "staged_plan": "；".join(
            (answer_key["plan"][k] or {}).get("content") or ""
            for k in ("definitive", "review")),
    }
    if mode == "good":
        return full
    # partial：只写诊断和理由，计划和鉴别空着
    return {k: (v if k in ("primary_diagnosis", "diagnosis_reason") else "")
            for k, v in full.items()}


def render(report: dict) -> str:
    L = []
    safety = report["safety"]
    if safety["requires_review"]:
        L.append("┌─ ⚠ 需人工复核 " + "─" * 50)
        for f in safety["flags"]:
            if f["hit"]:
                L.append(f"│ 命中关键错误 {f['index']}：{f['error']}")
                L.append(f"│   学员原话：{f['evidence_quote'][:60]}")
            elif not f["checked"]:
                L.append(f"│ 未能复核 {f['index']}：{f['error']}（系统侧未跑成，不等于没犯）")
        if safety["safety_priority_case"]:
            L.append(f"│ 【安全优先例】已识别危险并转诊：{safety['stop_evidence'][:50]}")
        L.append("│ 安全标记不参与计分，也不与沟通表现相互抵消。")
        L.append("└" + "─" * 58)
        L.append("")

    by_id = {i["id"]: i for i in report["items"]}
    for view in report["views"]:
        L.append(f"┌─ {view['name']} " + "─" * 50)
        for g in view["groups"]:
            bar = "".join(
                {"2": "▓▓", "1": "▓░", "0": "░░"}.get(str(by_id[i]["score"]), "··")
                for i in g["items"] if i in by_id)
            L.append(f"│  {g['name']:<14} {' '.join(g['items'])}  {bar}  {g['score']}/{g['max']}")
        L.append("└" + "─" * 58)
        L.append("")

    t = report["total"]
    L.append(f"原始分：{t['raw_total']} / 可评上限 {t['raw_max_counted']}（名义满分 {t['raw_max_nominal']}）")
    if t["excluded"]:
        L.append(f"未计入：{t['excluded']}")
    if report["system_errors"]:
        L.append(f"⚠ 会话中出现 {report['system_errors']} 次上游失败（未折算为学员失分）")
    L.append("")
    L.append("逐项明细：")
    for i in report["items"]:
        mark = {"scored": " ", "ne": "NE", "na": "NA", "skipped_safety": "SS"}[i["status"]]
        ev = next((e["quote"] for e in i["evidence"] if e.get("quote")), "")
        note = i["note"] or ev
        L.append(f"  {i['id']} {i['score']}/{i['max_score']} [{mark}] {note[:64]}")
    return "\n".join(L)


async def run(case_id: str, mode: str) -> None:
    rubric = load(case_id, "rubric")
    answer = load(case_id, "answer")
    try:
        exam = load(case_id, "exam")
    except FileNotFoundError:
        exam = None
    common = {i["id"]: i for i in json.loads(
        (ROOT / "data" / "scoring" / "rubric_common.json").read_text(encoding="utf-8"))["items"]}

    print(f"═══ R14 评分报告 · {case_id} · 作答={mode} ═══\n")
    report = await score_session(rubric, answer, exam, TRANSCRIPT,
                                 build_report(answer, mode), common)
    print(render(report))
    out = ROOT / "data" / "tests" / f"scoring_report_{case_id}_{mode}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n（完整 JSON 已写入 {out.relative_to(ROOT)}）")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="EN01")
    ap.add_argument("--report", default="good", choices=["good", "empty", "partial"])
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(run(args.case, args.report))


if __name__ == "__main__":
    main()
