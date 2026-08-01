"""Response generator — streams the patient's answer token by token."""

from collections.abc import AsyncIterator

from agent.llm_client import chat_stream
from app.config import settings


RESPONSE_PROMPT: str | None = None
SYSTEM_BASE_PROMPT: str | None = None


def _load_prompts() -> tuple[str, str]:
    """Lazy-load response generator prompt templates."""
    global RESPONSE_PROMPT, SYSTEM_BASE_PROMPT
    if RESPONSE_PROMPT is None:
        from pathlib import Path
        base = Path(__file__).resolve().parent / "prompts" / "patient"
        SYSTEM_BASE_PROMPT = (base / "system_base.txt").read_text(encoding="utf-8")
        RESPONSE_PROMPT = (base / "response_generator.txt").read_text(encoding="utf-8")
    return SYSTEM_BASE_PROMPT, RESPONSE_PROMPT  # type: ignore[return-value]


def _format_facts(facts: dict[str, str]) -> str:
    """Format retrieved facts into a readable string for the prompt."""
    if not facts:
        return '（暂无可用信息 — 请用“不清楚”来回答）'
    lines = []
    for label, value in facts.items():
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def _format_history(history: list[dict]) -> str:
    """Format conversation history into a readable summary for the prompt."""
    if not history:
        return "（这是对话的开始，还没有之前的交流）"
    lines = []
    for msg in history[-6:]:  # Last 6 messages only
        role_label = "学生" if msg.get("role") == "student" else "患者"
        content = msg.get("content", "")[:200]  # Truncate long messages
        lines.append(f"{role_label}: {content}")
    return "\n".join(lines)


async def generate_response(
    case_data: dict,
    facts: dict[str, str],
    student_message: str,
    conversation_history: list[dict],
    persona_style: str = "你是一个普通的患者，说话比较正常。",
) -> AsyncIterator[str]:
    """Generate a streaming patient response.

    Args:
        case_data: Full case data (for basic_info).
        facts: Retrieved facts that the patient may use.
        student_message: The student's latest question.
        conversation_history: Previous messages in this session.
        persona_style: Persona prompt fragment.

    Yields:
        Tokens of the patient's response, one by one.
    """
    system_base, response_template = _load_prompts()

    # Build system prompt from system_base
    basic = case_data.get("basic_info", {})
    system_prompt = system_base.format(
        gender=basic.get("gender", "未知"),
        age_range=basic.get("age_range", "未知"),
        retrieved_facts=_format_facts(facts),
        persona_style=persona_style,
    )

    # Build user message from response template
    user_message = response_template.format(
        gender=basic.get("gender", "未知"),
        age_range=basic.get("age_range", "未知"),
        retrieved_facts=_format_facts(facts),
        persona_style=persona_style,
        student_question=student_message,
        conversation_history=_format_history(conversation_history),
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    async for token in chat_stream(messages, model=settings.llm_model_pro, temperature=0.3):
        yield token
