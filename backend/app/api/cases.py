"""Case API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.case import CaseDetailResponse, CaseListResponse, CaseSummary
from app.services import case_service

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])


@router.get("", response_model=CaseListResponse)
def list_cases(
    department: str | None = Query(None),
    difficulty: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    """List available cases with pagination."""
    cases = case_service.list_cases(db, department=department, difficulty=difficulty)

    # Pagination
    total = len(cases)
    start = (page - 1) * page_size
    end = start + page_size
    paged = cases[start:end]

    return CaseListResponse(
        cases=[CaseSummary(**c) for c in paged],
        total=total,
    )


@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    """Get case detail (Tier 1-3 only — diagnosis/treatment hidden)."""
    case = case_service.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="病例不存在")
    return CaseDetailResponse(**case)
