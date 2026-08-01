"""JWT auth middleware — FastAPI dependency for protected routes."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth_service import decode_token

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Extract and validate the current user from the JWT Bearer token.

    Raises 401 if token is missing or invalid.
    Returns the decoded token payload: {"sub": user_id, "username": str, "role": str}.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )

    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
        )

    return payload


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    """Like get_current_user but returns None instead of 401 for unauthenticated requests."""
    if credentials is None:
        return None
    return decode_token(credentials.credentials)
