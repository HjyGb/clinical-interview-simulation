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


def _verify_ownership(db: Session, session_id: int, user_id: int) -> dict | None:
    """Verify session exists and belongs to user. Returns session dict or raises 403/404."""
    s = session_service.get_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    if s["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="无权访问此会话")
    return s


@router.post("")
async def create_session(
    req: SessionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new interview session with AI opening statement."""
    case = case_service.get_case_full(db, req.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="病例不存在")

    user_id = int(current_user["sub"])
    result = await session_service.create_session(db, user_id, req.case_id, case["data"])
    return result


@router.get("")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List current user's sessions with case info and assessment status."""
    user_id = int(current_user["sub"])
    sessions = session_service.list_user_sessions(db, user_id)
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get session details."""
    user_id = int(current_user["sub"])
    return _verify_ownership(db, session_id, user_id)


@router.get("/{session_id}/messages")
def get_messages(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get all messages in a session."""
    user_id = int(current_user["sub"])
    _verify_ownership(db, session_id, user_id)
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
    user_id = int(_current_user["sub"])
    s = _verify_ownership(db, session_id, user_id)

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
    current_user: dict = Depends(get_current_user),
):
    """End a session."""
    user_id = int(current_user["sub"])
    _verify_ownership(db, session_id, user_id)
    result = session_service.end_session(db, session_id)
    if not result:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result


@router.delete("/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a session and all associated messages & assessments."""
    user_id = int(current_user["sub"])
    _verify_ownership(db, session_id, user_id)
    result = session_service.delete_session(db, session_id)
    if not result:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result
