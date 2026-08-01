"""Information retriever — structured field lookup from case data.

Pure Python — no LLM call. Maps intent categories to case data field paths
and applies Tier-level filtering.
"""

from loguru import logger


# Maps intent types to the case data fields they can access
INTENT_FIELD_MAP: dict[str, list[str]] = {
    "chief_complaint_inquiry": [
        "chief_complaint",
    ],
    "pain_character_inquiry": [
        "chief_complaint",
        "present_illness.onset",
        "present_illness.duration",
        "present_illness.character",
        "present_illness.aggravating_factors",
        "present_illness.relieving_factors",
        "present_illness.radiation",
    ],
    "medical_history_inquiry": [
        "past_history.dental",
        "past_history.medical",
        "past_history.allergy",
        "past_history.medication",
    ],
    "examination_inquiry": [
        "oral_examination.inspection",
        "oral_examination.percussion",
        "oral_examination.palpation",
        "oral_examination.mobility",
        "oral_examination.thermal",
        "oral_examination.periodontal",
        "auxiliary_examination.xray",
        "auxiliary_examination.cbct",
    ],
    "diagnosis_guess": [],       # Tier 4 — blocked
    "treatment_inquiry": [],     # Tier 4 — blocked
    "greeting": [
        "chief_complaint",
    ],
    "multiple_questions": [
        "chief_complaint",
    ],
    "irrelevant": [],
}

# Tier determines how much of the mapped data is actually returned
# Tier 1: min — only chief complaint
# Tier 2: chief complaint + present illness + past history
# Tier 3: chief complaint + present illness + past history + examination + auxiliary
# Tier 4: blocked (diagnosis/treatment) — no data returned
TIER_ALLOWED_SECTIONS: dict[int, set[str]] = {
    1: {"chief_complaint"},
    2: {"chief_complaint", "present_illness", "past_history"},
    3: {"chief_complaint", "present_illness", "past_history", "oral_examination", "auxiliary_examination"},
    4: set(),  # blocked
}


def _get_nested(data: dict, path: str) -> str | None:
    """Get a nested dict value by dot-separated path. Returns None if missing."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            return ", ".join(str(v) for v in current)
        else:
            return None
    if current is None or current == "":
        return None
    return str(current)


def retrieve(case_data: dict, intent: str, tier: int) -> dict[str, str]:
    """Retrieve facts from case_data based on intent and Tier.

    Args:
        case_data: Full structured case data (JSON from DB).
        intent: Intent category from intent_classifier.
        tier: Information tier (1-4).

    Returns:
        Dict of field_label → field_value for facts the patient may disclose.
    """
    # Get the fields this intent can access
    field_paths = INTENT_FIELD_MAP.get(intent, [])
    if not field_paths:
        logger.debug(f"[Retrieve] intent={intent} tier={tier} → BLOCKED (no fields)")
        return {}

    # Filter by tier — only allow sections in the permitted tier
    allowed_sections = TIER_ALLOWED_SECTIONS.get(tier, set())

    facts: dict[str, str] = {}
    for path in field_paths:
        section = path.split(".")[0]
        if section not in allowed_sections:
            continue
        value = _get_nested(case_data, path)
        if value:
            # Human-readable label
            label = path.replace(".", " → ")
            facts[label] = value

    logger.debug(f"[Retrieve] intent={intent} tier={tier} → {len(facts)} facts")
    return facts
