"""Assessment service — run the R01–R14 scoring and persist the report.

取代旧的双轨评估（Station 4 + MAAS-Global）。两条纪律：

  1. **失败必须像失败。** 评分链路整体出错时**抛异常**（→ 5xx），
     **绝不写一份"看着正常"的 0 分报告**。单条 LLM 判定失败由 `llm_judge` 标成 NE，
     是"这一条没评成"，不是"学员这块没做到"——两者在报告里分得很开。
  2. **不取平均。** 原始分就是 14 项之和；安全标记独立列出，不与任何分数抵消。
"""

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.assessment import Assessment as AssessmentModel
from app.models.message import Message
from app.models.session import Session as SessionModel
from app.services.case_service import get_case_full
from scoring.runner import load_common_rubric, score_session


def submit_diagnosis(db: Session, session_id: int, student_report: dict) -> dict | None:
    """Mark the session ended. Scoring itself happens in `run_assessment`."""
    session = db.query(SessionModel).filter_by(id=session_id).first()
    if not session:
        return None
    session.status = "ended"
    session.ended_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "assessing", "session_id": session_id}


async def run_assessment(db: Session, session_id: int, student_report: dict) -> dict:
    """Score the session and persist the report. Raises on failure — never fakes a 0."""
    session = db.query(SessionModel).filter_by(id=session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    case = get_case_full(db, session.case_id)
    if not case:
        raise ValueError(f"Case {session.case_id} not found")

    rubric, answer_key = case.get("scoring_rubric"), case.get("answer_key")
    if not rubric or not answer_key:
        # 明确报出来。旧代码在这种情况下会把标准答案当成"未知"，然后照常给分。
        raise ValueError(
            f"病例 {case['title']} 缺少评分数据（scoring_rubric / answer_key 未入库）——无法评分"
        )

    messages = (
        db.query(Message)
        .filter_by(session_id=session_id)
        .order_by(Message.created_at, Message.id)
        .all()
    )
    history = [
        {"role": m.role, "content": m.content, "round_num": m.round_num,
         "intent": m.intent, "disclosed": m.disclosed or []}
        for m in messages
    ]

    logger.info(f"[Scoring] session={session_id} case={case['title']} "
                f"messages={len(history)} report_fields={sum(1 for v in student_report.values() if v)}")

    report = await score_session(
        rubric=rubric,
        answer_key=answer_key,
        exam_data=case.get("exam_data"),
        messages=history,
        student_report=student_report,
        common_items=load_common_rubric(),
    )

    assessment = AssessmentModel(
        session_id=session_id,
        report=report,
        raw_total=report["total"]["raw_total"],
        student_report=student_report,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    return {
        "id": assessment.id,
        "session_id": assessment.session_id,
        "report": assessment.report,
        "raw_total": assessment.raw_total,
        "comment": assessment.comment,
        "student_report": assessment.student_report,
        "created_at": assessment.created_at,
    }


def get_assessment(db: Session, session_id: int) -> dict | None:
    a = db.query(AssessmentModel).filter_by(session_id=session_id).first()
    if not a:
        return None
    return {
        "id": a.id,
        "session_id": a.session_id,
        "report": a.report,
        "raw_total": a.raw_total,
        "comment": a.comment,
        "student_report": a.student_report,
        "created_at": a.created_at,
    }
