"""Assessment schemas."""

from datetime import datetime

from pydantic import BaseModel


class DiagnosisSubmit(BaseModel):
    primary_diagnosis: str = ""
    differential_diagnosis: str = ""
    evidence: str = ""
    suggested_exams: str = ""
    treatment_plan: str = ""


class ScoreDimension(BaseModel):
    name: str
    score: float
    max_score: float
    justification: str = ""
    missed_items: list[str] = []
    suggestions: list[str] = []


class AssessmentBlock(BaseModel):
    total_score: float
    max_score: float
    dimensions: list[ScoreDimension]


class AssessmentResponse(BaseModel):
    id: int
    session_id: int
    diagnostic: AssessmentBlock
    communication: AssessmentBlock
    comment: str | None = None
    created_at: datetime
