from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID
import uuid

from pydantic import BaseModel, Field, ConfigDict


class GoldenCaseCategory(str, Enum):
    LEGITIMATE_TRANSACTION = "legitimate_transaction"
    HIGH_VALUE_ANOMALY = "high_value_anomaly"
    NEW_DEVICE = "new_device"
    VELOCITY_ANOMALY = "velocity_anomaly"
    RISKY_DEVICE = "risky_device"
    CUSTOMER_RISK_ANOMALY = "customer_risk_anomaly"
    MERCHANT_ANOMALY = "merchant_anomaly"
    MULTIPLE_SIMULTANEOUS_SIGNALS = "multiple_simultaneous_signals"
    CONFLICTING_SIGNALS = "conflicting_signals"
    AMBIGUOUS_CASE = "ambiguous_case"
    FALSE_POSITIVE_PRONE = "false_positive_prone"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class GoldenCaseDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    AMBIGUOUS = "ambiguous"


class GoldenCaseInput(BaseModel):
    provider_event_id: str
    amount: Decimal
    currency: str
    customer_external_id: str
    device_fingerprint_hash: Optional[str] = None
    device_ip: Optional[str] = None
    device_user_agent: Optional[str] = None
    merchant_name: str
    merchant_category_code: str
    raw_payload: dict = Field(default_factory=dict)


class GoldenCaseExpected(BaseModel):
    deterministic_action: str  # "allow", "review", "block"
    key_evidence_types: list[str] = Field(default_factory=list)  # e.g., ["transaction_history", "customer_profile"]
    investigation_recommendation: str  # "approve", "review", "block"
    rationale: str
    difficulty: GoldenCaseDifficulty
    category: GoldenCaseCategory


class GoldenCase(BaseModel):
    case_id: UUID = Field(default_factory=uuid.uuid4)
    name: str
    description: str
    input: GoldenCaseInput
    expected: GoldenCaseExpected
    category: GoldenCaseCategory
    difficulty: GoldenCaseDifficulty
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1

    model_config = ConfigDict(from_attributes=True)


class GoldenDataset(BaseModel):
    cases: list[GoldenCase]
    version: str
    created_at: datetime
    metadata: dict = Field(default_factory=dict)


class EvaluationMetric(str, Enum):
    RECOMMENDATION_ACCURACY = "recommendation_accuracy"
    EVIDENCE_GROUNDING_RATE = "evidence_grounding_rate"
    UNSUPPORTED_FINDING_RATE = "unsupported_finding_rate"
    TOOL_SELECTION_ACCURACY = "tool_selection_accuracy"
    AVG_TOOL_CALLS = "avg_tool_calls"
    INVESTIGATION_LATENCY_MS = "investigation_latency_ms"
    AI_AVAILABILITY_RATE = "ai_availability_rate"


class MetricResult(BaseModel):
    metric_name: str
    value: float
    description: str
    formula: str
    sample_count: int
    confidence_interval: Optional[tuple[float, float]] = None


class EvaluationResult(BaseModel):
    case_id: UUID
    investigation_id: UUID
    recommendation_accuracy: bool
    evidence_grounding_rate: float
    unsupported_finding_rate: float
    tool_selection_accuracy: Optional[float] = None
    tool_calls_count: int
    investigation_latency_ms: int
    ai_available: bool
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class EvaluationSummary(BaseModel):
    total_cases: int
    completed_investigations: int
    failed_investigations: int
    ai_unavailable_count: int
    metrics: list[MetricResult]
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)