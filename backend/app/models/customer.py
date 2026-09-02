from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Index, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    risk_tier: Mapped[str] = mapped_column(String(50), nullable=False, default="standard")
    kyc_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="customer", lazy="dynamic")

    __table_args__ = (
        Index("ix_customers_risk_tier", "risk_tier"),
    )

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, external_id={self.external_id}, risk_tier={self.risk_tier})>"