"""R05–R14：交给 LLM 判，但**只判锚点、抄证据**，分数怎么算由代码决定。

设计见 docs/scoring-system-design.md §5.2、§5.3。

分工的理由：LLM 擅长"这句话是不是在解释病因"这类语义判断，不擅长校准和算术。
所以这里让模型回答一个**窄问题**——「对照这条锚点，学员该得 0/1/2，证据是哪句原话」——
然后由 `aggregate.direct_score` 强制证据、定位分数。

三条纪律：
  1. **没抄原话的给分一律归零**（`direct_score` 里做，不靠模型自觉）。
  2. **失败必须像失败**：调用挂了返回 `NE`（不可评价），**绝不返回 0 分**——
     0 分是"学员没做到"，NE 是"系统没评成"，两者混在一起就是 CLAUDE.md 里记的
     "评估失败静默渲染成 0 分"。医院也明说「系统失败…不得转换为学员失分」。
  3. **一次只判一条**：把 14 条塞进一次调用，模型会互相串味（"诊断对了"顺手给理由加分）。
"""

import asyncio
import json
import re
from pathlib import Path

from loguru import logger

from agent.llm_client import chat
from app.config import settings
from scoring.aggregate import NE, ItemScore, SubAnchorResult, direct_score, unscored
from scoring.evidence import quote_is_from

PROMPT: str | None = None
PROMPT_PATH = Path(__file__).resolve().parent.parent / "agent" / "prompts" / "scoring" / "r14_item.txt"

# R05–R14：不由代码判的那 10 条
LLM_ITEMS = ("R05", "R06", "R07", "R08", "R09", "R10", "R11", "R12", "R13", "R14")

# 证据主要在哪：锚点里写「须在患者对话中体现」的，证据在对话；其余在作答
REPORT_ITEMS = frozenset({"R06", "R07", "R08", "R09", "R10"})

FOCUS_DIALOGUE = ("**本条看的是对话。** 证据要出自学员对患者说过的话，"
                  "作答框里写了不算——医院原文：「诊疗框写了计划，不代表 R11 已经完成」。")
FOCUS_REPORT = ("**本条看的是作答。** 证据要出自学员提交的处置/诊断框，"
                "对话里提到过但没写进作答，不算完成。")


def _load_prompt() -> str:
    global PROMPT
    if PROMPT is None:
        PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
    return PROMPT


def _render_answer_key(answer_key: dict) -> str:
    """把隐藏参考答案排成人能读的清单。只给该例真实有的字段，不补空。"""
    if not answer_key:
        return "（本病例无参考答案资料）"
    lines = []
    diag = answer_key.get("diagnosis") or {}
    reason = answer_key.get("diagnosis_reason") or {}
    if diag.get("content"):
        lines.append(f"标准诊断：{diag['content']}")
    if reason.get("content"):
        lines.append(f"诊断理由：{reason['content']}")
    for d in answer_key.get("differentials", []):
        lines.append(f"鉴别诊断·{d.get('label', '')}：{d.get('reason', '')}")
    for slot, label in (("immediate", "近期处理"), ("definitive", "确定性处理"), ("review", "复评维护")):
        v = (answer_key.get("plan") or {}).get(slot) or {}
        if v.get("content"):
            lines.append(f"{label}：{v['content']}")
    for slot, label in (("explain", "病情与计划解释（对患者）"), ("warn", "注意事项与求助（对患者）")):
        v = (answer_key.get("communication_reference") or {}).get(slot) or {}
        if v.get("content"):
            lines.append(f"{label}：{v['content']}")
    return "\n".join(lines) if lines else "（本病例无参考答案资料）"


def _render_report(student_report: dict | None) -> str:
    """渲染学员作答。**字段就是那五项**（2026-10-12 定，见设计文档 §4.3）。

    医院文档只出现过「学员四项作答」这五个字、从没列举是哪四项；我们按 R06–R10
    加教师参考反推出五项，并按此定稿。改这里等于改答卷形态——前端 DiagnosisForm 要同步。
    """
    if not student_report:
        return "（学员未提交作答）"
    fields = [
        ("primary_diagnosis", "① 主诊断（部位 + 确定性）"),
        ("diagnosis_reason", "② 诊断理由"),
        ("differential_diagnosis", "③ 鉴别诊断（含区分依据）"),
        ("immediate_plan", "④ 近期处理"),
        ("staged_plan", "⑤ 阶段计划与复评"),
    ]
    lines = [f"{label}：{student_report.get(key) or '（空）'}" for key, label in fields]
    return "\n".join(lines)


# 答卷字段名（唯一权威）。前端 DiagnosisForm、API schema、评分渲染都从这里对齐。
ANSWER_FIELDS = ("primary_diagnosis", "diagnosis_reason", "differential_diagnosis",
                 "immediate_plan", "staged_plan")


def _render_conversation(history: list[dict]) -> str:
    if not history:
        return "（无对话记录）"
    lines = []
    for m in history:
        role = {"student": "学员", "patient": "患者", "exam": "检查结果"}.get(m.get("role"), "系统")
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"[第{m.get('round_num', '?')}轮] {role}：{content}")
    return "\n".join(lines) if lines else "（无对话记录）"


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


async def judge_item(
    item: dict,
    common: dict | None,
    answer_key: dict,
    student_report: dict | None,
    history: list[dict],
) -> ItemScore:
    """判一条 R05–R14。任何失败都返回 NE，绝不返回 0 分。"""
    rid = item["id"]
    common = common or {}
    focus = FOCUS_REPORT if rid in REPORT_ITEMS else FOCUS_DIALOGUE

    prompt = _load_prompt().format(
        item_id=rid,
        item_name=item.get("name", ""),
        item_anchor=item.get("anchor") or "（本例未提供锚点）",
        item_partial=common.get("partial_1", "（见册前共同锚点）"),
        item_zero=common.get("zero_0", "（见册前共同锚点）"),
        judging_focus=focus,
        answer_key=_render_answer_key(answer_key),
        student_report=_render_report(student_report),
        conversation=_render_conversation(history),
    )

    report_blob = _render_report(student_report)
    dialogue_blob = _render_conversation(history)
    # 报告类条目只能引作答，对话类条目只能引对话
    source = report_blob if rid in REPORT_ITEMS else dialogue_blob

    try:
        raw = await chat([{"role": "user", "content": prompt}],
                         model=settings.llm_model_pro, temperature=0.0, max_tokens=1024)
        data = _parse_json(raw)
        score = int(data.get("score", 0))
        quote = (data.get("evidence_quote") or "").strip()

        result = direct_score(
            rid, score,
            evidence_quote=quote,
            evidence_ref=data.get("evidence_ref") or "",
            note=(data.get("justification") or "").strip(),
        )

        # 代码兜底：证据必须真的出自该条该看的地方，否则归零。
        if result.score > 0 and not quote_is_from(quote, source):
            where = "学员作答" if rid in REPORT_ITEMS else "对话记录"
            logger.warning(f"[Scoring] {rid} 的证据不出自{where}，归零：{quote[:40]!r}")
            return ItemScore(
                item_id=rid, score=0,
                sub_anchors=[SubAnchorResult(n=1, met=False, downgraded=True)],
                note=f"证据不出自{where} → 归零（模型引用的是：{quote[:30]}）",
            )
        return result
    except Exception as e:
        # 失败 ≠ 0 分。返回 NE，报告里单列，不折算成学员失分。
        logger.error(f"[Scoring] {rid} 判定失败，标记 NE：{e}")
        return unscored(rid, NE, f"评分调用失败，无法评价：{type(e).__name__}")


async def judge_session(
    rubric: dict,
    common_items: dict[str, dict],
    answer_key: dict,
    student_report: dict | None,
    history: list[dict],
    concurrency: int = 4,
    items: tuple[str, ...] = LLM_ITEMS,
) -> list[ItemScore]:
    """判 R05–R14（或指定的子集）。

    并发跑但限流：一条失败不影响其他条（各自独立返回 NE）。
    """
    wanted = [it for it in rubric.get("items", []) if it["id"] in items]
    sem = asyncio.Semaphore(concurrency)

    async def one(item: dict) -> ItemScore:
        async with sem:
            return await judge_item(item, common_items.get(item["id"]), answer_key,
                                    student_report, history)

    return list(await asyncio.gather(*(one(it) for it in wanted)))
