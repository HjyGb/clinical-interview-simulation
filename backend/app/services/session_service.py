"""Session service — manages interview sessions and message processing."""

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from agent.patient_agent import get_opening_statement, process_message
from agent.persona import DEFAULT_PERSONA
from app.models.assessment import Assessment as AssessmentModel
from app.models.case import Case
from app.models.message import Message
from app.models.session import Session as SessionModel


async def create_session(
    db: Session, user_id: int, case_id: int, case_data: dict
) -> dict:
    """Create a new interview session and generate the AI patient's opening statement."""
    persona = {
        "anxiety_level": DEFAULT_PERSONA.anxiety_level,
        "verbosity": DEFAULT_PERSONA.verbosity,
        "trust_level": DEFAULT_PERSONA.trust_level,
        "language_style": DEFAULT_PERSONA.language_style,
    }

    session = SessionModel(
        user_id=user_id,
        case_id=case_id,
        persona=persona,
        status="active",
        # 25 轮：医院的 S01 常规路径本身就有 13 步，12 轮装不下。
        # 开发测试期放宽，正式值待与医院确认问诊时长后再定。
        max_rounds=25,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # 开场白直接取自病例数据（固定文本），不再调 LLM，保证每位学生看到同一句
    opening = get_opening_statement(case_data, DEFAULT_PERSONA)

    # Store as the first patient message (round 0)
    opening_msg = Message(
        session_id=session.id,
        role="patient",
        content=opening,
        round_num=0,
        intent="greeting",
    )
    db.add(opening_msg)
    db.commit()

    return {
        "id": session.id,
        "user_id": session.user_id,
        "case_id": session.case_id,
        "status": session.status,
        "max_rounds": session.max_rounds,
        "current_round": 0,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "opening_message": opening,
    }


def _student_turn_count(db: Session, session_id: int) -> int:
    """How many student turns so far. This is what a 'round' means.

    Counting all rows and dividing by 2 was only valid while every round was
    exactly one student + one patient row. Exam results add a third row type,
    so count student rows directly.
    """
    return db.query(Message).filter_by(session_id=session_id, role="student").count()


def get_session(db: Session, session_id: int) -> dict | None:
    """Get session details."""
    s = db.query(SessionModel).filter_by(id=session_id).first()
    if not s:
        return None

    # 一轮 = 学生的一次发言。按学生消息数算，不按总消息数——
    # 检查结果（role="exam"）是额外的回复行，用总数除 2 会算错轮次。
    current_round = _student_turn_count(db, s.id)

    return {
        "id": s.id,
        "user_id": s.user_id,
        "case_id": s.case_id,
        "status": s.status,
        "max_rounds": s.max_rounds,
        "current_round": current_round,
        "started_at": s.started_at,
        "ended_at": s.ended_at,
    }


def get_messages(db: Session, session_id: int) -> list[dict]:
    """Get all messages for a session, ordered by creation time.

    `created_at` comes from SQLite's CURRENT_TIMESTAMP, which has **1-second**
    resolution — every message in a session usually shares the same value. Tie-break
    on `id` so the order is deterministic; the patient's memory depends on it.
    """
    msgs = (
        db.query(Message)
        .filter_by(session_id=session_id)
        .order_by(Message.created_at, Message.id)
        .all()
    )
    return [
        {
            "id": m.id,
            "session_id": m.session_id,
            "role": m.role,
            "content": m.content,
            "round_num": m.round_num,
            "disclosed": m.disclosed or [],
            "created_at": m.created_at,
        }
        for m in msgs
    ]


async def add_student_message(
    db: Session,
    session_id: int,
    content: str,
    case_data: dict,
    exam_data: dict | None = None,
) -> AsyncIterator[dict]:
    """Process a student message through the Agent and yield SSE events.

    Yields:
        SSE event dicts: {"event": str, "data": dict}
    """
    session = db.query(SessionModel).filter_by(id=session_id).first()
    if not session or session.status != "active":
        yield {"event": "error", "data": {"message": "Session not found or not active"}}
        return

    # Check round limit（一轮 = 学生一次发言）
    current_round = _student_turn_count(db, session_id) + 1  # upcoming round

    if current_round > session.max_rounds:
        yield {"event": "error", "data": {"message": f"已达到最大轮次（{session.max_rounds}轮），请提交诊断"}}
        return

    # Store student message
    student_msg = Message(
        session_id=session_id,
        role="student",
        content=content,
        round_num=current_round,
    )
    db.add(student_msg)
    db.commit()

    # Get conversation history
    history = get_messages(db, session_id)

    # Process through the Agent
    reply_parts: list[str] = []
    reply_role = "patient"
    done_data: dict = {}

    async for event in process_message(
        student_message=content,
        case_data=case_data,
        # exclude just-added student msg; carry `disclosed` so the patient remembers what it already said
        conversation_history=[
            {"role": h["role"], "content": h["content"], "disclosed": h.get("disclosed") or []}
            for h in history[:-1]
        ],
        exam_data=exam_data,
    ):
        event_type = event["event"]

        if event_type == "token":
            reply_parts.append(event["data"]["token"])
            yield event
        elif event_type == "data_gap":
            # 模拟资料不足由**系统**说明，不是患者说话——单独立一个 role，
            # 回放和审计才看得出"这句不是这个患者讲的"。
            reply_role = "system"
            reply_parts.append(event["data"]["message"])
            yield event
        elif event_type == "exam":
            # 检查结果是整段文本（数据原文，逐字不流式），由前端单独渲染成检查卡片
            reply_role = "exam"
            reply_parts.append(event["data"]["content"])
            yield event
        elif event_type == "done":
            done_data = event["data"]
        else:
            # "intent" 等上游事件原样透传给前端
            yield event

    # Store the reply. 检查结果以 role="exam" 落库——它不是患者说的话，
    # 混进 role="patient" 会让回放和审计都失真。
    full_response = "".join(reply_parts)
    question_type = done_data.get("question_type", "")
    disclosed = done_data.get("disclosed", [])

    reply_msg = Message(
        session_id=session_id,
        role=reply_role,
        content=full_response,
        round_num=current_round,
        intent=question_type,
        disclosed=disclosed,
    )
    db.add(reply_msg)
    db.commit()

    # Round limit warning
    remaining = session.max_rounds - current_round
    if remaining <= 2:
        yield {
            "event": "limit_warning",
            "data": {
                "remaining_rounds": remaining,
                "message": f"本轮后仅剩 {remaining} 轮对话，请考虑提交诊断",
            },
        }

    # exam_ids 只对检查结果有意义；disclosed 只对患者回复有意义。两个都带上，
    # 前端/测试按 question_type 各取所需。
    yield {
        "event": "done",
        "data": {
            "round": current_round,
            "question_type": question_type,
            "disclosed": disclosed,
            "exam_ids": done_data.get("exam_ids", []),
            "subitem_keys": done_data.get("subitem_keys", []),
        },
    }


def end_session(db: Session, session_id: int) -> dict | None:
    """End a session."""
    session = db.query(SessionModel).filter_by(id=session_id).first()
    if not session:
        return None
    session.status = "ended"
    session.ended_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ended", "ended_at": session.ended_at.isoformat()}


def delete_session(db: Session, session_id: int) -> dict | None:
    """Delete a session and all associated messages & assessments (hard delete)."""
    session = db.query(SessionModel).filter_by(id=session_id).first()
    if not session:
        return None

    # Cascade: delete children first to avoid FK issues
    db.query(Message).filter_by(session_id=session_id).delete()
    db.query(AssessmentModel).filter_by(session_id=session_id).delete()
    db.delete(session)
    db.commit()

    logger.info(f"[Session] deleted session {session_id}")
    return {"deleted": True, "session_id": session_id}


def list_user_sessions(db: Session, user_id: int) -> list[dict]:
    """List all sessions for a user with case info and assessment status."""
    rows = (
        db.query(SessionModel, Case, AssessmentModel)
        .join(Case, SessionModel.case_id == Case.id)
        .outerjoin(AssessmentModel, AssessmentModel.session_id == SessionModel.id)
        .filter(SessionModel.user_id == user_id)
        .order_by(SessionModel.started_at.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "case_id": s.case_id,
            "status": s.status,
            "max_rounds": s.max_rounds,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "case_title": case.title,
            "case_department": case.department,
            "case_difficulty": case.difficulty,
            "has_assessment": assessment is not None,
            "assessment_id": assessment.id if assessment else None,
        }
        for s, case, assessment in rows
    ]
