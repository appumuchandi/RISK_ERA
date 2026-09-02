from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


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