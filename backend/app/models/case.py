from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, ForeignKey, Index, DateTime, func, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.transaction import Transaction
    from app.models.evidence import Evidence
    from app.models.investigation import Investigation
    from app.models.feedback import AnalystFeedback


class CaseStatus(str, PyEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED_APPROVED = "closed_approved"
    CLOSED_DENIED = "closed_denied"
    ESCALATED = "escalated"


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True)
    status: Mapped[CaseStatus] = mapped_column(SQLEnum(CaseStatus, name="case_status", create_type=True), nullable=False, default=CaseStatus.OPEN)
    assignee: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="case", lazy="selectin")
    evidence: Mapped[list["Evidence"]] = relationship("Evidence", back_populates="case", lazy="dynamic", cascade="all, delete-orphan")
    investigations: Mapped[list["Investigation"]] = relationship("Investigation", back_populates="case", lazy="dynamic", order_by="Investigation.started_at.desc()")
    feedback: Mapped[list["AnalystFeedback"]] = relationship("AnalystFeedback", back_populates="case", lazy="dynamic", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_cases_status", "status"),
        Index("ix_cases_assignee", "assignee"),
        Index("ix_cases_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Case(id={self.id}, transaction_id={self.transaction_id}, status={self.status})>"