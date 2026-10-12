"""Assessment schemas.

答卷就是**五项**（2026-10-12 定，依据 R06–R10 加教师参考的对应字段反推；
医院文档只出现过「学员四项作答」这五个字，从未列举是哪四项——待医院确认）。
见 docs/scoring-system-design.md §4.3。

字段名以 scoring.llm_judge.ANSWER_FIELDS 为唯一权威，前端 DiagnosisForm 必须对齐。
"""

from datetime import datetime

from pydantic import BaseModel


class DiagnosisSubmit(BaseModel):
    """学员答卷：五项，一一对应 R06–R10。"""

    # ① 诊断：R06 要求「部位 + 确定性」，所以这里既写病名也写确定程度
    primary_diagnosis: str = ""
    # ② 诊断理由：R07 要求「以实际已获得信息说明推理链」，不是只报病名
    diagnosis_reason: str = ""
    # ③ 鉴别诊断：R08 要求「说明区分依据或还需资料」，不只是列病名
    differential_diagnosis: str = ""
    # ④ 近期处理：R09
    immediate_plan: str = ""
    # ⑤ 阶段计划与复评：R10（确定性处理、条件、替代路径、复评）

    staged_plan: str = ""

    # 注：旧的 `suggested_exams` 已删除——R04 看的是**对话里实际申请过什么**，
    # 留一个事后填空的字段，学生会补写压根没问过的检查。见设计文档 §4.3。
    # 旧的 `evidence` 改名为 `diagnosis_reason`（就是 R07 的"诊断理由"）。


class ScoringItem(BaseModel):
    id: str
    score: int
    max_score: int
    status: str = "scored"          # scored / ne / na / skipped_safety
    note: str = ""
    evidence: list[dict] = []


class ViewGroup(BaseModel):
    name: str
    items: list[str]
    score: int
    max: int


class ScoringView(BaseModel):
    name: str
    groups: list[ViewGroup]


class SafetyFlagOut(BaseModel):
    index: int
    error: str
    hit: bool
    evidence_quote: str = ""
    evidence_ref: str = ""
    checked: bool = True


class SafetyOut(BaseModel):
    flags: list[SafetyFlagOut] = []
    hits: int = 0
    unchecked: int = 0
    requires_review: bool = False
    safety_priority_case: bool = False
    stop_evidence: str = ""


class TotalOut(BaseModel):
    raw_total: int
    raw_max_counted: int
    raw_max_nominal: int
    excluded: dict = {}


class AssessmentResponse(BaseModel):
    id: int
    session_id: int
    report: dict
    raw_total: int
    comment: str | None = None
    student_report: dict | None = None
    created_at: datetime
