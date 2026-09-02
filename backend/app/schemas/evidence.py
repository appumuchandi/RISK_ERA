from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class EvidenceCreate(BaseModel):
    source_type: str = Field(..., min_length=1, max_length=100)
    source_id: str = Field(..., min_length=1, max_length=255)
    payload: dict = Field(default_factory=dict)


class EvidenceResponse(BaseModel):
    id: UUID
    case_id: UUID
    source_type: str
    source_id: str
    payload: dict
    retrieved_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvidenceListResponse(BaseModel):
    items: list[EvidenceResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class EvidenceFilter(BaseModel):
    source_type: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)