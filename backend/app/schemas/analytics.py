from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class OverviewMetrics(BaseModel):
    total_transactions: int
    total_cases: int
    open_cases: int
    in_progress_cases: int
    escalated_cases: int
    high_risk_transactions: int
    critical_risk_transactions: int
    blocked_transactions: int
    review_transactions: int
    allowed_transactions: int
    total_transaction_value: Decimal
    average_transaction_value: Decimal


class RiskDistributionItem(BaseModel):
    risk_level: str  # low, medium, high, critical
    count: int
    percentage: float


class DecisionDistributionItem(BaseModel):
    decision: str  # allow, review, block
    count: int
    percentage: float


class TransactionTrendItem(BaseModel):
    date: str  # YYYY-MM-DD
    transaction_count: int
    transaction_value: Decimal
    high_risk_count: int
    blocked_count: int


class CaseTrendItem(BaseModel):
    date: str
    opened: int
    in_progress: int
    resolved: int
    confirmed_fraud: int  # closed_denied


class RuleTriggerStats(BaseModel):
    rule: str
    count: int
    action: str


class RiskConcentrationItem(BaseModel):
    id: str
    label: str
    type: str  # customer, merchant, device
    transaction_count: int
    high_risk_count: int
    blocked_count: int
    total_value: Decimal
    average_risk_score: float
    risk_level: str


class RiskConcentration(BaseModel):
    customers: List[RiskConcentrationItem] = Field(default_factory=list)
    merchants: List[RiskConcentrationItem] = Field(default_factory=list)
    devices: List[RiskConcentrationItem] = Field(default_factory=list)


class DashboardAnalytics(BaseModel):
    overview: OverviewMetrics
    risk_distribution: List[RiskDistributionItem]
    decision_distribution: List[DecisionDistributionItem]
    transaction_trend: List[TransactionTrendItem]
    case_trend: List[CaseTrendItem]
    top_triggered_rules: List[RuleTriggerStats]
    risk_concentration: RiskConcentration
    generated_at: datetime
    days: int
