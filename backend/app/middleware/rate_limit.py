from __future__ import annotations

import time
from collections import deque
from typing import Dict, Deque, Optional

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.status import HTTP_429_TOO_MANY_REQUESTS


# Simple in-memory rate limiter
# Keyed by client IP address
_rate_limiter: Optional["RateLimiter"] = None


class RateLimiter:
    """Simple in-memory rate limiter for API endpoints."""

    def __init__(self, limit: int = 100, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clients: Dict[str, Deque[float]] = {}
    
    def check(self, client_ip: str) -> tuple[bool, dict[str, int]]:
        """Check if the client is within rate limits.
        
        Returns (allowed, info_dict) where info_dict contains:
        - remaining: requests remaining in current window
        - reset: timestamp when the window resets
        """
        now = time.time()
        window_start = now - (now % self.window_seconds)
        
        if client_ip not in self._clients:
            self._clients[client_ip] = deque()
        
        # Remove timestamps outside the current window
        client_queue = self._clients[client_ip]
        while client_queue and client_queue[0] < window_start:
            client_queue.popleft()
        
        remaining = self.limit - len(client_queue)
        
        if len(client_queue) >= self.limit:
            # Calculate when the oldest request will expire
            reset_time = client_queue[0] + self.window_seconds
            return False, {
                "remaining": 0,
                "reset": int(reset_time),
            }
        
        # Add this request to the queue
        client_queue.append(now)
        
        return True, {
            "remaining": remaining - 1,
            "reset": int(window_start + self.window_seconds),
        }


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        # Higher limit for development to avoid false 429 during rapid dashboard switching
        # Testing already bypasses rate limiting via app_env check in main.py
        from app.core.config import settings
        limit = 1000 if settings.app_env == "development" else 100
        _rate_limiter = RateLimiter(limit=limit, window_seconds=60)
    return _rate_limiter


def check_rate_limit(request: Request, limiter: RateLimiter | None = None) -> Response | None:
    """Check rate limit for the current request.
    
    Returns None if allowed, or a Response with HTTP 429 if rate limited.
    """
    if limiter is None:
        limiter = get_rate_limiter()
    
    client_ip = request.client.host if request.client else "unknown"
    allowed, info = limiter.check(client_ip)
    
    if not allowed:
        retry_after = info["reset"] - int(time.time())
        headers = {
            "X-Rate-Limit-Limit": str(limiter.limit),
            "X-Rate-Limit-Remaining": "0",
            "X-Rate-Limit-Reset": str(info["reset"]),
            "Retry-After": str(max(retry_after, 1)),
        }
        return JSONResponse(
            content={"error": "rate_limit_exceeded", "detail": "Too many requests", "request_id": getattr(request.state, "request_id", "unknown")},
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            headers=headers,
        )
    
    return None