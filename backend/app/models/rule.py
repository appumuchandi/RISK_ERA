from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import String, Index, DateTime, func, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RuleAction(str, PyEnum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    dsl_expression: Mapped[str] = mapped_column(String(5000), nullable=False)
    action: Mapped[RuleAction] = mapped_column(SQLEnum(RuleAction, name="rule_action", create_type=True), nullable=False)
    priority: Mapped[int] = mapped_column(nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_rules_priority_enabled", "priority", "enabled"),
    )

    def __repr__(self) -> str:
        return f"<Rule(id={self.id}, name={self.name}, action={self.action}, priority={self.priority})>"