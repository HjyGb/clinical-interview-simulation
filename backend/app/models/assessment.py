"""Assessment result model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("sessions.id"), unique=True, nullable=False)
    diagnostic: Mapped[dict] = mapped_column(JSON, nullable=False)           # Block A: Station 4 scores
    communication: Mapped[dict] = mapped_column(JSON, nullable=False)        # Block B: MAAS-Global scores
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)         # Block C: teacher-style comment
    student_report: Mapped[dict] = mapped_column(JSON, nullable=False)       # snapshot of student's diagnosis submission
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
