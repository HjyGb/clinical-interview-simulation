"""Session service — manages interview sessions and message processing."""

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from agent.patient_agent import get_opening_statement, process_message
from agent.persona import DEFAULT_PERSONA
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
        max_rounds=12,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Generate the patient's opening statement via LLM
    try:
        opening = await get_opening_statement(case_data, DEFAULT_PERSONA)
    except Exception as e:
        logger.error(f"[Session] opening statement generation failed: {e}")
        opening = "你好...（患者暂时无法说话，请稍后再试）"

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


def get_session(db: Session, session_id: int) -> dict | None:
    """Get session details."""
    s = db.query(SessionModel).filter_by(id=session_id).first()
    if not s:
        return None

    # Count messages for current round
    msg_count = db.query(Message).filter_by(session_id=s.id).count()
    current_round = msg_count // 2  # Each round = student msg + patient msg

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
    """Get all messages for a session, ordered by creation time."""
    msgs = (
        db.query(Message)
        .filter_by(session_id=session_id)
        .order_by(Message.created_at)
        .all()
    )
    return [
        {
            "id": m.id,
            "session_id": m.session_id,
            "role": m.role,
            "content": m.content,
            "round_num": m.round_num,
            "created_at": m.created_at,
        }
        for m in msgs
    ]


async def add_student_message(
    db: Session,
    session_id: int,
    content: str,
    case_data: dict,
) -> AsyncIterator[dict]:
    """Process a student message through the Patient Agent and yield SSE events.

    Yields:
        SSE event dicts: {"event": str, "data": dict}
    """
    session = db.query(SessionModel).filter_by(id=session_id).first()
    if not session or session.status != "active":
        yield {"event": "error", "data": {"message": "Session not found or not active"}}
        return

    # Check round limit
    msg_count = db.query(Message).filter_by(session_id=session_id).count()
    current_round = msg_count // 2 + 1  # upcoming round

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

    # Process through Patient Agent
    patient_content_parts: list[str] = []
    intent_result = None
    fact_verify = None

    async for event in process_message(
        student_message=content,
        case_data=case_data,
        conversation_history=[{"role": h["role"], "content": h["content"]} for h in history[:-1]],  # exclude just-added student msg
    ):
        event_type = event["event"]

        if event_type == "intent":
            intent_result = event["data"]
            yield event
        elif event_type == "token":
            patient_content_parts.append(event["data"]["token"])
            yield event
        elif event_type == "done":
            fact_verify = event["data"].get("fact_verify", {"pass": True, "violations": []})
            intent_result = event["data"]

    # Store patient message
    full_response = "".join(patient_content_parts)
    intent_str = intent_result.get("class", "") if isinstance(intent_result, dict) else ""

    patient_msg = Message(
        session_id=session_id,
        role="patient",
        content=full_response,
        round_num=current_round,
        intent=intent_str,
        fact_verify=fact_verify,
    )
    db.add(patient_msg)
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

    yield {"event": "done", "data": {"round": current_round, "fact_verify": fact_verify}}


def end_session(db: Session, session_id: int) -> dict | None:
    """End a session."""
    session = db.query(SessionModel).filter_by(id=session_id).first()
    if not session:
        return None
    session.status = "ended"
    session.ended_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ended", "ended_at": session.ended_at.isoformat()}
