from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, ForeignKey, Index, DateTime, func, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.investigation import Investigation
    from app.models.case import Case


class FeedbackDecision(str, PyEnum):
    ACCEPT = "accept"
    MODIFY = "modify"
    REJECT = "reject"


class AnalystFeedback(Base):
    __tablename__ = "analyst_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)

    decision: Mapped[str] = mapped_column(SQLEnum(FeedbackDecision, name="feedback_decision", create_type=True), nullable=False)
    corrected_recommendation: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    actor: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    investigation: Mapped["Investigation"] = relationship("Investigation", back_populates="feedback", lazy="selectin")
    case: Mapped["Case"] = relationship("Case", back_populates="feedback", lazy="selectin")

    __table_args__ = (
        Index("ix_analyst_feedback_investigation_id", "investigation_id"),
        Index("ix_analyst_feedback_case_id", "case_id"),
        Index("ix_analyst_feedback_actor", "actor"),
        Index("ix_analyst_feedback_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AnalystFeedback(id={self.id}, investigation_id={self.investigation_id}, decision={self.decision})>"