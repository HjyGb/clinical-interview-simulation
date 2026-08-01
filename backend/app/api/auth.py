"""Auth API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.auth import LoginRequest, LoginResponse, UserInfo
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Login or auto-register. Returns JWT token."""
    result = auth_service.login(db, req.username, req.password)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="密码错误",
        )
    return result


@router.get("/me", response_model=UserInfo)
def me(current_user: dict = Depends(get_current_user)):
    """Get current user info from JWT."""
    return UserInfo(
        id=int(current_user["sub"]),
        username=current_user["username"],
        role=current_user["role"],
    )
