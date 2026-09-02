from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditAction(str):
    CASE_CREATED = "CASE_CREATED"
    CASE_ASSIGNED = "CASE_ASSIGNED"
    CASE_STATUS_CHANGED = "CASE_STATUS_CHANGED"
    CASE_CLOSED = "CASE_CLOSED"
    EVIDENCE_ADDED = "EVIDENCE_ADDED"
    RULE_CHANGED = "RULE_CHANGED"


class AuditLogResponse(BaseModel):
    id: UUID
    actor: str
    action: str
    resource_type: str
    resource_id: str
    before_json: Optional[dict] = None
    after_json: Optional[dict] = None
    prev_hash: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AuditLogFilter(BaseModel):
    actor: Optional[str] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)