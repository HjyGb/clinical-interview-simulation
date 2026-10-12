"""Assessment result model — the R01–R14 report."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("sessions.id"), unique=True, nullable=False)
    # 完整报告：14 项明细 + 两个视图 + 原始分/可评上限 + 安全标记。
    # 取代旧的 diagnostic/communication 两列——旧的双轨（Station 4 + MAAS）已废弃，
    # 把两个分取平均正是医院明令禁止的「安全错误与礼貌分平均抵消」。
    report: Mapped[dict] = mapped_column(JSON, nullable=False)
    # 原始分另存一列，方便历史列表排序/筛选，不用去 JSON 里挖
    raw_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    student_report: Mapped[dict] = mapped_column(JSON, nullable=False)   # 学员提交的作答快照
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
