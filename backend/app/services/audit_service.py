from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.auth import authenticate_token


# Standardized audit event types
class AuditEventType:
    """Standardized audit event types for consistent logging."""
    AUTHENTICATION_SUCCESS = "authentication_success"
    AUTHENTICATION_FAILED = "authentication_failed"
    AUTHORIZATION_SUCCESS = "authorization_success"
    AUTHORIZATION_DENIED = "authorization_denied"
    INVESTIGATION_STARTED = "investigation_started"
    INVESTIGATION_COMPLETED = "investigation_completed"
    EVIDENCE_ADDED = "evidence_added"
    RATE_LIMITED = "rate_limited"
    CASE_CREATED = "case_created"
    CASE_UPDATED = "case_updated"


class AuditService:
    def __init__(self, db: Session, actor: str | None = None):
        self.db = db
        self.actor = actor or self._derive_actor()

    def _derive_actor(self) -> str:
        """Derive actor from authentication context."""
        # Try to authenticate token from context
        # This would be set by the middleware/dependency injection
        return "system"

    def log(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        before: Optional[dict] = None,
        after: Optional[dict] = None,
    ) -> AuditLog:
        """Log an audit event with hash chain integrity."""
        prev_hash = self._get_latest_hash()

        audit_entry = AuditLog(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            before_json=before,
            after_json=after,
            prev_hash=prev_hash,
        )
        self.db.add(audit_entry)
        self.db.flush()
        return audit_entry

    def log_authentication(self, success: bool, actor: str | None = None, detail: str = "") -> None:
        """Log authentication events."""
        action = (
            AuditEventType.AUTHENTICATION_SUCCESS
            if success
            else AuditEventType.AUTHENTICATION_FAILED
        )
        actual_actor = actor or (self.actor or "unknown")
        self.log(
            actor=actual_actor,
            action=action,
            resource_type="authentication",
            resource_id="session",
            before=None,
            after={"detail": detail, "actor": actual_actor},
        )

    def log_authorization(self, allowed: bool, permission: str | None = None) -> None:
        """Log authorization events."""
        action = (
            AuditEventType.AUTHORIZATION_SUCCESS
            if allowed
            else AuditEventType.AUTHORIZATION_DENIED
        )
        detail = permission or ""
        self.log(
            actor=self.actor,
            action=action,
            resource_type="authorization",
            resource_id="permission",
            before=None,
            after={"permission": detail, "allowed": allowed},
        )

    def log_rate_limited(self, endpoint: str, actor: str | None = None) -> None:
        """Log rate limiting events."""
        actual_actor = actor or (self.actor or "unknown")
        self.log(
            actor=actual_actor,
            action=AuditEventType.RATE_LIMITED,
            resource_type="rate_limit",
            resource_id=endpoint,
            before=None,
            after={"endpoint": endpoint, "actor": actual_actor},
        )

    def log_investigation_started(self, case_id: str, actor: str | None = None) -> None:
        """Log investigation start."""
        actual_actor = actor or (self.actor or "unknown")
        self.log(
            actor=actual_actor,
            action=AuditEventType.INVESTIGATION_STARTED,
            resource_type="investigation",
            resource_id=case_id,
            after={"case_id": case_id, "actor": actual_actor},
        )

    def log_investigation_completed(self, case_id: str, duration_ms: float, actor: str | None = None) -> None:
        """Log investigation completion."""
        actual_actor = actor or (self.actor or "unknown")
        self.log(
            actor=actual_actor,
            action=AuditEventType.INVESTIGATION_COMPLETED,
            resource_type="investigation",
            resource_id=case_id,
            after={"case_id": case_id, "duration_ms": duration_ms, "actor": actual_actor},
        )

    def _get_latest_hash(self) -> Optional[str]:
        stmt = (
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        result = self.db.execute(stmt).scalar_one_or_none()
        if not result:
            return None
        return self.compute_hash(result)

    def compute_hash(self, entry: AuditLog) -> str:
        data = {
            "actor": entry.actor,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "before_json": entry.before_json,
            "after_json": entry.after_json,
            "prev_hash": entry.prev_hash,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode()).hexdigest()

    def verify_chain(self, limit: int = 1000) -> tuple[bool, Optional[str]]:
        stmt = (
            select(AuditLog)
            .order_by(AuditLog.created_at.asc())
            .limit(limit)
        )
        entries = self.db.execute(stmt).scalars().all()

        if not entries:
            return True, None

        expected_prev = None
        for entry in entries:
            computed = self.compute_hash(entry)
            if entry.prev_hash != expected_prev:
                return False, f"Hash chain broken at entry {entry.id}: expected prev_hash={expected_prev}, got {entry.prev_hash}"
            expected_prev = computed

        return True, None

    def get_audit_logs(
        self,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[AuditLog], int]:
        from sqlalchemy import func, or_

        # Validate sort_by allow-list
        allowed_sort = {"created_at", "actor", "action", "resource_type"}
        if sort_by not in allowed_sort:
            raise ValueError(f"Invalid sort_by: {sort_by}")
        if sort_order not in ("asc", "desc"):
            raise ValueError(f"Invalid sort_order: {sort_order}")

        stmt = select(AuditLog)
        count_stmt = select(func.count(AuditLog.id))

        if actor:
            stmt = stmt.where(AuditLog.actor == actor)
            count_stmt = count_stmt.where(AuditLog.actor == actor)
        if action:
            stmt = stmt.where(AuditLog.action == action)
            count_stmt = count_stmt.where(AuditLog.action == action)
        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
            count_stmt = count_stmt.where(AuditLog.resource_type == resource_type)
        if resource_id:
            stmt = stmt.where(AuditLog.resource_id == resource_id)
            count_stmt = count_stmt.where(AuditLog.resource_id == resource_id)
        if date_from:
            from datetime import datetime
            # Query param + may be decoded as space, fix
            df = date_from.replace(" ", "+")
            dt = datetime.fromisoformat(df.replace("Z", "+00:00"))
            stmt = stmt.where(AuditLog.created_at >= dt)
            count_stmt = count_stmt.where(AuditLog.created_at >= dt)
        if date_to:
            from datetime import datetime
            dt_raw = date_to.replace(" ", "+")
            dt = datetime.fromisoformat(dt_raw.replace("Z", "+00:00"))
            stmt = stmt.where(AuditLog.created_at <= dt)
            count_stmt = count_stmt.where(AuditLog.created_at <= dt)
        if search:
            like = f"%{search}%"
            cond = or_(
                AuditLog.actor.ilike(like),
                AuditLog.action.ilike(like),
                AuditLog.resource_type.ilike(like),
                AuditLog.resource_id.ilike(like),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = self.db.execute(count_stmt).scalar() or 0
        # Sorting deterministic with secondary id
        sort_col_map = {
            "created_at": AuditLog.created_at,
            "actor": AuditLog.actor,
            "action": AuditLog.action,
            "resource_type": AuditLog.resource_type,
        }
        col = sort_col_map[sort_by]
        order = col.desc() if sort_order == "desc" else col.asc()
        stmt = stmt.order_by(order, AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
        items = self.db.execute(stmt).scalars().all()

        return list(items), total

    def get_summary(self, from_date: Optional[str] = None, to_date: Optional[str] = None) -> dict:
        from sqlalchemy import func, distinct

        # Base filter for time window
        base_filter = []
        if from_date:
            from datetime import datetime
            df = from_date.replace(" ", "+")
            dt = datetime.fromisoformat(df.replace("Z", "+00:00"))
            base_filter.append(AuditLog.created_at >= dt)
        if to_date:
            from datetime import datetime
            dt_raw = to_date.replace(" ", "+")
            dt = datetime.fromisoformat(dt_raw.replace("Z", "+00:00"))
            base_filter.append(AuditLog.created_at <= dt)

        def count_with_filter(extra=None):
            stmt = select(func.count(AuditLog.id))
            if base_filter:
                for f in base_filter:
                    stmt = stmt.where(f)
            if extra is not None:
                stmt = stmt.where(extra)
            return self.db.execute(stmt).scalar() or 0

        total = count_with_filter()
        if base_filter:
            stmt = select(func.count(distinct(AuditLog.actor)))
            for f in base_filter:
                stmt = stmt.where(f)
            unique_actors = self.db.execute(stmt).scalar() or 0
        else:
            unique_actors = self.db.execute(select(func.count(distinct(AuditLog.actor)))).scalar() or 0

        case_actions = count_with_filter(AuditLog.resource_type == "case")
        investigation_actions = count_with_filter(AuditLog.resource_type == "investigation")
        evidence_actions = count_with_filter(AuditLog.resource_type == "evidence")
        alert_actions = count_with_filter(AuditLog.resource_type == "alert")
        status_changes = count_with_filter(AuditLog.action.ilike("%status%"))
        assignment_changes = count_with_filter(AuditLog.action.ilike("%assign%"))

        # Latest event
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(1)
        if base_filter:
            for f in base_filter:
                stmt = stmt.where(f)
        latest = self.db.execute(stmt).scalars().first()
        latest_ts = latest.created_at.isoformat() if latest and latest.created_at else None

        # First event
        stmt_first = select(AuditLog).order_by(AuditLog.created_at.asc()).limit(1)
        if base_filter:
            for f in base_filter:
                stmt_first = stmt_first.where(f)
        first = self.db.execute(stmt_first).scalars().first()
        first_ts = first.created_at.isoformat() if first and first.created_at else None

        return {
            "total": total,
            "unique_actors": unique_actors,
            "case_actions": case_actions,
            "investigation_actions": investigation_actions,
            "evidence_actions": evidence_actions,
            "alert_actions": alert_actions,
            "status_changes": status_changes,
            "assignment_changes": assignment_changes,
            "latest_event_at": latest_ts,
            "first_event_at": first_ts,
        }