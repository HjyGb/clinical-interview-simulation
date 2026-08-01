"""Case schemas."""

from pydantic import BaseModel


class CaseSummary(BaseModel):
    id: int
    title: str
    department: str
    difficulty: str
    visit_type: str = "首诊"
    chief_complaint: str = ""


class CaseListResponse(BaseModel):
    cases: list[CaseSummary]
    total: int


class CaseDetailResponse(BaseModel):
    id: int
    title: str
    department: str
    difficulty: str
    data: dict  # Full case data with Tier 1-3 only (Tier 4 stripped by service)
