from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class AlertResponse(BaseModel):
    id: UUID
    transaction_id: Optional[UUID] = None
    case_id: Optional[UUID] = None
    rule_id: Optional[UUID] = None
    alert_type: str
    title: str
    description: str
    severity: str
    risk_score: Optional[float] = None
    decision: str
    status: str
    priority: int
    assigned_to: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_reason: Optional[str] = None
    provider_event_id: Optional[str] = None
    customer_label: Optional[str] = None
    merchant_name: Optional[str] = None
    rule_name: Optional[str] = None

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    items: List[AlertResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AlertDetailResponse(BaseModel):
    id: UUID
    transaction_id: Optional[UUID] = None
    case_id: Optional[UUID] = None
    rule_id: Optional[UUID] = None
    alert_type: str
    title: str
    description: str
    severity: str
    risk_score: Optional[float] = None
    decision: str
    status: str
    priority: int
    assigned_to: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_reason: Optional[str] = None
    provider_event_id: Optional[str] = None
    customer_label: Optional[str] = None
    merchant_name: Optional[str] = None
    merchant_category_code: Optional[str] = None
    rule_name: Optional[str] = None
    # full objects not exposed, but we include ids
    model_config = {"from_attributes": True}


class OperationsSummaryResponse(BaseModel):
    open_alerts: int
    critical_alerts: int
    high_alerts: int
    acknowledged_alerts: int
    in_progress_alerts: int
    unresolved_alerts: int
    alerts_last_24h: int
    blocked_transactions: int
    review_transactions: int
    open_cases: int
    escalated_cases: int
    average_alert_risk: float
    highest_priority_alert: Optional[dict] = None
    oldest_open_alert_age_hours: Optional[float] = None
    generated_at: datetime
