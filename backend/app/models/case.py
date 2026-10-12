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
    data: Mapped[dict] = mapped_column(JSON, nullable=False)       # patient side: identity/opening/facts/psychology
    # 检查侧数据（E 项：label/level/aliases/result/boundary），与 data 分开存。
    # 分开的意义是结构性的：患者 Agent 拿不到检查结果，检查模块拿不到患者事实。
    exam_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 评分侧数据。与 data / exam_data 并列、且**互不可见**：
    #   answer_key     = 病例 A2 隐藏参考答案（D/DD/T/G），只给评分链路；
    #   scoring_rubric = 病例 A3 的 R01–R14 锚点 + 关键错误，只给评分链路。
    # 患者 Agent 与学员端 API 永远拿不到这两列（见 scripts/verify_scoring_isolation.py）。
    answer_key: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scoring_rubric: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft / reviewed / published / archived
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
