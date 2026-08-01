"""Evaluator Agent — dual-track assessment (Station 4 + MAAS-Global)."""

import asyncio
import json
import re

from loguru import logger

from agent.llm_client import chat
from app.config import settings


STATION4_PROMPT: str | None = None
MAAS_GLOBAL_PROMPT: str | None = None


def _load_prompts() -> tuple[str, str]:
    global STATION4_PROMPT, MAAS_GLOBAL_PROMPT
    if STATION4_PROMPT is None:
        from pathlib import Path
        base = Path(__file__).resolve().parent / "prompts" / "evaluator"
        STATION4_PROMPT = (base / "station4_scoring.txt").read_text(encoding="utf-8")
        MAAS_GLOBAL_PROMPT = (base / "maas_global_scoring.txt").read_text(encoding="utf-8")
    return STATION4_PROMPT, MAAS_GLOBAL_PROMPT  # type: ignore[return-value]


def _format_history(history: list[dict]) -> str:
    """Format conversation history for evaluator prompts."""
    lines = []
    for msg in history:
        role_label = "学生" if msg.get("role") == "student" else "患者"
        content = msg.get("content", "")
        lines.append(f"{role_label}: {content}")
    return "\n".join(lines)


def _parse_json(raw: str) -> dict:
    """Parse JSON from LLM output, handling markdown fences."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


async def evaluate_diagnostic(
    student_report: dict,
    case_data: dict,
    conversation_history: list[dict],
) -> dict:
    """Block A: Station 4 diagnostic scoring."""
    prompt_template = _load_prompts()[0]
    diagnosis = case_data.get("diagnosis", {})
    treatment = case_data.get("treatment_plan", {})

    user_message = prompt_template.format(
        true_diagnosis=diagnosis.get("primary", "未知"),
        true_treatment_plan=treatment.get("definitive", "未知"),
        student_primary_diagnosis=student_report.get("primary_diagnosis", ""),
        student_differential_diagnosis=student_report.get("differential_diagnosis", ""),
        student_evidence=student_report.get("evidence", ""),
        student_suggested_exams=student_report.get("suggested_exams", ""),
        student_treatment_plan=student_report.get("treatment_plan", ""),
        conversation_history=_format_history(conversation_history),
    )

    messages = [{"role": "user", "content": user_message}]

    try:
        raw = await chat(messages, model=settings.llm_model_pro, temperature=0.0, max_tokens=2048)
        result = _parse_json(raw)
        logger.info(f"[Eval-Station4] total_score={result.get('total_score')}")
        return result
    except Exception as e:
        logger.error(f"[Eval-Station4] failed: {e}")
        return {"total_score": 0, "max_score": 100, "dimensions": [], "error": str(e)}


async def evaluate_communication(
    conversation_history: list[dict],
) -> dict:
    """Block B: MAAS-Global communication scoring."""
    prompt_template = _load_prompts()[1]

    user_message = prompt_template.format(
        conversation_history=_format_history(conversation_history),
    )

    messages = [{"role": "user", "content": user_message}]

    try:
        raw = await chat(messages, model=settings.llm_model_pro, temperature=0.0, max_tokens=2048)
        result = _parse_json(raw)
        logger.info(f"[Eval-MAAS] total_score={result.get('total_score')}")
        return result
    except Exception as e:
        logger.error(f"[Eval-MAAS] failed: {e}")
        return {"total_score": 0, "max_score": 100, "dimensions": [], "error": str(e)}


async def evaluate(
    student_report: dict,
    case_data: dict,
    conversation_history: list[dict],
) -> dict:
    """Run both diagnostic and communication assessments in parallel.

    Returns:
        {"diagnostic": dict, "communication": dict}
    """
    diagnostic_result, comm_result = await asyncio.gather(
        evaluate_diagnostic(student_report, case_data, conversation_history),
        evaluate_communication(conversation_history),
    )
    return {
        "diagnostic": diagnostic_result,
        "communication": comm_result,
    }
