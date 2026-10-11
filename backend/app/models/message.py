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
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)    # 问句类型：open / targeted / meta
    # 本轮实际披露给学生的 H/P 编号，如 ["H01", "H02"]。用于 B 测试断言与过度披露审计。
    disclosed: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 已废弃：旧流水线的事后事实校验结果。新流水线在上游做边界控制，保留列只为兼容旧数据。
    fact_verify: Mapped[dict | None] = mapped_column(JSON, nullable=True)    # {pass: bool, violations: [...]}
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
