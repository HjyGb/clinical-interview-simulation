#!/usr/bin/env python3
"""P4 — R05–R14 LLM judging: does it discriminate, and does it demand evidence?

This is the quantitative check for the LLM half of the rubric. It needs the real LLM.

Two submissions for the same case, same transcript:

    良          作答取自该例参考答案（学员"写对了"）
    空          不作答（学员"什么都没写"）

Assertions:
  D1 判别力   R06–R10 上，良 > 空（否则评分器分不出好坏，等于没评）
  D2 证据强制 任何 >0 的项都必须带 evidence_quote
  D3 无假分   没有调用失败时不应出现 NE；出现 NE 也要如实标出（不折成 0 分）
  D4 定锚     良作答的诊断条目应明显高于空作答

设计文档 §11 的 V8（判别力）。人工一致性那几条（V6/V7）要等医院，这里不做。

Usage:
    python scripts/run_scoring_llm_tests.py                 # EN01
    python scripts/run_scoring_llm_tests.py --case PE01
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

logger.remove()  # 静音，只看结论
for _n in ("sqlalchemy", "sqlalchemy.engine"):
    logging.getLogger(_n).disabled = True
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from scoring.aggregate import NE, total  # noqa: E402
from scoring.llm_judge import LLM_ITEMS, judge_session  # noqa: E402

REPORT_ITEMS = ("R06", "R07", "R08", "R09", "R10")


def load(case_id: str, kind: str) -> dict:
    return json.loads((ROOT / "data" / "cases" / f"{case_id.lower()}.{kind}.json")
                      .read_text(encoding="utf-8"))


def good_report(answer_key: dict) -> dict:
    """学员"写对了"的作答：用该例参考答案的要点填进**那五个**作答框。

    字段名必须与 scoring.llm_judge.ANSWER_FIELDS 一致——写错了评测会静默变成"作答为空"，
    看起来像评分器失灵，其实是夹具写错了（这个坑踩过一次）。
    """
    return {
        "primary_diagnosis": answer_key["diagnosis"]["content"],
        "diagnosis_reason": answer_key["diagnosis_reason"]["content"],
        "differential_diagnosis": "；".join(
            f"{d['label']}：{d['reason']}" for d in answer_key.get("differentials", [])),
        "immediate_plan": (answer_key["plan"]["immediate"] or {}).get("content") or "",
        "staged_plan": "；".join(
            (answer_key["plan"][k] or {}).get("content") or ""
            for k in ("definitive", "review")),
    }


# 合成对话：只为给"对话类"条目（R05/R11–R14）提供可评的材料。
# **刻意写成与病例无关的中性措辞**——否则换一个病例跑，对话条目会因为对不上而集体低分，
# 让人误以为是评分器的问题。断言（D1–D4）本来也只针对报告类条目。
TRANSCRIPT = [
    {"role": "student", "content": "您好，我是今天的接诊医生。请问您这次是哪里不舒服？", "round_num": 1},
    {"role": "patient", "content": "（患者叙述本次就诊的起因与经过）", "round_num": 1},
    {"role": "student", "content": "明白。这种情况持续多久了？有没有加重？", "round_num": 2},
    {"role": "patient", "content": "（患者补充时间与变化）", "round_num": 2},
    {"role": "student", "content": "请提供相关检查的结果。", "round_num": 3},
    {"role": "exam", "content": "（本例相关资料中记录的检查结果）", "round_num": 3},
    {"role": "student", "content": "我看了检查结果。我先跟您说一下目前主要是什么问题，以及我们打算怎么处理；", "round_num": 4},
    {"role": "student", "content": "但具体方案还要看治疗中的实际情况，现在不能给您打包票。", "round_num": 4},
    {"role": "student", "content": "您刚才提到的那点担心我听明白了，这个顾虑是合理的。", "round_num": 5},
    {"role": "student", "content": "接下来要注意的是：如果出现某些情况，请及时来复诊，不要拖。", "round_num": 5},
]


def score_of(scores) -> dict:
    return {s.item_id: s for s in scores}


async def run(case_id: str) -> int:
    rub = load(case_id, "rubric")
    answer = load(case_id, "answer")
    common = {i["id"]: i for i in json.loads(
        (ROOT / "data" / "scoring" / "rubric_common.json").read_text(encoding="utf-8"))["items"]}

    print(f"P4 LLM 判定 — {case_id}（{len(LLM_ITEMS)} 条 × 2 份作答）\n")

    good = score_of(await judge_session(rub, common, answer, good_report(answer), TRANSCRIPT))
    empty = score_of(await judge_session(rub, common, answer, {}, TRANSCRIPT))

    def quote_of(s) -> str:
        return next((a.evidence_quote for a in s.sub_anchors if a.evidence_quote), "")

    print(f"{'项':5} {'良':4} {'空':4}  良作答的证据原话 / 说明")
    for rid in LLM_ITEMS:
        g, e = good.get(rid), empty.get(rid)
        if g is None or e is None:
            continue
        detail = quote_of(g) or g.note or ""
        print(f"{rid:5} {g.score:<4} {e.score:<4}  {detail[:56]}")

    results = []
    def check(name, ok, detail=""):
        results.append((name, ok))
        print(f"  {'✅' if ok else '❌'} {name}" + ("" if ok else f"   ← {detail}"))

    print()
    g_report = sum(good[r].score for r in REPORT_ITEMS)
    e_report = sum(empty[r].score for r in REPORT_ITEMS)
    check(f"D1 判别力：良作答(报告条) {g_report}/10 > 空作答 {e_report}/10", g_report > e_report)

    bad_evidence = [r for r in LLM_ITEMS
                    if good[r].score > 0 and not quote_of(good[r])]
    check("D2 证据强制：良作答每个 >0 的项都引用了原话", not bad_evidence, str(bad_evidence))

    bad_evidence_e = [r for r in LLM_ITEMS
                      if empty[r].score > 0 and not quote_of(empty[r])]
    check("D2 证据强制：空作答每个 >0 的项都引用了原话", not bad_evidence_e, str(bad_evidence_e))

    ne_good = [r for r in LLM_ITEMS if good[r].status == NE]
    check("D3 无调用失败（有 NE 会列在下方）", not ne_good, str(ne_good))

    check(f"D4 诊断理由：良 {good['R07'].score} > 空 {empty['R07'].score}",
          good["R07"].score > empty["R07"].score)

    # ── 安全通道：好作答不该被误判，违规作答必须被抓到 ──────────
    from scoring.safety import check_critical_errors
    good_safety = await check_critical_errors(rub, good_report(answer), TRANSCRIPT)
    bad_safety = await check_critical_errors(rub, {
        "primary_diagnosis": answer["diagnosis"]["content"],
        "immediate_plan": "先开一周口服抗生素，吃完再观察，这颗牙本身不用处理。",
        "staged_plan": "这个牙必须做根管治疗，我保证一定能治好。",
    }, TRANSCRIPT)

    print(f"\n  安全通道：良作答命中 {len(good_safety.hits)} 条；"
          f"违规作答命中 {len(bad_safety.hits)} 条")
    check("D5 良作答不被误判为安全错误", len(good_safety.hits) == 0,
          str([f.error for f in good_safety.hits]))
    check("D5 违规作答被标记（抗生素替代病因处理 / 承诺必然能保住）",
          len(bad_safety.hits) >= 1, str([f.error for f in bad_safety.flags]))
    check("D5 命中的标记都带学员原话", all(f.evidence_quote for f in bad_safety.hits))
    for f in bad_safety.hits:
        print(f"      命中：{f.error}  ← 学员原话：{f.evidence_quote[:40]}")

    print(f"\n  良作答合计 {total(list(good.values()))}/20   空作答合计 {total(list(empty.values()))}/20")
    passed = sum(1 for _, ok in results if ok)
    print(f"\nP4 LLM 判定：{passed}/{len(results)} 通过")
    return 0 if passed == len(results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="EN01")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(asyncio.run(run(args.case)))


if __name__ == "__main__":
    main()
