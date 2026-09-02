from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable

import jwt  # PyJWT

from app.core.config import settings


class JWTAuth:
    """JWT-based authentication abstraction."""
    
    @staticmethod
    def _secret() -> str:
        # Fallback for demo / tests when JWT_SECRET_KEY not configured
        return settings.jwt_secret_key or "dev-demo-secret-not-for-production-32chars!"

    @staticmethod
    def encode_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
        """Encode a JWT token for the given subject."""
        expires = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
        payload = {
            "sub": subject,
            "iat": datetime.utcnow(),
            "exp": expires,
        }
        encoded = jwt.encode(payload, JWTAuth._secret(), algorithm=settings.jwt_algorithm)
        return encoded
    
    @staticmethod
    def decode_token(token: str) -> Optional[Dict[str, Any]]:
        """Decode a JWT token and return the payload, or None if invalid/expired."""
        try:
            payload = jwt.decode(token, JWTAuth._secret(), algorithms=[settings.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            return None  # Token expired
        except jwt.InvalidTokenError:
            return None  # Invalid token
    
    @staticmethod
    def extract_token_from_headers(authorization: str) -> Optional[str]:
        """Extract Bearer token from Authorization header."""
        if not authorization or not authorization.startswith("Bearer "):
            return None
        return authorization[7:]


def authenticate_token(authorization: str) -> Optional[str]:
    """Dependency to get the current actor from JWT token.
    
    Returns the actor identity (sub/email), or None if authentication fails.
    This is designed to be used as a FastAPI dependency.
    """
    token = JWTAuth.extract_token_from_headers(authorization)
    if not token:
        return None
    payload = JWTAuth.decode_token(token)
    if not payload:
        return None
    # Return the subject - this could be email, username, or user ID
    return payload.get("sub")