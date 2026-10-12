"""Assessment API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.assessment import DiagnosisSubmit
from app.services import assessment_service

router = APIRouter(prefix="/api/v1/sessions", tags=["assessments"])


def _verify_ownership(db: Session, session_id: int, user_id: int) -> dict:
    """Verify session exists and belongs to user."""
    from app.services.session_service import get_session as get_s
    s = get_s(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    if s["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="无权访问此会话")
    return s


@router.post("/{session_id}/assessment")
async def submit_assessment(
    session_id: int,
    req: DiagnosisSubmit,
    db: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    """Submit diagnosis and trigger evaluation."""
    user_id = int(_current_user["sub"])
    _verify_ownership(db, session_id, user_id)

    # Check existing assessment
    existing = assessment_service.get_assessment(db, session_id)
    if existing:
        return existing

    # 答卷五项（字段名以 scoring.llm_judge.ANSWER_FIELDS 为准）
    student_report = {
        "primary_diagnosis": req.primary_diagnosis,
        "diagnosis_reason": req.diagnosis_reason,
        "differential_diagnosis": req.differential_diagnosis,
        "immediate_plan": req.immediate_plan,
        "staged_plan": req.staged_plan,
    }

    _ = assessment_service.submit_diagnosis(db, session_id, student_report)

    # Run evaluation (synchronous for simplicity in MVP — blocks until done)
    result = await assessment_service.run_assessment(db, session_id, student_report)
    return result


@router.get("/{session_id}/assessment")
def get_assessment(
    session_id: int,
    db: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    """Get assessment result."""
    user_id = int(_current_user["sub"])
    _verify_ownership(db, session_id, user_id)
    result = assessment_service.get_assessment(db, session_id)
    if not result:
        raise HTTPException(status_code=404, detail="评估结果不存在，请先提交诊断")
    return result
