from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class FeedbackDecision(str, Enum):
    ACCEPT = "accept"
    MODIFY = "modify"
    REJECT = "reject"


class FeedbackCreate(BaseModel):
    decision: FeedbackDecision
    corrected_recommendation: Optional[str] = Field(None, max_length=50)
    reason: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: UUID
    investigation_id: UUID
    case_id: UUID
    decision: str
    corrected_recommendation: Optional[str] = None
    reason: Optional[str] = None
    actor: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeedbackListResponse(BaseModel):
    items: list[FeedbackResponse]
    total: int
    page: int
    page_size: int
    total_pages: int