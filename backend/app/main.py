from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.transactions import router as transactions_router
from app.api.cases import router as cases_router
from app.api.audit import router as audit_router
from app.api.investigation import router as investigation_router
from app.api.feedback import router as feedback_router
from app.api.auth import router as auth_router
from app.api.ai import router as ai_router
from app.api.tools import router as tools_router
from app.api.customers import router as customers_router
from app.api.merchants import router as merchants_router
from app.api.devices import router as devices_router
from app.api.network import router as network_router
from app.api.analytics import router as analytics_router
from app.api.rules import router as rules_router
from app.api.alerts import router as alerts_router
from app.api.operations import router as operations_router
from app.api.assistant import router as assistant_router
from app.core.config import settings
from app.middleware.rate_limit import get_rate_limiter, check_rate_limit


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

# CORS configuration - configurable, defaulting to secure settings
allowed_origins = []

# Only add development origins in non-production environments
if settings.app_env == "development":
    allowed_origins = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
else:
    # In production allow configured CORS origins if provided
    import os
    cors_env = os.getenv("CORS_ORIGINS", "")
    if cors_env:
        allowed_origins = [o.strip() for o in cors_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next: Callable) -> Response:
    """Add security headers to every response."""
    response = await call_next(request)
    
    # X-Content-Type-Options: Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # X-Frame-Options: Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    
    # Referrer-Policy: Control referrer information
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Content-Security-Policy: Restrict resource loading (configured for API)
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    
    # Strict-Transport-Security: Enable HTTPS only (for browsable APIs)
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    return response

# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next: Callable) -> Response:
    """Add X-Request-ID to every request/response for tracing."""
    # Get existing request ID if present (e.g., from proxies)
    existing_id = request.headers.get("X-Request-ID")
    request_id = existing_id or str(uuid.uuid4())
    
    # Add request ID to response headers
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    # Add request ID to request state for use in logging
    request.state.request_id = request_id
    
    return response

# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next: Callable) -> Response:
    """Apply rate limiting to requests."""
    # Skip rate limiting for health/readiness endpoints and testing
    path = request.url.path
    if path in ("/health", "/ready") or settings.app_env == "testing":
        return await call_next(request)
    
    # Check rate limit before processing
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
            status_code=429,
            headers=headers,
        )
    
    # Add rate limit info to response headers
    response = await call_next(request)
    response.headers["X-Rate-Limit-Limit"] = str(limiter.limit)
    response.headers["X-Rate-Limit-Remaining"] = str(info["remaining"])
    response.headers["X-Rate-Limit-Reset"] = str(info["reset"])
    return response


app.include_router(transactions_router)
app.include_router(cases_router)
app.include_router(audit_router)
app.include_router(investigation_router)
app.include_router(feedback_router)
app.include_router(auth_router)
app.include_router(ai_router)
app.include_router(tools_router)
app.include_router(customers_router)
app.include_router(merchants_router)
app.include_router(devices_router)
app.include_router(network_router)
app.include_router(analytics_router)
app.include_router(rules_router)
app.include_router(alerts_router)
app.include_router(operations_router)
app.include_router(assistant_router)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@app.get("/ready")
def readiness_check():
    """Readiness endpoint - verifies required dependencies."""
    from sqlalchemy import text
    from app.core.database import engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "unavailable"
    
    return {
        "database": db_status,
        "nemotron": "configured",  # Available status separate from health
        "service": settings.app_name,
        "environment": settings.app_env,
    }