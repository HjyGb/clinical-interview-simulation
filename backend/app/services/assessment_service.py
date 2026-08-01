"""Assessment service — diagnosis submission and evaluation."""

from loguru import logger
from sqlalchemy.orm import Session

from agent.evaluator_agent import evaluate
from app.models.assessment import Assessment as AssessmentModel
from app.models.message import Message
from app.models.session import Session as SessionModel
from app.services.case_service import get_case_full


def submit_diagnosis(
    db: Session,
    session_id: int,
    student_report: dict,
) -> dict | None:
    """Submit a diagnosis and trigger assessment."""
    session = db.query(SessionModel).filter_by(id=session_id).first()
    if not session:
        return None

    # Mark session as ended
    from datetime import datetime, timezone
    session.status = "ended"
    session.ended_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "assessing", "session_id": session_id}


async def run_assessment(
    db: Session,
    session_id: int,
    student_report: dict,
) -> dict:
    """Run the full dual-track assessment.

    Returns the assessment dict ready for JSON serialization.
    """
    # Get session & case
    session = db.query(SessionModel).filter_by(id=session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    case = get_case_full(db, session.case_id)
    if not case:
        raise ValueError(f"Case {session.case_id} not found")

    # Get conversation history
    messages = (
        db.query(Message)
        .filter_by(session_id=session_id)
        .order_by(Message.created_at)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in messages]

    # Run evaluation
    logger.info(f"[Assessment] evaluating session {session_id}")
    result = await evaluate(
        student_report=student_report,
        case_data=case["data"],
        conversation_history=history,
    )

    # Store in DB
    assessment = AssessmentModel(
        session_id=session_id,
        diagnostic=result["diagnostic"],
        communication=result["communication"],
        student_report=student_report,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    return {
        "id": assessment.id,
        "session_id": assessment.session_id,
        "diagnostic": assessment.diagnostic,
        "communication": assessment.communication,
        "comment": assessment.comment,
        "student_report": assessment.student_report,
        "created_at": assessment.created_at,
    }


def get_assessment(db: Session, session_id: int) -> dict | None:
    """Get an existing assessment for a session."""
    a = db.query(AssessmentModel).filter_by(session_id=session_id).first()
    if not a:
        return None
    return {
        "id": a.id,
        "session_id": a.session_id,
        "diagnostic": a.diagnostic,
        "communication": a.communication,
        "comment": a.comment,
        "student_report": a.student_report,
        "created_at": a.created_at,
    }
