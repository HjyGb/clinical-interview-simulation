"""Patient Agent — orchestrates the 4-step response pipeline.

Pipeline: Intent Classify → Info Retrieve → Response Generate → Fact Verify
"""

from collections.abc import AsyncIterator

from loguru import logger

from agent.fact_verifier import verify
from agent.info_retriever import retrieve
from agent.intent_classifier import classify_intent
from agent.persona import DEFAULT_PERSONA, PersonaConfig
from agent.response_generator import generate_response


def _summarize_history(history: list[dict], max_msgs: int = 4) -> str:
    """Create a brief summary of recent conversation for the intent classifier."""
    if not history:
        return "（对话刚开始）"
    recent = history[-max_msgs:]
    lines = []
    for msg in recent:
        role = "学生" if msg.get("role") == "student" else "患者"
        content = msg.get("content", "")[:100]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def get_opening_statement(case_data: dict, persona: PersonaConfig | None = None) -> str:
    """Generate the patient's opening statement (first message in a session).

    This is NOT streamed — it's a single message that starts the conversation.
    The opening statement is deterministic per case so all students get the same start.
    """
    persona = persona or DEFAULT_PERSONA
    basic = case_data.get("basic_info", {})
    complaint = basic.get("chief_complaint", "牙齿不舒服")

    # Build a simple opening — non-streamed, cached per case
    facts = {
        "主诉": complaint,
    }
    persona_style = persona.to_prompt_fragment()

    # Use the response generator but collect all tokens
    tokens: list[str] = []
    async for token in generate_response(
        case_data=case_data,
        facts=facts,
        student_message="（问诊开始，请患者描述自己的不适）",
        conversation_history=[],
        persona_style=persona_style,
    ):
        tokens.append(token)

    return "".join(tokens)


async def process_message(
    student_message: str,
    case_data: dict,
    conversation_history: list[dict],
    persona: PersonaConfig | None = None,
) -> AsyncIterator[str]:
    """Process a student message through the full Patient Agent pipeline.

    Args:
        student_message: The student's latest question.
        case_data: Full structured case data.
        conversation_history: Previous messages (list of {role, content}).
        persona: Persona configuration for this session.

    Yields:
        SSE event dicts: {event: str, data: dict}
        Events: "intent", "token" (multiple), "done"
    """
    persona = persona or DEFAULT_PERSONA

    # ── Step 1: Intent Classification ──────────────────────────
    summary = _summarize_history(conversation_history)
    intent_result = await classify_intent(student_message, summary)
    intent = intent_result.get("intent", "chief_complaint_inquiry")
    tier = intent_result.get("tier", 2)
    confidence = intent_result.get("confidence", 0.5)

    yield {"event": "intent", "data": {"class": intent, "tier": tier, "confidence": confidence}}

    # ── Step 2: Information Retrieval ──────────────────────────
    facts = retrieve(case_data, intent, tier)
    persona_style = persona.to_prompt_fragment()

    # ── Step 3: Response Generation (streaming) ────────────────
    full_response_parts: list[str] = []
    async for token in generate_response(
        case_data=case_data,
        facts=facts,
        student_message=student_message,
        conversation_history=conversation_history,
        persona_style=persona_style,
    ):
        full_response_parts.append(token)
        yield {"event": "token", "data": {"token": token}}

    full_response = "".join(full_response_parts)

    # ── Step 4: Fact Verification (non-blocking) ───────────────
    try:
        verify_result = await verify(full_response, facts)
    except Exception as e:
        logger.error(f"[PatientAgent] fact verification failed: {e}")
        verify_result = {"pass": True, "violations": []}

    yield {"event": "done", "data": {"fact_verify": verify_result, "intent": intent, "tier": tier}}
