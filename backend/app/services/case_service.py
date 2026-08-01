"""Case service — case listing and retrieval."""

from sqlalchemy.orm import Session

from app.models.case import Case


# Tier 4 fields to strip before returning to students
_TIER4_KEYS = {"diagnosis", "treatment_plan"}


def _strip_tier4(data: dict) -> dict:
    """Remove Tier 4 fields from case data before returning to students."""
    return {k: v for k, v in data.items() if k not in _TIER4_KEYS}


def list_cases(
    db: Session,
    department: str | None = None,
    difficulty: str | None = None,
    status: str = "published",
) -> list[dict]:
    """List published cases, optionally filtered."""
    query = db.query(Case).filter_by(status=status)
    if department:
        query = query.filter_by(department=department)
    if difficulty:
        query = query.filter_by(difficulty=difficulty)

    cases = query.all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "department": c.department,
            "difficulty": c.difficulty,
            "visit_type": c.data.get("basic_info", {}).get("visit_type", "首诊"),
            "chief_complaint": c.data.get("basic_info", {}).get("chief_complaint", ""),
        }
        for c in cases
    ]


def get_case(db: Session, case_id: int) -> dict | None:
    """Get a single case with Tier 4 fields stripped."""
    case = db.query(Case).filter_by(id=case_id).first()
    if not case:
        return None
    return {
        "id": case.id,
        "title": case.title,
        "department": case.department,
        "difficulty": case.difficulty,
        "data": _strip_tier4(case.data),
    }


def get_case_full(db: Session, case_id: int) -> dict | None:
    """Get full case data including Tier 4 (for internal use by Agent/Evaluator)."""
    case = db.query(Case).filter_by(id=case_id).first()
    if not case:
        return None
    return {
        "id": case.id,
        "title": case.title,
        "department": case.department,
        "difficulty": case.difficulty,
        "data": case.data,  # Full data including Tier 4
    }
