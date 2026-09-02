from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class CaseStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED_APPROVED = "closed_approved"
    CLOSED_DENIED = "closed_denied"
    ESCALATED = "escalated"


class CaseAction(str, Enum):
    ASSIGN = "assign"
    REASSIGN = "reassign"
    STATUS_CHANGE = "status_change"
    CLOSE = "close"
    ESCALATE = "escalate"


class CaseCreate(BaseModel):
    transaction_id: UUID
    assignee: Optional[str] = None


class CaseUpdate(BaseModel):
    status: Optional[CaseStatus] = None
    assignee: Optional[str] = None


class CaseResponse(BaseModel):
    id: UUID
    transaction_id: UUID
    status: CaseStatus
    assignee: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaseDetail(CaseResponse):
    transaction: Optional[dict] = None
    evidence_count: int = 0


class CaseListResponse(BaseModel):
    items: list[CaseResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CaseFilter(BaseModel):
    status: Optional[CaseStatus] = None
    assignee: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)