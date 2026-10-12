"""把 14 条拼成一份完整评分报告。

     R01–R04  纯 Python（deterministic）
     R05–R14  LLM（llm_judge，逐条）
     NE/NA/SKIPPED_SAFETY  代码判定（本模块）
     安全通道 独立并行（safety）

三条从设计文档带过来的硬规则：
  - **不取平均、不给综合分**（§9）：原始分 + 两个视图，各自呈现。
  - **安全错误独立输出、不参与任何求和**（§8.3）。
  - **NE/NA 不变成 0 分**，同时报告可评上限（§8.1）。

视图（§9，正好对上"两条评估线"）：
     临床能力  病史采集 R01–R03 · 检查运用 R04–R05 · 诊断与推理 R06–R08 · 处理与计划 R09–R10
     沟通与人文 解释与告知 R11–R12 · 以患者为中心 R13–R14
"""

import asyncio
import json
from pathlib import Path

from loguru import logger

from scoring.aggregate import (
    MAX_PER_ITEM, NA, NE, SCORED, SKIPPED_SAFETY, ItemScore, report_ceiling, total, unscored,
)
from scoring.deterministic import judge_r01_r04, required_exam_ids
from scoring.llm_judge import LLM_ITEMS, judge_session
from scoring.safety import SafetyReport, check_critical_errors, detect_safety_stop

# 册前共同 1/0 锚点 + 全局规则。它是**全局**的，不属于任何一例，所以不从病例表取。
COMMON_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "scoring" / "rubric_common.json"
_common_cache: dict[str, dict] | None = None


def load_common_rubric() -> dict[str, dict]:
    """{item_id: {partial_1, zero_0, …}}，带缓存。文件缺失时告警但不炸——只是 1/0 锚点不可用。"""
    global _common_cache
    if _common_cache is None:
        try:
            raw = json.loads(COMMON_PATH.read_text(encoding="utf-8"))
            _common_cache = {i["id"]: i for i in raw.get("items", [])}
        except FileNotFoundError:
            logger.warning(f"[Scoring] 未找到 {COMMON_PATH}；1/0 分共同锚点不可用，不影响判分")
            _common_cache = {}
    return _common_cache

CODE_ITEMS = ("R01", "R02", "R03", "R04")
ALL_ITEMS = [f"R{i:02d}" for i in range(1, 15)]

# 视图分组（设计文档 §9）。改这里就能改报告的呈现，不用动评分逻辑。
VIEWS = [
    ("临床能力", [
        ("病史采集", ("R01", "R02", "R03")),
        ("检查运用", ("R04", "R05")),
        ("诊断与推理", ("R06", "R07", "R08")),
        ("处理与计划", ("R09", "R10")),
    ]),
    ("沟通与人文", [
        ("解释与告知", ("R11", "R12")),
        ("以患者为中心", ("R13", "R14")),
    ]),
]


def _as_trace(messages: list[dict]) -> list[dict]:
    """Message rows → the trace shape the deterministic judge expects."""
    return [
        {
            "role": m.get("role"),
            "content": m.get("content") or "",
            "round_num": m.get("round_num"),
            "intent": m.get("intent"),
            "disclosed": m.get("disclosed") or [],
        }
        for m in messages
    ]


def _apply_not_applicable(items: dict[str, ItemScore], rubric: dict, exam_data: dict | None) -> None:
    """R04：本例没有 [关键] 检查项时，本条**不适用**（NA），不是 0 分。"""
    if not required_exam_ids(exam_data) and not any(
            it["id"] == "R04" and it.get("refs") for it in rubric.get("items", [])):
        items["R04"] = unscored("R04", NA, "本例无 [关键] 检查项，本条目不适用")


def _apply_safety_stop(items: dict[str, ItemScore], safety: SafetyReport) -> None:
    """安全优先例识别到危险并转诊后：未完成的条目标 SKIPPED_SAFETY，不按 0 分计。

    医院原文：「允许停止非必要问诊、影像和完整常规作答，及时转急救。不能以未跑完清单扣分；
    无机会观察的常规项目标 NA/NE 并人工确认。」
    —— 我们无法精确知道学员"本来会做什么"，所以采取**对学员有利**的读法：
    已判 0 的条目转为 SKIPPED_SAFETY，并在报告里要求人工确认。
    """
    if not safety.stopped_early:
        return
    for rid, score in items.items():
        if score.status == SCORED and score.score == 0:
            items[rid] = unscored(
                rid, SKIPPED_SAFETY,
                "安全优先例：已识别危险并转诊，本条未有机会完成（需人工确认）")


def _view_report(items: dict[str, ItemScore]) -> list[dict]:
    views = []
    for view_name, groups in VIEWS:
        g_out = []
        for group_name, rids in groups:
            scored = [items[r] for r in rids if r in items and items[r].counted]
            g_out.append({
                "name": group_name,
                "items": [items[r].item_id for r in rids if r in items],
                "score": sum(s.score for s in scored),
                "max": len(scored) * MAX_PER_ITEM,
            })
        views.append({"name": view_name, "groups": g_out})
    return views


def _serialize(items: dict[str, ItemScore], rubric: dict) -> list[dict]:
    names = {it["id"]: it.get("name", "") for it in rubric.get("items", [])}
    out = []
    for rid in ALL_ITEMS:
        s = items.get(rid)
        if s is None:
            continue
        out.append({
            "id": s.item_id,
            "name": names.get(rid, ""),      # 报告要能直接显示"R07 诊断理由"，前端不该自己维护这张表
            "score": s.score,
            "max_score": s.max_score,
            "status": s.status,
            "note": s.note,
            "evidence": [
                {"n": a.n, "met": a.met, "quote": a.evidence_quote,
                 "ref": a.evidence_ref, "downgraded": a.downgraded}
                for a in s.sub_anchors
            ],
        })
    return out


async def score_session(
    rubric: dict,
    answer_key: dict,
    exam_data: dict | None,
    messages: list[dict],
    student_report: dict | None,
    common_items: dict[str, dict] | None = None,
) -> dict:
    """Run the whole R01–R14 assessment. Returns a JSON-ready report dict."""
    trace = _as_trace(messages)
    items: dict[str, ItemScore] = {}
    common_items = common_items if common_items is not None else load_common_rubric()

    # ── R01–R04：纯代码 ────────────────────────────────────────
    items.update(judge_r01_r04(rubric, exam_data, trace))
    _apply_not_applicable(items, rubric, exam_data)

    # ── R05–R14：LLM（逐条，各自独立失败）──────────────────────
    for s in await judge_session(rubric, common_items or {}, answer_key, student_report, trace):
        items[s.item_id] = s

    # ── 安全通道：并行、独立，绝不进分数 ───────────────────────
    safety, stopped = await asyncio.gather(
        check_critical_errors(rubric, student_report, trace),
        detect_safety_stop(rubric, trace),
    )
    safety.stopped_early, safety.stop_evidence = stopped
    _apply_safety_stop(items, safety)

    ordered = [items[r] for r in ALL_ITEMS if r in items]
    ceiling = report_ceiling(ordered)

    # 会话里出现过 question_type="error" 说明上游挂过——单列，不折算成学员失分
    system_errors = sum(1 for m in trace if m.get("intent") == "error")
    if system_errors:
        logger.warning(f"[Scoring] 会话中上游失败 {system_errors} 次（不折算为学员失分）")

    return {
        "items": _serialize(items, rubric),
        "views": _view_report(items),
        "total": ceiling,
        "safety": {
            "flags": [
                {"index": f.index, "error": f.error, "hit": f.hit,
                 "evidence_quote": f.evidence_quote, "evidence_ref": f.evidence_ref,
                 "checked": f.checked}
                for f in safety.flags
            ],
            "hits": len(safety.hits),
            "unchecked": len(safety.unchecked),
            "requires_review": safety.requires_review,
            "safety_priority_case": bool(safety.stopped_early),
            "stop_evidence": safety.stop_evidence,
        },
        "system_errors": system_errors,
        # 明确写出来，免得以后有人又去算平均
        "scoring_note": "原始分为各项之和；安全标记独立，不参与求和，不与沟通表现互相抵消。",
    }
