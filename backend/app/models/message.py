"""Chat message model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)    # student / patient
    content: Mapped[str] = mapped_column(Text, nullable=False)
    round_num: Mapped[int] = mapped_column(Integer, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)    # only for patient messages
    fact_verify: Mapped[dict | None] = mapped_column(JSON, nullable=True)    # {pass: bool, violations: [...]}
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
