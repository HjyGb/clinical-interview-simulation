"""Session schemas."""

from datetime import datetime

from pydantic import BaseModel


class SessionCreate(BaseModel):
    case_id: int


class SessionResponse(BaseModel):
    id: int
    user_id: int
    case_id: int
    status: str
    max_rounds: int
    current_round: int = 0
    started_at: datetime
    ended_at: datetime | None = None


class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    round_num: int
    created_at: datetime


class SendMessageRequest(BaseModel):
    content: str
