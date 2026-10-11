"""Case service — case listing and retrieval."""

from sqlalchemy.orm import Session

from app.models.case import Case


# Tier 4 fields to strip before returning to students
_TIER4_KEYS = {"diagnosis", "treatment_plan"}


def _safe_get(data: dict, *paths: str, default: str = "") -> str:
    """Try multiple dot-separated paths in order, return first non-empty value.

    Supports both MVP schema (e.g. chief_complaint at data.chief_complaint)
    and auto-generated schema (e.g. chief_complaint at data.basic_info.chief_complaint).
    """
    for path in paths:
        keys = path.split(".")
        val: object = data
        try:
            for k in keys:
                if isinstance(val, dict):
                    val = val.get(k, {})
                else:
                    val = {}
                    break
        except (AttributeError, TypeError):
            val = {}
        if isinstance(val, str) and val.strip():
            return val.strip()
    return default


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
            "visit_type": _safe_get(c.data, "basic_info.visit_type", "visit_type", default="首诊"),
            # v2.1 patient.json: 主诉文本在 data.opening；旧嵌套 schema 的两条路径保留兜底。
            "chief_complaint": _safe_get(
                c.data, "opening", "chief_complaint", "basic_info.chief_complaint", default=""
            ),
            "case_number": _safe_get(c.data, "case_number", "case_id", default=""),
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
        "data": case.data,            # 患者侧：identity/opening/facts/psychology
        "exam_data": case.exam_data,  # 检查侧：E 项。只给检查模块用，不进患者上下文
    }
