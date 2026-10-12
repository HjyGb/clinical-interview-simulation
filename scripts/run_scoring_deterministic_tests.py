#!/usr/bin/env python3
"""P2+P3 — deterministic scoring tests: sub-anchor decomposition, aggregation, R01–R04.

No LLM, no network, no DB. Pure logic against the **real 5-case rubric files**, so a
change in the extracted data shows up here too.

Three groups:
  A 子锚点分解    R01–R04 按参照 ID 拆；R05–R14 不拆（整条锚点=一个判据）
  B 聚合与证据强制  全中 2 / 部分 1 / 全未中 0；没有证据原话的"命中"降级
  C R01–R04 判定  用合成轨迹断言得分，覆盖 OPEN 兜底、子项请求、缺项

对标 scripts/run_exam_subitem_tests.py（同为纯 Python 确定性测试）。

Usage:
    python scripts/run_scoring_deterministic_tests.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from scoring.aggregate import (  # noqa: E402
    SubAnchorResult, aggregate, direct_score, enforce_evidence, score_item,
)
from scoring.deterministic import (  # noqa: E402
    elicited_fact_ids, judge_r01_r04, requested_exam_ids, required_exam_ids,
)
from scoring.sub_anchors import CODE_JUDGED, JUDGE, REQUEST, decompose  # noqa: E402

CASES = ["EN01", "PE01", "PR01", "MU01", "SU01"]

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail if not ok else ""))
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}" + (f"   ← {detail}" if not ok else ""))


def load(case_id: str, kind: str) -> dict:
    return json.loads((ROOT / "data" / "cases" / f"{case_id.lower()}.{kind}.json")
                      .read_text(encoding="utf-8"))


# ── 合成轨迹 ───────────────────────────────────────────────────────
def trace_for(facts=(), exams=(), open_round: str | None = None) -> list[dict]:
    """Build a conversation trace. Each fact/exam is one student turn + one reply turn."""
    t: list[dict] = []
    rnd = 0
    for f in facts:
        rnd += 1
        t.append({"role": "student", "content": f"请说说{f}相关的情况。", "round_num": rnd,
                  "intent": "targeted", "disclosed": None})
        t.append({"role": "patient", "content": "……", "round_num": rnd,
                  "intent": "targeted", "disclosed": [f]})
    if open_round is not None:
        rnd += 1
        t.append({"role": "student", "content": "请从头说说你的情况。", "round_num": rnd,
                  "intent": "open", "disclosed": None})
        t.append({"role": "patient", "content": "……", "round_num": rnd,
                  "intent": "open", "disclosed": []})   # 轨迹为空 —— 模拟漏记
    for e in exams:
        rnd += 1
        t.append({"role": "student", "content": "请提供该检查结果。", "round_num": rnd,
                  "intent": "exam", "disclosed": None})
        t.append({"role": "exam", "content": "……", "round_num": rnd,
                  "intent": "exam", "disclosed": [e]})
    return t


# ── A 子锚点分解 ───────────────────────────────────────────────────
def group_a() -> None:
    print("A. 子锚点分解")
    r01 = {"id": "R01", "anchor": "……", "refs": ["H01", "H02"]}
    subs = decompose(r01)
    check("A1 R01 拆成 2 个子锚点", len(subs) == 2, f"得到 {len(subs)}")
    check("A1 R01 子锚点类型=elicit", all(s["kind"] == "elicit" for s in subs))
    check("A1 R01 每个子锚点挂 1 个 ref",
          all(len(s["refs"]) == 1 for s in subs))

    r04 = {"id": "R04", "anchor": "……", "refs": ["E01", "E02", "E03"]}
    subs = decompose(r04)
    check("A2 R04 拆成 3 个 request 子锚点",
          len(subs) == 3 and all(s["kind"] == REQUEST for s in subs))

    r06 = {"id": "R06", "anchor": "给出合理部位和诊断确定性……", "refs": ["D01"]}
    subs = decompose(r06)
    check("A3 R06 不拆分（1 个整体判据）",
          len(subs) == 1 and subs[0]["kind"] == JUDGE)
    check("A3 R06 判据=整条锚点原文", subs[0]["criterion"] == r06["anchor"])

    check("A4 无参照的代码判项 → 空子锚点", decompose({"id": "R01", "refs": []}) == [])
    check("A5 CODE_JUDGED 恰好是 R01–R04", set(CODE_JUDGED) == {"R01", "R02", "R03", "R04"})


# ── B 聚合与证据强制 ───────────────────────────────────────────────
def group_b() -> None:
    print("B. 聚合与证据强制")
    R = lambda n, met, q="q": SubAnchorResult(n=n, met=met, evidence_quote=q)  # noqa: E731

    check("B1 全中 → 2", aggregate([R(1, True), R(2, True)]) == 2)
    check("B2 部分中 → 1", aggregate([R(1, True), R(2, False)]) == 1)
    check("B3 全未中 → 0", aggregate([R(1, False), R(2, False)]) == 0)
    check("B4 空子锚点 → 0", aggregate([]) == 0)

    no_q = SubAnchorResult(n=1, met=True, evidence_quote="")
    enforce_evidence([no_q])
    check("B5 命中但无证据 → 降级为未命中", no_q.met is False and no_q.downgraded is True)
    s = score_item("R01", [SubAnchorResult(n=1, met=True, evidence_quote=""),
                           SubAnchorResult(n=2, met=True, evidence_quote="问了疼不疼")])
    check("B5 降级后聚合为 1", s.score == 1, f"得到 {s.score}")
    check("B5 报告里注明降级", "降级" in s.note)

    check("B6 direct_score 有证据 → 保留", direct_score("R06", 2, "学员原话").score == 2)
    check("B7 direct_score 无证据 → 归零", direct_score("R06", 2, "").score == 0)
    try:
        direct_score("R06", 3)
        check("B8 越界分数报错", False, "未抛异常")
    except ValueError:
        check("B8 越界分数报错", True)


# ── C R01–R04 判定 ─────────────────────────────────────────────────
def group_c(case_id: str) -> None:
    print(f"C. R01–R04 判定 — {case_id}")
    rub = load(case_id, "rubric")
    exam = load(case_id, "exam")
    key = required_exam_ids(exam)
    check(f"C0 {case_id} 必做检查 = level==关键 的 E 项", len(key) >= 1, "该例无关键检查项")
    # 必做项必须与该例 rubric 里 R04 的参照一致（这是 S1 的结论性发现）
    r04_refs = next((i["refs"] for i in rub["items"] if i["id"] == "R04"), [])
    check(f"C0 {case_id} R04 锚点参照 == 关键 E 项", set(r04_refs) <= set(key),
          f"R04 refs={r04_refs} 关键={key}")

    # 满分路径
    full = judge_r01_r04(rub, exam, trace_for(facts=[f"H{i:02d}" for i in range(1, 8)], exams=key))
    check(f"C1 {case_id} 全问到 → R01–R04 全 2",
          all(full[r].score == 2 for r in ("R01", "R02", "R03", "R04")),
          str({r: full[r].score for r in ("R01", "R02", "R03", "R04")}))

    # 空会话
    none = judge_r01_r04(rub, exam, [])
    check(f"C2 {case_id} 空会话 → 全 0",
          all(none[r].score == 0 for r in ("R01", "R02", "R03", "R04")))

    # 只问出 H01
    part = judge_r01_r04(rub, exam, trace_for(facts=["H01"]))
    check(f"C3 {case_id} 只问到 H01 → R01=1、其余 0",
          part["R01"].score == 1 and part["R02"].score == 0
          and part["R03"].score == 0 and part["R04"].score == 0,
          str({r: part[r].score for r in ("R01", "R02", "R03", "R04")}))

    # 开放式问句：门控放行 H01–H04，即使披露轨迹漏记也要认
    opened = judge_r01_r04(rub, exam, trace_for(open_round="yes"))
    check(f"C4 {case_id} OPEN 兜底（轨迹漏记）→ R01/R02 满分、R03 仍 0",
          opened["R01"].score == 2 and opened["R02"].score == 2 and opened["R03"].score == 0,
          str({r: opened[r].score for r in ("R01", "R02", "R03")}))

    # 子项请求也算申请了该 E 项
    if key:
        sub = judge_r01_r04(rub, exam, trace_for(exams=[f"{key[0]}.cold"]))
        check(f"C5 {case_id} 子项请求 {key[0]}.cold 记为该 E 项已申请",
              sub["R04"].sub_anchors and sub["R04"].sub_anchors[0].met is True)
        check(f"C5 {case_id} 宽召回复核信息被保留", "子项请求" in sub["R04"].note)

    # 补充项不算必做
    supplemental = [eid for eid, e in (exam.get("exams") or {}).items()
                    if (e or {}).get("level") == "补充"]
    if supplemental:
        s = judge_r01_r04(rub, exam, trace_for(exams=supplemental))
        check(f"C6 {case_id} 只申请 [补充] 项 → R04 不满分", s["R04"].score < 2,
              f"申请了 {supplemental}，得到 {s['R04'].score}")


def group_c_purity() -> None:
    print("C. 轨迹解析的边界")
    t = [{"role": "exam", "content": "", "disclosed": ["E02.cold", "E01"]},
         {"role": "patient", "content": "", "intent": "targeted", "disclosed": ["H01", "E02"]}]
    check("D1 检查子项键折算成 E 项", requested_exam_ids(t) == {"E01", "E02"})
    check("D2 患者事实只认 H/P 编号，E 键不混入", elicited_fact_ids(t) == {"H01"})
    check("D3 open 且轨迹为空 → 补 H01–H04",
          elicited_fact_ids([{"role": "patient", "intent": "open", "disclosed": []}])
          == {"H01", "H02", "H03", "H04"})
    check("D4 targeted 且轨迹为空 → 不补（不许猜）",
          elicited_fact_ids([{"role": "patient", "intent": "targeted", "disclosed": []}]) == set())


def group_e() -> None:
    print("E. 不可评价（NE/NA）与渲染")
    from scoring.aggregate import (  # noqa: E402
        ItemScore, NE, NA, SKIPPED_SAFETY, report_ceiling, total, unscored,
    )
    from scoring.llm_judge import (  # noqa: E402
        _render_answer_key, _render_conversation, _render_report, LLM_ITEMS,
    )

    check("E1 R05–R14 共 10 条", len(LLM_ITEMS) == 10)

    ok = ItemScore("R01", 2)
    ne = unscored("R07", NE, "调用失败")
    check("E2 NE 不是 0 分，也不计入合计", total([ok, ne]) == 2 and ne.counted is False)
    check("E3 NE 保留状态供报告单列", ne.status == NE and "调用失败" in ne.note)

    ceil = report_ceiling([ok, ne, unscored("R04", NA, "本例无关键检查项")])
    check("E4 可评上限按已评条目算，不是恒定 28",
          ceil["raw_max_counted"] == 2 and ceil["raw_max_nominal"] == 6,
          str(ceil))
    check("E5 报告列出被排除的条目", ceil["excluded"].get("ne") == ["R07"]
          and ceil["excluded"].get("na") == ["R04"], str(ceil["excluded"]))

    try:
        unscored("R01", "whatever", "")
        check("E6 非法状态报错", False, "未抛异常")
    except ValueError:
        check("E6 非法状态报错", True)
    check("E6 SKIPPED_SAFETY 是合法状态", unscored("R04", SKIPPED_SAFETY, "").status == SKIPPED_SAFETY)

    key = load("EN01", "answer")
    rendered = _render_answer_key(key)
    check("E7 参考答案渲染含标准诊断原文", key["diagnosis"]["content"] in rendered)
    check("E8 空作答不崩", "未提交作答" in _render_report(None))
    check("E9 对话渲染带角色与轮次",
          "[第2轮] 学员：" in _render_conversation(
              [{"role": "student", "content": "疼吗", "round_num": 2}]))


def group_f() -> None:
    print("F. 安全通道（独立于分数）")
    from scoring.safety import (  # noqa: E402
        SafetyFlag, SafetyReport, critical_errors_of, is_safety_priority_case,
    )
    from scoring.runner import _apply_safety_stop  # noqa: E402
    from scoring.aggregate import SKIPPED_SAFETY, ItemScore, unscored  # noqa: E402

    en01 = load("EN01", "rubric")
    su05 = json.loads((ROOT / "data" / "staging" / "su05.rubric.new.json").read_text(encoding="utf-8"))

    check("F1 EN01 有两条关键错误", len(critical_errors_of(en01)) == 2,
          str(critical_errors_of(en01)))
    check("F2 常规例不是安全优先例", is_safety_priority_case(en01) is False)
    check("F2 SU05 是安全优先例", is_safety_priority_case(su05) is True)

    clean = SafetyReport(flags=[SafetyFlag(1, "e1", hit=False, checked=True)])
    check("F3 全部复核未命中 → 不需复核", clean.requires_review is False)

    hit = SafetyReport(flags=[SafetyFlag(1, "e1", hit=True, checked=True)])
    check("F3 命中 → 需复核", hit.requires_review is True)

    unchecked = SafetyReport(flags=[SafetyFlag(1, "e1", hit=False, checked=False)])
    check("F4 未复核 → 也需复核（不是「安全通过」）", unchecked.requires_review is True)

    # 安全早停：已判 0 的条目不按 0 计
    items = {"R06": ItemScore("R06", 0), "R07": ItemScore("R07", 2),
             "R04": unscored("R04", "na", "不适用")}
    _apply_safety_stop(items, SafetyReport(stopped_early=True))
    check("F5 早停后 0 分项转为 SKIPPED_SAFETY", items["R06"].status == SKIPPED_SAFETY)
    check("F5 已得分项不受影响", items["R07"].score == 2 and items["R07"].status == "scored")
    check("F5 原本 NA 的项保持 NA", items["R04"].status == "na")

    items2 = {"R06": ItemScore("R06", 0)}
    _apply_safety_stop(items2, SafetyReport(stopped_early=False))
    check("F5 未早停则不改写分数", items2["R06"].status == "scored")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    group_a()
    group_b()
    for cid in CASES:
        group_c(cid)
    group_c_purity()
    group_e()
    group_f()

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print("-" * 70)
    print(f"确定性评分测试：{passed}/{total} 通过 ({100.0 * passed / total:.1f}%)")
    if passed != total:
        print("\n失败项：")
        for name, ok, detail in _results:
            if not ok:
                print(f"  ❌ {name}  {detail}")
        sys.exit(1)
    print("无失败项 ✅")


if __name__ == "__main__":
    main()
