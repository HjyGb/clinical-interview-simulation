"""Session API routes — the core interview endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.session import (
    MessageResponse,
    SendMessageRequest,
    SessionCreate,
    SessionResponse,
)
from app.services import case_service, session_service

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
def create_session(
    req: SessionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new interview session."""
    # Verify case exists
    case = case_service.get_case_full(db, req.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="病例不存在")

    user_id = int(current_user["sub"])
    return session_service.create_session(db, user_id, req.case_id)


@router.get("")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List current user's sessions (stub — returns empty for MVP)."""
    # MVP: return empty list; full implementation would query by user_id
    return {"sessions": [], "total": 0}


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    """Get session details."""
    s = session_service.get_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    return s


@router.get("/{session_id}/messages")
def get_messages(
    session_id: int,
    db: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    """Get all messages in a session."""
    msgs = session_service.get_messages(db, session_id)
    return {"messages": [MessageResponse(**m) for m in msgs], "total": len(msgs)}


@router.post("/{session_id}/messages")
async def send_message(
    session_id: int,
    req: SendMessageRequest,
    db: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    """Send a message to the patient and receive a streaming response via SSE."""
    # Get case data for the Agent
    s = session_service.get_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")

    case = case_service.get_case_full(db, s["case_id"])
    if not case:
        raise HTTPException(status_code=404, detail="病例不存在")

    async def event_stream():
        async for event in session_service.add_student_message(
            db=db,
            session_id=session_id,
            content=req.content,
            case_data=case["data"],
        ):
            event_name = event.get("event", "message")
            data = event.get("data", {})
            yield f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{session_id}/end")
def end_session(
    session_id: int,
    db: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    """End a session."""
    result = session_service.end_session(db, session_id)
    if not result:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result
