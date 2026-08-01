"""Intent classifier — categorizes student questions to determine info Tier."""

import json
import re

from loguru import logger

from agent.llm_client import chat
from app.config import settings


INTENT_CLASSIFIER_PROMPT: str | None = None


def _load_prompt() -> str:
    """Lazy-load the intent classifier prompt template."""
    global INTENT_CLASSIFIER_PROMPT
    if INTENT_CLASSIFIER_PROMPT is None:
        from pathlib import Path
        prompt_path = Path(__file__).resolve().parent / "prompts" / "patient" / "intent_classifier.txt"
        INTENT_CLASSIFIER_PROMPT = prompt_path.read_text(encoding="utf-8")
    return INTENT_CLASSIFIER_PROMPT


async def classify_intent(student_message: str, conversation_summary: str = "") -> dict:
    """Classify the student's question into an intent category and Tier level.

    Args:
        student_message: The student's latest question.
        conversation_summary: Brief summary of previous conversation turns.

    Returns:
        {"intent": str, "tier": int, "confidence": float}
    """
    prompt_template = _load_prompt()
    system_prompt = (
        f"{prompt_template}\n\n"
        f"## 对话背景摘要\n{conversation_summary}\n"
        if conversation_summary else prompt_template
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"学生提问：{student_message}"},
    ]

    try:
        raw = await chat(messages, model=settings.llm_model_lite, temperature=0.0)
        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)
        logger.debug(f"[Intent] {student_message[:30]!r} → {result.get('intent')} (tier={result.get('tier')})")
        return result
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"[Intent] parse error for {student_message[:30]!r}: {e}, raw={raw[:200]!r}")
        return {"intent": "chief_complaint_inquiry", "tier": 1, "confidence": 0.5}
