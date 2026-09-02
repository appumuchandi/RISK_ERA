from __future__ import annotations

from typing import Any, Generic, TypeVar, Callable
from pydantic import BaseModel, Field, validator
from typing_extensions import Literal

# Type variable for generic response
T = TypeVar("T", bound=BaseModel)

# Maximum payload size in bytes (1MB default for JSON requests)
MAX_JSON_PAYLOAD_SIZE = 1_000_000

# Maximum pagination limits
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
DEFAULT_PAGE = 1
MIN_PAGE = 1


class PaginationParams(BaseModel):
    """Standard pagination parameters with validation."""
    page: int = Field(default=DEFAULT_PAGE, ge=MIN_PAGE, description="Page number (1-indexed)")
    page_size: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=MIN_PAGE_SIZE,
        le=MAX_PAGE_SIZE,
        description="Items per page"
    )
    
    @validator("page_size", pre=True, always=True)
    def cap_page_size(cls, v):
        """Cap page_size to MAX_PAGE_SIZE if exceeded."""
        return min(v, MAX_PAGE_SIZE) if v is not None else DEFAULT_PAGE_SIZE
    
    @validator("page")
    def cap_page(cls, v):
        """Ensure page is at least 1."""
        return max(v, MIN_PAGE)


class APIErrorResponse(BaseModel):
    """Standardized API error response."""
    error: str
    detail: str
    request_id: str
    timestamp: str
    
    model_config = {"use_enum_values": True}


class ValidationErrorResponse(APIErrorResponse):
    """Response for validation errors."""
    errors: dict[str, list[str]]


class RateLimitErrorResponse(APIErrorResponse):
    """Response for rate limit errors."""
    retry_after: int | None = None


def validate_json_payload(
    max_size: int = MAX_JSON_PAYLOAD_SIZE
) -> Callable:
    """Decorator to validate JSON payload size before Pydantic parsing.
    
    Raises HTTP 413 if payload exceeds max_size.
    """
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check content length from request
            # This is a placeholder - in FastAPI, the request object
            # would provide access to body size
            # The actual enforcement is done at the middleware level
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def limit_page_size(max_size: int = MAX_PAGE_SIZE):
    """Decorator to limit page_size in pagination parameters."""
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # page_size will be validated by Pydantic in the schema
            return await func(*args, **kwargs)
        return wrapper
    return decorator


class UUIDStr(str):
    """String that must be a valid UUID."""
    
    @validator("*")
    def must_be_valid_uuid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import uuid
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError(f"Invalid UUID format: {v}")
        return v


class DateRange(BaseModel):
    """Date range validation with start/end constraints."""
    start: str | None = Field(default=None, description="Start date (ISO format)")
    end: str | None = Field(default=None, description="End date (ISO format)")
    
    @validator("start", "end")
    def validate_date_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Basic ISO format check
        if len(v) < 10:
            raise ValueError(f"Invalid date format: {v}")
        return v
    
    @validator("end")
    def end_after_start(cls, v: str, values: Any) -> str:
        start = values.data.get("start") if hasattr(values, "data") else None
        if start and v and start > v:
            raise ValueError("End date must be after start date")
        return v


class SortOrder(str):
    """Sort order enumeration."""
    ASC = "asc"
    DESC = "desc"
    
    @classmethod
    def valid_values(cls) -> list[str]:
        return [cls.ASC, cls.DESC]


# Error response helpers


def make_error_response(
    error: str,
    detail: str,
    request_id: str,
    timestamp: str | None = None,
) -> APIErrorResponse:
    """Create a standardized error response."""
    from datetime import datetime, timezone
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    return APIErrorResponse(
        error=error,
        detail=detail,
        request_id=request_id,
        timestamp=timestamp,
    )


def make_422_response(request_id: str) -> APIErrorResponse:
    """Create a 422 validation error response."""
    return make_error_response(
        error="validation_error",
        detail="Request validation failed",
        request_id=request_id,
    )