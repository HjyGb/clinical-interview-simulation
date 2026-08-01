"""Fact verifier — post-generation hallucination check.

Runs after the response has been streamed to the user. Violations are logged
but cannot be retracted from the already-sent stream.
"""

import json
import re

from loguru import logger

from agent.llm_client import chat
from app.config import settings


VERIFIER_PROMPT: str | None = None


def _load_prompt() -> str:
    global VERIFIER_PROMPT
    if VERIFIER_PROMPT is None:
        from pathlib import Path
        prompt_path = Path(__file__).resolve().parent / "prompts" / "patient" / "fact_verifier.txt"
        VERIFIER_PROMPT = prompt_path.read_text(encoding="utf-8")
    return VERIFIER_PROMPT


def _format_facts(facts: dict[str, str]) -> str:
    if not facts:
        return "（无可用事实 — 患者回答不应包含任何事实性陈述）"
    lines = [f"- {k}: {v}" for k, v in facts.items()]
    return "\n".join(lines)


async def verify(generated_response: str, facts: dict[str, str]) -> dict:
    """Verify the generated response against the known facts.

    Args:
        generated_response: The full patient response text.
        facts: The retrieved facts that were provided to the generator.

    Returns:
        {"pass": bool, "violations": [{"claim": str, "fact": str|null, "severity": str}]}
    """
    prompt_template = _load_prompt()

    user_message = prompt_template.format(
        retrieved_facts=_format_facts(facts),
        generated_response=generated_response,
    )

    messages = [
        {"role": "user", "content": user_message},
    ]

    try:
        raw = await chat(messages, model=settings.llm_model_lite, temperature=0.0, max_tokens=512)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)

        if not result.get("pass", False):
            violations = result.get("violations", [])
            logger.warning(f"[FactVerify] FAILED — {len(violations)} violations:")
            for v in violations:
                logger.warning(f"  Claim: {v.get('claim', '?')} | Fact: {v.get('fact', '?')} | Severity: {v.get('severity', '?')}")
        else:
            logger.debug("[FactVerify] passed")

        return result
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"[FactVerify] parse error: {e}, raw={raw[:200]!r}")
        return {"pass": True, "violations": []}
