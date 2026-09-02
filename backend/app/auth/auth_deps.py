from __future__ import annotations

from fastapi import HTTPException, status, Header
from typing import Optional

from app.auth import authenticate_token


# Role constants for FastAPI dependency injection
class UserRole:
    ANALYST = "analyst"
    ADMIN = "admin"


def get_current_actor(authorization: str) -> str:
    """Get the current authenticated actor.
    
    Requires a valid JWT. Raises 401 if authentication fails.
    """
    actor_from_token = authenticate_token(authorization)
    if not actor_from_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return actor_from_token


def require_auth(authorization: Optional[str] = Header(None, alias="Authorization")) -> str:
    """Require valid JWT via Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return get_current_actor(authorization)