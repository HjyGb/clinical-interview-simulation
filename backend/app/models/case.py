"""Case (standardized patient case) model."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str] = mapped_column(String(50), default="口腔科")
    difficulty: Mapped[str] = mapped_column(String(20), default="intermediate")  # beginner / intermediate / advanced
    data: Mapped[dict] = mapped_column(JSON, nullable=False)       # full structured case (Tier 1–4)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft / reviewed / published / archived
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
