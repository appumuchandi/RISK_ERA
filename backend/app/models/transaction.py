from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, ForeignKey, UniqueConstraint, Index, Numeric, DateTime, func, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.device import Device
    from app.models.merchant import Merchant
    from app.models.case import Case


class TransactionStatus(str, PyEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    REFUNDED = "refunded"
    FAILED = "failed"
    FLAGGED = "flagged"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(SQLEnum(TransactionStatus, name="transaction_status", create_type=True), nullable=False, default=TransactionStatus.PENDING)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    device_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id", ondelete="RESTRICT"), nullable=False, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    customer: Mapped["Customer"] = relationship("Customer", back_populates="transactions", lazy="selectin")
    device: Mapped[Optional["Device"]] = relationship("Device", back_populates="transactions", lazy="selectin")
    merchant: Mapped["Merchant"] = relationship("Merchant", back_populates="transactions", lazy="selectin")
    case: Mapped[Optional["Case"]] = relationship("Case", back_populates="transaction", uselist=False, lazy="selectin")

    __table_args__ = (
        UniqueConstraint("provider_event_id", name="uq_transactions_provider_event_id"),
        Index("ix_transactions_customer_id", "customer_id"),
        Index("ix_transactions_device_id", "device_id"),
        Index("ix_transactions_merchant_id", "merchant_id"),
        Index("ix_transactions_status", "status"),
        Index("ix_transactions_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, provider_event_id={self.provider_event_id}, amount={self.amount} {self.currency}, status={self.status})>"