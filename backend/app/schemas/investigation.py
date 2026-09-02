from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# --- Tool 1: get_transaction_history ---
class TransactionHistoryRequest(BaseModel):
    customer_id: UUID
    limit: int = Field(default=20, ge=1, le=100)
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class TransactionSummary(BaseModel):
    transaction_id: UUID
    provider_event_id: str
    amount: Decimal
    currency: str
    status: str
    merchant_name: Optional[str] = None
    merchant_category_code: Optional[str] = None
    created_at: datetime


class TransactionHistoryResponse(BaseModel):
    customer_id: UUID
    transactions: list[TransactionSummary]
    total_count: int


# --- Tool 2: get_customer_profile ---
class CustomerProfileRequest(BaseModel):
    customer_id: UUID


class CustomerProfileResponse(BaseModel):
    customer_id: UUID
    external_id: str
    risk_tier: str
    kyc_status: str
    created_at: datetime
    transaction_count: int
    total_amount: Decimal
    average_amount: Decimal
    unique_devices: int
    unique_merchants: int


# --- Tool 3: get_device_activity ---
class DeviceActivityRequest(BaseModel):
    device_id: UUID
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class DeviceActivityResponse(BaseModel):
    device_id: UUID
    fingerprint_hash: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    risk_score: Optional[float] = None
    transaction_count: int
    total_amount: Decimal
    unique_customers: int
    unique_merchants: int
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


# --- Tool result wrapper ---
class ToolResult(BaseModel):
    tool_name: str
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


# --- Investigation result ---
class Finding(BaseModel):
    finding_id: str
    description: str
    evidence_ids: list[UUID] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    source: str  # "tool" | "deterministic" | "nemotron"


class InvestigationRecommendation(str, Enum):
    APPROVE = "approve"
    REVIEW = "review"
    BLOCK = "block"


class InvestigationResult(BaseModel):
    case_id: UUID
    risk_assessment: str
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[Finding] = Field(default_factory=list)
    evidence_references: list[UUID] = Field(default_factory=list)
    recommendation: InvestigationRecommendation
    reasoning_summary: str
    missing_evidence: list[str] = Field(default_factory=list)
    investigation_timestamp: datetime = Field(default_factory=datetime.utcnow)
    ai_available: bool = True

    model_config = ConfigDict(use_enum_values=True)