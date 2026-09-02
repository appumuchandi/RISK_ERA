from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, ForeignKey, Index, DateTime, func, Enum as SQLEnum, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.feedback import AnalystFeedback


class InvestigationStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    model_provider: Mapped[str] = mapped_column(String(100), nullable=False, default="nvidia")
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, default="nemotron-3.5-lightning-30b-a3b")
    model_available: Mapped[bool] = mapped_column(nullable=False, default=False)

    risk_assessment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reasoning_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    findings: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    evidence_references: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    missing_evidence: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    tool_calls: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    tool_calls_count: Mapped[int] = mapped_column(default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(nullable=True)

    status: Mapped[InvestigationStatus] = mapped_column(
        SQLEnum(InvestigationStatus, name="investigation_status", create_type=True),
        nullable=False,
        default=InvestigationStatus.PENDING
    )

    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="investigations", lazy="selectin")
    feedback: Mapped[list["AnalystFeedback"]] = relationship("AnalystFeedback", back_populates="investigation", lazy="dynamic", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_investigations_case_id", "case_id"),
        Index("ix_investigations_status", "status"),
        Index("ix_investigations_started_at", "started_at"),
        Index("ix_investigations_completed_at", "completed_at"),
    )

    def __repr__(self) -> str:
        return f"<Investigation(id={self.id}, case_id={self.case_id}, status={self.status}, recommendation={self.recommendation})>"