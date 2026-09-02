from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Index, Numeric, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    risk_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="device", lazy="dynamic")

    __table_args__ = (
        Index("ix_devices_fingerprint_hash", "fingerprint_hash"),
    )

    def __repr__(self) -> str:
        return f"<Device(id={self.id}, fingerprint_hash={self.fingerprint_hash[:16]}...)>"