"""Patient Agent — orchestrates the 3-step response pipeline.

Pipeline: Fact Select → Disclosure Gate → Response Generate
    fact_selector (lite)   → which facts is the student asking about?
    disclosure    (pure py)→ which of them may the patient use this turn?
    generator     (pro)    → say it in character, streaming

The old 4th step (post-hoc fact verification) was removed: it ran after tokens
had already been streamed, so it could log a violation but never retract one.
The real defence is upstream — the data boundary (no D/DD/T/G/R in the case
data) plus this gate.
"""

from collections.abc import AsyncIterator

from loguru import logger

from agent import exam_module
from agent.disclosure import gate, to_generator_facts
from agent.fact_selector import ERROR_QUESTION_TYPE, EXAM_QUESTION_TYPE, select_facts
from agent.persona import DEFAULT_PERSONA, PersonaConfig
from agent.response_generator import generate_response


def _summarize_history(history: list[dict], max_msgs: int = 6) -> str:
    """Format recent turns for the selector.

    The selector needs enough context to resolve references ("刚才说的那个…"),
    so this keeps more than the old intent classifier did.
    """
    if not history:
        return "（对话刚开始）"
    recent = history[-max_msgs:]
    lines = []
    for msg in recent:
        role = "学生" if msg.get("role") == "student" else "患者"
        content = msg.get("content", "")[:200]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def get_opening_statement(case_data: dict, persona: PersonaConfig | None = None) -> str:
    """Return the patient's fixed opening statement.

    The docx authors this text per case, and it must be identical for every
    student — so it is read straight from the data and never generated. (The
    old version called the LLM, which was both non-deterministic and read a
    field path that no longer exists.)
    """
    return case_data.get("opening", "").strip()


async def process_message(
    student_message: str,
    case_data: dict,
    conversation_history: list[dict],
    persona: PersonaConfig | None = None,
    exam_data: dict | None = None,
) -> AsyncIterator[dict]:
    """Process a student message through the Patient Agent pipeline.

    Args:
        student_message: The student's latest question.
        case_data: The case's patient data (identity/opening/facts/psychology).
        conversation_history: Previous messages (list of {role, content}).
        persona: Persona configuration for this session.
        exam_data: The case's exam data — handed to the exam module, never to the
            patient generator. `None` means the case has no exam data at all.

    Yields:
        SSE event dicts: {event: str, data: dict}
        Events: "intent", "token" (multiple), "done"
    """
    persona = persona or DEFAULT_PERSONA

    # 本会话此前已经披露过的事实（来自历史里每条患者消息的 disclosed），供生成器避免重复
    already_disclosed: list[str] = []
    for msg in conversation_history:
        for fact_id in msg.get("disclosed") or []:
            if fact_id not in already_disclosed:
                already_disclosed.append(fact_id)

    # ── Step 1: Fact selection (lite) ──────────────────────────
    history_text = _summarize_history(conversation_history)
    selector_result = await select_facts(student_message, case_data, conversation_history=history_text)

    # ── 检查请求走检查模块，不经过患者 ─────────────────────────
    # 文档把这些测试标成 [检查模块]：患者不会背"探诊深度 2–3 mm"，让患者口述检查结果
    # 既不可审计也不像真人。selector 判"是不是要检查"，exam_module 判"是哪一项"并原样取结果。
    if selector_result["question_type"] == EXAM_QUESTION_TYPE:
        result = exam_module.answer(student_message, exam_data)
        yield {"event": "intent", "data": {"question_type": EXAM_QUESTION_TYPE,
                                           "asked_facts": [], "exam_ids": result["exam_ids"]}}
        yield {"event": "exam", "data": {"exam_ids": result["exam_ids"], "content": result["content"]}}
        yield {"event": "done", "data": {"question_type": EXAM_QUESTION_TYPE,
                                         "exam_ids": result["exam_ids"], "disclosed": []}}
        return

    if selector_result["question_type"] == ERROR_QUESTION_TYPE:
        # 上游 LLM 挂了。不要让它伪装成一次正常的"患者不知道"——记 error 级日志，
        # 并且这个值会一路写进 Message.intent，事后可查。
        logger.error(f"[PatientAgent] fact selector failed, degrading to 'error': {selector_result['reason']}")

    yield {
        "event": "intent",
        "data": {
            "question_type": selector_result["question_type"],
            "asked_facts": selector_result["asked_facts"],
            "reason": selector_result.get("reason", ""),
        },
    }

    # ── Step 2: Disclosure gate (pure Python) ──────────────────
    disclosure = gate(case_data, selector_result)
    facts = to_generator_facts(disclosure["allowed_facts"])
    persona_style = persona.to_prompt_fragment()

    # ── Step 3: Response generation (streaming) ────────────────
    full_response_parts: list[str] = []
    async for token in generate_response(
        case_data=case_data,
        facts=facts,
        student_message=student_message,
        conversation_history=conversation_history,
        persona_style=persona_style,
        already_disclosed=already_disclosed,
        question_type=disclosure["question_type"],
    ):
        full_response_parts.append(token)
        yield {"event": "token", "data": {"token": token}}

    logger.debug(f"[PatientAgent] disclosed {disclosure['disclosed']} for {student_message[:30]!r}")

    yield {
        "event": "done",
        "data": {
            "question_type": disclosure["question_type"],
            "asked_facts": selector_result["asked_facts"],
            "disclosed": disclosure["disclosed"],
        },
    }
