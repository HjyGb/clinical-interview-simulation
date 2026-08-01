"""Auth service — login with auto-registration for MVP."""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt
from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24


def create_token(user_id: int, username: str, role: str) -> str:
    """Create a JWT access token."""
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None


def login(db: Session, username: str, password: str) -> dict | None:
    """Login or auto-register a new user.

    Returns:
        {"access_token": str, "token_type": "bearer", "username": str, "role": str}
        or None if password is wrong for an existing user.
    """
    user = db.query(User).filter_by(username=username).first()

    if user:
        # Existing user — verify password
        if not bcrypt.checkpw(password.encode(), user.password.encode()):
            logger.warning(f"[Auth] wrong password for user: {username}")
            return None
    else:
        # Auto-register new student user
        user = User(
            username=username,
            password=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            role="student",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"[Auth] auto-registered new user: {username}")

    token = create_token(user.id, user.username, user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role,
    }
