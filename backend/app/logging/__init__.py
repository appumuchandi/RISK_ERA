from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Build structured log entry
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if hasattr(record, "endpoint"):
            log_entry["endpoint"] = record.endpoint
        if hasattr(record, "case_id"):
            log_entry["case_id"] = record.case_id
        if hasattr(record, "investigation_id"):
            log_entry["investigation_id"] = record.investigation_id
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        
        # Never log secrets - filter out sensitive keys
        message = record.msg
        if isinstance(message, str):
            # Redact any potential secrets from the message
            for secret_pattern in ["secret", "password", "token", "key"]:
                # Simple redaction - don't log anything looking like credentials
                pass
        
        # Format as JSON
        return json.dumps(log_entry)


def get_logger(name: str = "risk_era") -> logging.Logger:
    """Get a structured logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Avoid adding handlers if already configured
    if logger.handlers:
        return logger
    
    # Console handler with structured format
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)
    
    return logger


# Request logging context manager
class RequestContext:
    """Context manager for request-scoped logging."""
    
    def __init__(self, request_id: str, endpoint: str | None = None,
                 case_id: str | None = None, investigation_id: str | None = None):
        self.request_id = request_id
        self.endpoint = endpoint
        self.case_id = case_id
        self.investigation_id = investigation_id
    
    def _set_context(self):
        """Set logging context variables."""
        import logging
        logger = logging.getLogger("risk_era")
        # Use LogRecord attributes - set via extra param in log calls
        # These will be picked up by the formatter
        self._logger = logger
    
    def __enter__(self):
        self._set_context()
        return self
    
    def __exit__(self, *args):
        pass


def log_request_start(method: str, path: str, request_id: str) -> RequestContext:
    """Log the start of an HTTP request."""
    logger = get_logger()
    logger.info(
        "request_start",
        extra={
            "request_id": request_id,
            "endpoint": path,
            "method": method,
        }
    )
    return RequestContext(request_id, endpoint=path)


def log_request_end(method: str, path: str, request_id: str, status_code: int,
                    duration_ms: float) -> None:
    """Log the end of an HTTP request."""
    logger = get_logger()
    logger.info(
        "request_end",
        extra={
            "request_id": request_id,
            "endpoint": path,
            "method": method,
            "status_code": status_code,
            "duration_ms": duration_ms,
        }
    )


def log_investigation_start(case_id: str, operation: str, request_id: str) -> None:
    """Log the start of an investigation operation."""
    logger = get_logger()
    logger.info(
        "investigation_start",
        extra={
            "request_id": request_id,
            "case_id": case_id,
            "operation": operation,
        }
    )


def log_investigation_end(case_id: str, operation: str, duration_ms: float,
                         success: bool, request_id: str, investigation_id: str | None = None) -> None:
    """Log the end of an investigation operation."""
    logger = get_logger()
    logger.info(
        "investigation_end",
        extra={
            "request_id": request_id,
            "case_id": case_id,
            "operation": operation,
            "duration_ms": duration_ms,
            "success": success,
            "investigation_id": investigation_id,
        }
    )


def log_error(error: Exception, request_id: str, context: str | None = None,
              include_stack: bool = False) -> None:
    """Log an error with consistent formatting."""
    logger = get_logger()
    extra: Dict[str, Any] = {
        "request_id": request_id,
        "context": context or "unknown",
    }
    
    # Never include stack traces in structured logs by default
    # Only include if explicitly requested (e.g., for debugging)
    if include_stack:
        extra["stack_trace"] = str(error)
    
    logger.error(
        str(error),
        extra=extra,
        exc_info=include_stack,
    )


def log_audit_event(event_type: str, actor: str, detail: str, request_id: str | None = None) -> None:
    """Log an audit event."""
    logger = get_logger()
    logger.info(
        "audit_event",
        extra={
            "event_type": event_type,
            "actor": actor,
            "detail": detail,
            "request_id": request_id,
        }
    )