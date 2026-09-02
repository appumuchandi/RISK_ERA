from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RuleResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    enabled: bool
    priority: int
    action: str
    condition: str  # dsl_expression
    dsl_expression: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    version: int = 1

    model_config = {"from_attributes": True}


class RuleListResponse(BaseModel):
    items: List[RuleResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RuleExplainItem(BaseModel):
    rule_id: UUID
    rule_name: str
    action: str
    priority: int
    matched: bool
    explanation: str
    dsl_expression: str
    condition: str


class RiskExplainResponse(BaseModel):
    transaction_id: UUID
    provider_event_id: str
    amount: str
    currency: str
    risk_score: float
    risk_level: str
    decision: str  # allow/review/block
    triggered_rules: List[RuleExplainItem]
    evaluated_rules: List[RuleExplainItem]
    decision_reason: str
    score_breakdown: dict
    factors: dict
