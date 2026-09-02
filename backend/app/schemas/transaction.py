from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class TransactionAction(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


class TriggeredRule(BaseModel):
    rule_id: UUID
    rule_name: str
    action: TransactionAction
    priority: int
    dsl_expression: str


class TransactionIngestRequest(BaseModel):
    provider_event_id: str = Field(..., min_length=1, max_length=255)
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(..., min_length=3, max_length=3, pattern="^[A-Z]{3}$")
    customer_external_id: str = Field(..., min_length=1, max_length=255)
    device_fingerprint_hash: Optional[str] = Field(None, max_length=64)
    device_ip: Optional[str] = Field(None, max_length=45)
    device_user_agent: Optional[str] = Field(None, max_length=512)
    merchant_name: str = Field(..., min_length=1, max_length=255)
    merchant_category_code: str = Field(..., min_length=1, max_length=50)
    raw_payload: dict = Field(default_factory=dict)


class TransactionIngestResponse(BaseModel):
    transaction_id: UUID
    provider_event_id: str
    action: TransactionAction
    risk_score: Optional[float] = None
    triggered_rules: list[TriggeredRule] = Field(default_factory=list)
    case_id: Optional[UUID] = None
    is_new_transaction: bool

    model_config = ConfigDict(from_attributes=True)


class TransactionDetail(BaseModel):
    id: UUID
    provider_event_id: str
    amount: Decimal
    currency: str
    status: str
    customer_id: UUID
    device_id: Optional[UUID]
    merchant_id: UUID
    raw_payload: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionListItem(BaseModel):
    id: UUID
    provider_event_id: str
    amount: Decimal
    currency: str
    status: str
    customer_id: UUID
    device_id: Optional[UUID]
    merchant_id: UUID
    raw_payload: dict
    created_at: datetime
    # Intelligence
    risk_score: float
    risk_level: str  # low|medium|high|critical
    decision: TransactionAction
    triggered_rules: list[TriggeredRule] = Field(default_factory=list)
    # Case linkage
    has_case: bool = False
    case_id: Optional[UUID] = None
    case_status: Optional[str] = None
    # Denormalized for UX
    customer_external_id: Optional[str] = None
    merchant_name: Optional[str] = None
    merchant_category_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TransactionListResponse(BaseModel):
    items: list[TransactionListItem]
    total: int
    page: int
    page_size: int
    total_pages: int