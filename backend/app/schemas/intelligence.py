from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List
from uuid import UUID

from pydantic import BaseModel, Field


# Shared

class TriggeredRuleSummary(BaseModel):
    rule_name: str
    count: int
    action: str
    example_transaction_id: Optional[UUID] = None


class RecentTransactionItem(BaseModel):
    id: UUID
    provider_event_id: str
    amount: Decimal
    currency: str
    status: str
    merchant_name: Optional[str] = None
    merchant_id: Optional[UUID] = None
    device_id: Optional[UUID] = None
    risk_score: float
    risk_level: str
    decision: str
    triggered_rules: List[str] = Field(default_factory=list)
    created_at: datetime
    has_case: bool = False
    case_id: Optional[UUID] = None


class CaseSummary(BaseModel):
    total: int = 0
    open: int = 0
    in_progress: int = 0
    escalated: int = 0
    closed_approved: int = 0
    closed_denied: int = 0


# Customer

class CustomerProfile(BaseModel):
    customer_id: UUID
    external_id: str
    risk_tier: str
    kyc_status: str
    created_at: datetime
    # Transaction intelligence
    total_transactions: int
    total_amount: Decimal
    average_amount: Decimal
    average_transaction_amount: Optional[Decimal] = None
    min_amount: Optional[Decimal] = None
    min_transaction_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    max_transaction_amount: Optional[Decimal] = None
    first_transaction_at: Optional[datetime] = None
    last_transaction_at: Optional[datetime] = None
    # Risk
    average_risk_score: float
    max_risk_score: float
    maximum_risk_score: Optional[float] = None
    risk_level: str
    blocked_count: int
    review_count: int
    allowed_count: int
    flagged_count: int
    failed_count: int
    triggered_rule_frequency: Dict[str, int] = Field(default_factory=dict)
    top_triggered_rules: List[TriggeredRuleSummary] = Field(default_factory=list)
    # Relationships
    unique_merchants: int
    unique_devices: int
    recent_merchants: List[Dict] = Field(default_factory=list)
    recent_devices: List[Dict] = Field(default_factory=list)
    # Cases
    cases: CaseSummary
    # Flattened case counts for spec compatibility
    total_cases: Optional[int] = None
    open_cases: Optional[int] = None
    in_progress_cases: Optional[int] = None
    escalated_cases: Optional[int] = None
    # Recent activity
    recent_transactions: List[RecentTransactionItem] = Field(default_factory=list)
    # Explanation
    risk_explanation: str
    supporting_transaction_ids: List[UUID] = Field(default_factory=list)

    def model_post_init(self, __context):
        # Populate alias fields for spec compatibility
        if self.average_transaction_amount is None:
            object.__setattr__(self, 'average_transaction_amount', self.average_amount)
        if self.min_transaction_amount is None:
            object.__setattr__(self, 'min_transaction_amount', self.min_amount)
        if self.max_transaction_amount is None:
            object.__setattr__(self, 'max_transaction_amount', self.max_amount)
        if self.maximum_risk_score is None:
            object.__setattr__(self, 'maximum_risk_score', self.max_risk_score)
        if self.total_cases is None:
            object.__setattr__(self, 'total_cases', self.cases.total if self.cases else 0)
        if self.open_cases is None:
            object.__setattr__(self, 'open_cases', self.cases.open if self.cases else 0)
        if self.in_progress_cases is None:
            object.__setattr__(self, 'in_progress_cases', self.cases.in_progress if self.cases else 0)
        if self.escalated_cases is None:
            object.__setattr__(self, 'escalated_cases', self.cases.escalated if self.cases else 0)


class CustomerListItem(BaseModel):
    customer_id: UUID
    external_id: str
    risk_tier: str
    kyc_status: str
    created_at: datetime
    total_transactions: int
    total_amount: Decimal
    average_risk_score: float
    risk_level: str
    unique_merchants: int
    unique_devices: int
    total_cases: int


class CustomerListResponse(BaseModel):
    items: List[CustomerListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# Merchant

class MerchantProfile(BaseModel):
    merchant_id: UUID
    name: str
    category_code: str
    risk_level_merchant: str
    created_at: datetime
    total_transactions: int
    total_volume: Decimal
    average_amount: Decimal
    average_transaction_amount: Optional[Decimal] = None
    min_amount: Optional[Decimal] = None
    min_transaction_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    max_transaction_amount: Optional[Decimal] = None
    first_activity: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    average_risk_score: float
    max_risk_score: float
    maximum_risk_score: Optional[float] = None
    risk_level: str
    allowed_count: int
    review_count: int
    blocked_count: int
    flagged_count: int
    failed_count: int
    triggered_rule_frequency: Dict[str, int] = Field(default_factory=dict)
    top_triggered_rules: List[TriggeredRuleSummary] = Field(default_factory=list)
    unique_customers: int
    unique_devices: int
    recent_customers: List[Dict] = Field(default_factory=list)
    recent_devices: List[Dict] = Field(default_factory=list)
    cases: CaseSummary
    total_cases: Optional[int] = None
    open_cases: Optional[int] = None
    in_progress_cases: Optional[int] = None
    escalated_cases: Optional[int] = None
    recent_transactions: List[RecentTransactionItem] = Field(default_factory=list)
    risk_explanation: str
    supporting_transaction_ids: List[UUID] = Field(default_factory=list)

    def model_post_init(self, __context):
        if self.average_transaction_amount is None:
            object.__setattr__(self, 'average_transaction_amount', self.average_amount)
        if self.min_transaction_amount is None:
            object.__setattr__(self, 'min_transaction_amount', self.min_amount)
        if self.max_transaction_amount is None:
            object.__setattr__(self, 'max_transaction_amount', self.max_amount)
        if self.maximum_risk_score is None:
            object.__setattr__(self, 'maximum_risk_score', self.max_risk_score)
        if self.total_cases is None:
            object.__setattr__(self, 'total_cases', self.cases.total if self.cases else 0)
        if self.open_cases is None:
            object.__setattr__(self, 'open_cases', self.cases.open if self.cases else 0)
        if self.in_progress_cases is None:
            object.__setattr__(self, 'in_progress_cases', self.cases.in_progress if self.cases else 0)
        if self.escalated_cases is None:
            object.__setattr__(self, 'escalated_cases', self.cases.escalated if self.cases else 0)


class MerchantListItem(BaseModel):
    merchant_id: UUID
    name: str
    category_code: str
    risk_level: str
    created_at: datetime
    total_transactions: int
    total_volume: Decimal
    average_risk_score: float
    risk_level_computed: str
    unique_customers: int
    unique_devices: int
    total_cases: int


class MerchantListResponse(BaseModel):
    items: List[MerchantListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# Device

class DeviceProfile(BaseModel):
    device_id: UUID
    fingerprint_hash: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    risk_score_device: Optional[float] = None
    created_at: datetime
    total_transactions: int
    total_volume: Decimal
    average_amount: Decimal
    average_transaction_amount: Optional[Decimal] = None
    min_amount: Optional[Decimal] = None
    min_transaction_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    max_transaction_amount: Optional[Decimal] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    average_risk_score: float
    max_risk_score: float
    maximum_risk_score: Optional[float] = None
    risk_level: str
    allowed_count: int
    review_count: int
    blocked_count: int
    flagged_count: int
    failed_count: int
    triggered_rule_frequency: Dict[str, int] = Field(default_factory=dict)
    top_triggered_rules: List[TriggeredRuleSummary] = Field(default_factory=list)
    unique_customers: int
    unique_merchants: int
    recent_customers: List[Dict] = Field(default_factory=list)
    recent_merchants: List[Dict] = Field(default_factory=list)
    cases: CaseSummary
    total_cases: Optional[int] = None
    open_cases: Optional[int] = None
    in_progress_cases: Optional[int] = None
    escalated_cases: Optional[int] = None
    recent_transactions: List[RecentTransactionItem] = Field(default_factory=list)
    risk_explanation: str
    supporting_transaction_ids: List[UUID] = Field(default_factory=list)
    concentration_signal: str

    def model_post_init(self, __context):
        if self.average_transaction_amount is None:
            object.__setattr__(self, 'average_transaction_amount', self.average_amount)
        if self.min_transaction_amount is None:
            object.__setattr__(self, 'min_transaction_amount', self.min_amount)
        if self.max_transaction_amount is None:
            object.__setattr__(self, 'max_transaction_amount', self.max_amount)
        if self.maximum_risk_score is None:
            object.__setattr__(self, 'maximum_risk_score', self.max_risk_score)
        if self.total_cases is None:
            object.__setattr__(self, 'total_cases', self.cases.total if self.cases else 0)
        if self.open_cases is None:
            object.__setattr__(self, 'open_cases', self.cases.open if self.cases else 0)
        if self.in_progress_cases is None:
            object.__setattr__(self, 'in_progress_cases', self.cases.in_progress if self.cases else 0)
        if self.escalated_cases is None:
            object.__setattr__(self, 'escalated_cases', self.cases.escalated if self.cases else 0)


class DeviceListItem(BaseModel):
    device_id: UUID
    fingerprint_hash: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    risk_score_device: Optional[float] = None
    created_at: datetime
    total_transactions: int
    total_volume: Decimal
    average_risk_score: float
    risk_level: str
    unique_customers: int
    unique_merchants: int
    total_cases: int


class DeviceListResponse(BaseModel):
    items: List[DeviceListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
