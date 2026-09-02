from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List, Dict
from uuid import UUID

from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import Session, selectinload

from app.models import Transaction, Case, Rule, Customer, Merchant, Device
from app.models.alert import Alert, AlertStatus, AlertSeverity
from app.models.case import CaseStatus
from app.models.transaction import TransactionStatus
from app.schemas.transaction import TransactionAction
from app.services.rule_engine import RuleEngine, Rule as RuleEngineRule
from app.models.rule import RuleAction


def _get_enabled_rules(db: Session) -> List[RuleEngineRule]:
    rows = db.execute(select(Rule).where(Rule.enabled).order_by(Rule.priority)).scalars().all()
    return [
        RuleEngineRule(
            id=r.id,
            name=r.name,
            dsl_expression=r.dsl_expression,
            action=TransactionAction(r.action.value),
            priority=r.priority,
            enabled=r.enabled,
            version=r.version,
        )
        for r in rows
    ]


def _risk_level_from_score(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _severity_from_level(level: str) -> AlertSeverity:
    mapping = {"low": AlertSeverity.LOW, "medium": AlertSeverity.MEDIUM, "high": AlertSeverity.HIGH, "critical": AlertSeverity.CRITICAL}
    return mapping.get(level, AlertSeverity.MEDIUM)


def _priority_from_risk(severity: AlertSeverity, risk_score: float, decision: str, rule_priority: int) -> int:
    # Deterministic formula documented:
    # base by severity: critical 80, high 60, medium 30, low 10
    # + risk_score*0.2 (0-20)
    # + decision bonus: block 10, review 5, allow 0
    # + rule_priority/20 (0-5)
    # clamp 1-100, rounded
    base_map = {
        AlertSeverity.CRITICAL: 80,
        AlertSeverity.HIGH: 60,
        AlertSeverity.MEDIUM: 30,
        AlertSeverity.LOW: 10,
    }
    base = base_map.get(severity, 30)
    risk_component = (risk_score / 100.0) * 20
    decision_bonus = {"block": 10, "review": 5, "allow": 0}.get(decision.lower(), 0)
    rule_component = min(rule_priority / 20.0, 5)
    priority = base + risk_component + decision_bonus + rule_component
    return max(1, min(100, int(round(priority))))


class AlertService:
    def __init__(self, db: Session):
        self.db = db
        self._engine: Optional[RuleEngine] = None

    def _get_engine(self) -> RuleEngine:
        if self._engine is None:
            self._engine = RuleEngine(_get_enabled_rules(self.db))
        return self._engine

    def _compute_txn_risk(self, txn: Transaction):
        engine = self._get_engine()
        customer = txn.customer
        merchant = txn.merchant
        device = txn.device
        data = {
            "amount": txn.amount,
            "currency": txn.currency,
            "customer_risk_tier": customer.risk_tier if customer else "standard",
            "customer_kyc_status": customer.kyc_status if customer else "pending",
            "device_risk_score": float(device.risk_score) if device and device.risk_score is not None else None,
            "merchant_category_code": merchant.category_code if merchant else "",
            "merchant_risk_level": merchant.risk_level if merchant else "standard",
        }
        result = engine.evaluate(data)
        score = float(result.risk_score) if result.risk_score is not None else 0.0
        level = _risk_level_from_score(score)
        decision = result.final_action.value
        triggered = result.triggered_rules
        return score, level, decision, triggered

    def ensure_alerts_generated(self, limit: int = 200) -> int:
        """Generate alerts for transactions that meet alert criteria and don't already have open alerts.
        Returns number of alerts created.
        Deterministic deduplication on (transaction_id, rule_id, alert_type) for non-resolved/dismissed.
        """
        # Find transactions that qualify: BLOCK or HIGH/CRITICAL or REVIEW with risk >=50
        # Fetch recent transactions (created_at desc) up to limit*2 to scan
        txns = self.db.execute(
            select(Transaction)
            .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))
            .order_by(Transaction.created_at.desc())
            .limit(limit * 2)
        ).scalars().all()

        created = 0
        engine = self._get_engine()
        for txn in txns:
            score, level, decision, triggered = self._compute_txn_risk(txn)
            # Determine if qualifies
            qualifies = False
            alert_type = "high_risk_transaction"
            rule_id_for_alert = None
            title = ""
            desc = ""
            severity = _severity_from_level(level)

            if decision == "block" or level in ("high", "critical"):
                qualifies = True
                if triggered:
                    # Use highest priority triggered rule
                    top = max(triggered, key=lambda r: r.priority)
                    rule_id_for_alert = top.rule_id
                    alert_type = top.rule_name[:100]
                    title = f"{level.upper()} risk — {top.rule_name}"
                    desc = f"Transaction {txn.provider_event_id} triggered rule '{top.rule_name}' ({top.action.value}) with risk score {score:.1f} ({level}). Amount {txn.amount} {txn.currency}."
                else:
                    title = f"{level.upper()} risk transaction"
                    desc = f"Transaction {txn.provider_event_id} has {level} risk score {score:.1f} and decision {decision} without specific rule."
            elif decision == "review" and score >= 50:
                qualifies = True
                if triggered:
                    top = max(triggered, key=lambda r: r.priority)
                    rule_id_for_alert = top.rule_id
                    alert_type = top.rule_name[:100]
                    title = f"Review — {top.rule_name}"
                    desc = f"Transaction {txn.provider_event_id} requires review, rule '{top.rule_name}' triggered with score {score:.1f}."
                else:
                    title = "Review required"
                    desc = f"Transaction {txn.provider_event_id} requires review with score {score:.1f}."

            if not qualifies:
                continue

            # Deduplication: check existing open alert for same transaction+rule+type
            # Consider open, acknowledged, in_progress as active
            existing = self.db.execute(
                select(Alert)
                .where(
                    Alert.transaction_id == txn.id,
                    Alert.alert_type == alert_type,
                    Alert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED, AlertStatus.IN_PROGRESS]),
                )
            ).scalars().first()
            # For rule-specific, also check rule_id if present
            if existing:
                # If rule_id matches or both None, skip
                if (existing.rule_id == rule_id_for_alert) or (existing.rule_id is None and rule_id_for_alert is None):
                    continue
                # Also check if same transaction already has alert with same type but different rule, still allow? We'll deduplicate per transaction+type regardless of rule to avoid spam
                # So skip if any active alert for this transaction and type
                continue

            # Also check if transaction already has any active alert (limit one high-priority per transaction)
            # To avoid per-transaction spam, check if any active alert for this transaction exists
            any_active = self.db.execute(
                select(Alert).where(
                    Alert.transaction_id == txn.id,
                    Alert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED, AlertStatus.IN_PROGRESS]),
                )
            ).scalars().first()
            if any_active:
                continue

            # Derive priority deterministically
            rule_prio = max([r.priority for r in triggered], default=50) if triggered else 50
            priority = _priority_from_risk(severity, score, decision, rule_prio)

            alert = Alert(
                transaction_id=txn.id,
                case_id=txn.case.id if txn.case else None,
                rule_id=rule_id_for_alert,
                alert_type=alert_type,
                title=title[:255],
                description=desc,
                severity=severity,
                risk_score=score,
                decision=decision,
                status=AlertStatus.OPEN,
                priority=priority,
                assigned_to=None,
            )
            self.db.add(alert)
            created += 1
            if created >= limit:
                break
        if created:
            self.db.flush()
        return created

    def list_alerts(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        priority: Optional[int] = None,
        alert_type: Optional[str] = None,
        decision: Optional[str] = None,
        assigned_to: Optional[str] = None,
        search: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict:
        # Ensure alerts exist (lazy generation) - only if empty
        cnt = self.db.execute(select(func.count(Alert.id))).scalar() or 0
        if cnt == 0:
            self.ensure_alerts_generated(limit=100)
            # Don't double count; proceed

        base = select(Alert)
        count_q = select(func.count(Alert.id))

        if status:
            try:
                st = AlertStatus[status.upper()]
                base = base.where(Alert.status == st)
                count_q = count_q.where(Alert.status == st)
            except KeyError:
                raise ValueError(f"Invalid status: {status}")
        if severity:
            try:
                sev = AlertSeverity[severity.upper()]
                base = base.where(Alert.severity == sev)
                count_q = count_q.where(Alert.severity == sev)
            except KeyError:
                raise ValueError(f"Invalid severity: {severity}")
        if priority is not None:
            base = base.where(Alert.priority == priority)
            count_q = count_q.where(Alert.priority == priority)
        if alert_type:
            base = base.where(Alert.alert_type == alert_type)
            count_q = count_q.where(Alert.alert_type == alert_type)
        if decision:
            if decision.lower() not in ("allow", "review", "block"):
                raise ValueError(f"Invalid decision: {decision}")
            base = base.where(Alert.decision == decision.lower())
            count_q = count_q.where(Alert.decision == decision.lower())
        if assigned_to:
            base = base.where(Alert.assigned_to == assigned_to)
            count_q = count_q.where(Alert.assigned_to == assigned_to)
        if search:
            like = f"%{search}%"
            cond = or_(Alert.title.ilike(like), Alert.description.ilike(like), Alert.alert_type.ilike(like))
            base = base.where(cond)
            count_q = count_q.where(cond)
        if from_date:
            base = base.where(Alert.created_at >= from_date)
            count_q = count_q.where(Alert.created_at >= from_date)
        if to_date:
            base = base.where(Alert.created_at <= to_date)
            count_q = count_q.where(Alert.created_at <= to_date)

        total = self.db.execute(count_q).scalar() or 0
        total_pages = (total + page_size - 1) // page_size if total else 0

        # Sorting allowlist
        sort_map = {
            "created_at": Alert.created_at,
            "priority": Alert.priority,
            "risk_score": Alert.risk_score,
            "severity": Alert.severity,
        }
        if sort_by not in sort_map:
            raise ValueError(f"Invalid sort_by: {sort_by}")
        if sort_order not in ("asc", "desc"):
            raise ValueError(f"Invalid sort_order: {sort_order}")
        col = sort_map[sort_by]
        order = col.desc() if sort_order == "desc" else col.asc()
        base = base.order_by(order, Alert.id.desc()).offset((page - 1) * page_size).limit(page_size)

        alerts = self.db.execute(base).scalars().all()

        # Enrich with denormalized fields without N+1: batch fetch transactions, customers, merchants, rules
        txn_ids = [a.transaction_id for a in alerts if a.transaction_id]
        txns = {}
        if txn_ids:
            rows = self.db.execute(
                select(Transaction)
                .where(Transaction.id.in_(txn_ids))
                .options(selectinload(Transaction.customer), selectinload(Transaction.merchant))
            ).scalars().all()
            txns = {r.id: r for r in rows}
        rule_ids = [a.rule_id for a in alerts if a.rule_id]
        rules = {}
        if rule_ids:
            rows = self.db.execute(select(Rule).where(Rule.id.in_(rule_ids))).scalars().all()
            rules = {r.id: r for r in rows}

        items = []
        for a in alerts:
            txn = txns.get(a.transaction_id) if a.transaction_id else None
            rule = rules.get(a.rule_id) if a.rule_id else None
            items.append({
                "id": a.id,
                "transaction_id": a.transaction_id,
                "case_id": a.case_id,
                "rule_id": a.rule_id,
                "alert_type": a.alert_type,
                "title": a.title,
                "description": a.description,
                "severity": a.severity.value.lower() if hasattr(a.severity, "value") else str(a.severity).lower(),
                "risk_score": float(a.risk_score) if a.risk_score is not None else None,
                "decision": a.decision,
                "status": a.status.value.lower() if hasattr(a.status, "value") else str(a.status).lower(),
                "priority": a.priority,
                "assigned_to": a.assigned_to,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
                "resolved_at": a.resolved_at,
                "resolution_reason": a.resolution_reason,
                "provider_event_id": txn.provider_event_id if txn else None,
                "customer_label": txn.customer.external_id if txn and txn.customer else None,
                "merchant_name": txn.merchant.name if txn and txn.merchant else None,
                "rule_name": rule.name if rule else None,
            })

        return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}

    def get_alert(self, alert_id: UUID) -> Optional[dict]:
        a = self.db.execute(select(Alert).where(Alert.id == alert_id)).scalar_one_or_none()
        if not a:
            return None
        # Enrich similarly
        txn = None
        if a.transaction_id:
            txn = self.db.execute(
                select(Transaction)
                .where(Transaction.id == a.transaction_id)
                .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))
            ).scalar_one_or_none()
        rule = None
        if a.rule_id:
            rule = self.db.execute(select(Rule).where(Rule.id == a.rule_id)).scalar_one_or_none()
        case = None
        if a.case_id:
            case = self.db.execute(select(Case).where(Case.id == a.case_id)).scalar_one_or_none()
        return {
            "id": a.id,
            "transaction_id": a.transaction_id,
            "case_id": a.case_id,
            "rule_id": a.rule_id,
            "alert_type": a.alert_type,
            "title": a.title,
            "description": a.description,
            "severity": a.severity.value.lower() if hasattr(a.severity, "value") else str(a.severity).lower(),
            "risk_score": float(a.risk_score) if a.risk_score is not None else None,
            "decision": a.decision,
            "status": a.status.value.lower() if hasattr(a.status, "value") else str(a.status).lower(),
            "priority": a.priority,
            "assigned_to": a.assigned_to,
            "created_at": a.created_at,
            "updated_at": a.updated_at,
            "resolved_at": a.resolved_at,
            "resolution_reason": a.resolution_reason,
            "provider_event_id": txn.provider_event_id if txn else None,
            "customer_label": txn.customer.external_id if txn and txn.customer else None,
            "merchant_name": txn.merchant.name if txn and txn.merchant else None,
            "merchant_category_code": txn.merchant.category_code if txn and txn.merchant else None,
            "rule_name": rule.name if rule else None,
            "transaction": txn,
            "case": case,
            "rule": rule,
        }

    def _validate_transition(self, current: AlertStatus, new: AlertStatus):
        allowed = {
            AlertStatus.OPEN: [AlertStatus.ACKNOWLEDGED, AlertStatus.DISMISSED],
            AlertStatus.ACKNOWLEDGED: [AlertStatus.IN_PROGRESS, AlertStatus.DISMISSED, AlertStatus.RESOLVED],
            AlertStatus.IN_PROGRESS: [AlertStatus.RESOLVED, AlertStatus.DISMISSED],
            AlertStatus.RESOLVED: [],
            AlertStatus.DISMISSED: [],
        }
        if new not in allowed.get(current, []):
            raise ValueError(f"Invalid transition from {current.value} to {new.value}")

    def update_status(self, alert_id: UUID, new_status: str, actor: str, reason: Optional[str] = None) -> Optional[Alert]:
        a = self.db.execute(select(Alert).where(Alert.id == alert_id)).scalar_one_or_none()
        if not a:
            return None
        try:
            ns = AlertStatus[new_status.upper()]
        except KeyError:
            raise ValueError(f"Invalid status: {new_status}")
        self._validate_transition(a.status, ns)
        before = {"status": a.status.value}
        a.status = ns
        if ns in (AlertStatus.RESOLVED, AlertStatus.DISMISSED):
            a.resolved_at = datetime.now(timezone.utc)
            a.resolution_reason = reason
        a.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        # audit
        from app.services.audit_service import AuditService
        AuditService(self.db, actor=actor).log(actor=actor, action=f"alert_{ns.value}", resource_type="alert", resource_id=str(a.id), before=before, after={"status": ns.value, "reason": reason})
        return a

    def assign(self, alert_id: UUID, assignee: str, actor: str) -> Optional[Alert]:
        a = self.db.execute(select(Alert).where(Alert.id == alert_id)).scalar_one_or_none()
        if not a:
            return None
        before = {"assigned_to": a.assigned_to}
        a.assigned_to = assignee
        a.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        from app.services.audit_service import AuditService
        AuditService(self.db, actor=actor).log(actor=actor, action="alert_assigned", resource_type="alert", resource_id=str(a.id), before=before, after={"assigned_to": assignee})
        return a

    def resolve(self, alert_id: UUID, actor: str, reason: Optional[str] = None) -> Optional[Alert]:
        return self.update_status(alert_id, "resolved", actor, reason)

    def dismiss(self, alert_id: UUID, actor: str, reason: Optional[str] = None) -> Optional[Alert]:
        return self.update_status(alert_id, "dismissed", actor, reason)

    def create_case_from_alert(self, alert_id: UUID, actor: str) -> tuple[Optional[Alert], Optional[Case]]:
        a = self.db.execute(select(Alert).where(Alert.id == alert_id)).scalar_one_or_none()
        if not a:
            return None, None
        if a.case_id:
            case = self.db.execute(select(Case).where(Case.id == a.case_id)).scalar_one_or_none()
            return a, case
        if not a.transaction_id:
            raise ValueError("Alert has no transaction to create case from")
        # Check if case already exists for transaction
        existing = self.db.execute(select(Case).where(Case.transaction_id == a.transaction_id)).scalar_one_or_none()
        if existing:
            a.case_id = existing.id
            self.db.flush()
            from app.services.audit_service import AuditService
            AuditService(self.db, actor=actor).log(actor=actor, action="alert_case_linked", resource_type="alert", resource_id=str(a.id), before=None, after={"case_id": str(existing.id)})
            return a, existing
        # Create case
        from app.models.case import CaseStatus
        case = Case(transaction_id=a.transaction_id, status=CaseStatus.OPEN, assignee=actor)
        self.db.add(case)
        self.db.flush()
        a.case_id = case.id
        self.db.flush()
        from app.services.audit_service import AuditService
        AuditService(self.db, actor=actor).log(actor=actor, action="alert_case_created", resource_type="alert", resource_id=str(a.id), before=None, after={"case_id": str(case.id), "transaction_id": str(a.transaction_id)})
        # Also log case creation
        AuditService(self.db, actor=actor).log(actor=actor, action="case_created", resource_type="case", resource_id=str(case.id), before=None, after={"transaction_id": str(a.transaction_id)})
        return a, case

    def get_operations_summary(self) -> dict:
        # Ensure alerts generated
        cnt = self.db.execute(select(func.count(Alert.id))).scalar() or 0
        if cnt == 0:
            self.ensure_alerts_generated(limit=100)

        # Aggregates
        open_alerts = self.db.execute(select(func.count(Alert.id)).where(Alert.status == AlertStatus.OPEN)).scalar() or 0
        critical = self.db.execute(select(func.count(Alert.id)).where(Alert.severity == AlertSeverity.CRITICAL)).scalar() or 0
        high = self.db.execute(select(func.count(Alert.id)).where(Alert.severity == AlertSeverity.HIGH)).scalar() or 0
        ack = self.db.execute(select(func.count(Alert.id)).where(Alert.status == AlertStatus.ACKNOWLEDGED)).scalar() or 0
        in_prog = self.db.execute(select(func.count(Alert.id)).where(Alert.status == AlertStatus.IN_PROGRESS)).scalar() or 0
        unresolved = self.db.execute(select(func.count(Alert.id)).where(Alert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED, AlertStatus.IN_PROGRESS]))).scalar() or 0
        since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        last_24h = self.db.execute(select(func.count(Alert.id)).where(Alert.created_at >= since_24h)).scalar() or 0
        # Transactions aggregates via alert decision? Or via transactions table directly
        blocked_tx = self.db.execute(select(func.count(Transaction.id)).where(Transaction.status == TransactionStatus.FAILED)).scalar() or 0
        # Also count via alerts decision block?
        # Use alerts decision for blocked
        blocked_alerts = self.db.execute(select(func.count(Alert.id)).where(Alert.decision == "block")).scalar() or 0
        review_alerts = self.db.execute(select(func.count(Alert.id)).where(Alert.decision == "review")).scalar() or 0
        open_cases = self.db.execute(select(func.count(Case.id)).where(Case.status == CaseStatus.OPEN)).scalar() or 0
        escalated = self.db.execute(select(func.count(Case.id)).where(Case.status == CaseStatus.ESCALATED)).scalar() or 0
        avg_risk = self.db.execute(select(func.avg(Alert.risk_score))).scalar()
        avg_risk = float(avg_risk) if avg_risk is not None else 0.0
        # Highest priority alert
        highest = self.db.execute(select(Alert).order_by(Alert.priority.desc(), Alert.created_at.desc()).limit(1)).scalar_one_or_none()
        oldest_open = self.db.execute(select(Alert).where(Alert.status == AlertStatus.OPEN).order_by(Alert.created_at.asc()).limit(1)).scalar_one_or_none()
        oldest_age_hours = None
        if oldest_open and oldest_open.created_at:
            delta = datetime.now(timezone.utc) - oldest_open.created_at
            oldest_age_hours = round(delta.total_seconds() / 3600, 1)

        return {
            "open_alerts": open_alerts,
            "critical_alerts": critical,
            "high_alerts": high,
            "acknowledged_alerts": ack,
            "in_progress_alerts": in_prog,
            "unresolved_alerts": unresolved,
            "alerts_last_24h": last_24h,
            "blocked_transactions": blocked_tx,
            "review_transactions": review_alerts,  # using alert review count
            "open_cases": open_cases,
            "escalated_cases": escalated,
            "average_alert_risk": round(avg_risk, 2),
            "highest_priority_alert": {"id": str(highest.id), "priority": highest.priority, "title": highest.title} if highest else None,
            "oldest_open_alert_age_hours": oldest_age_hours,
            "generated_at": datetime.now(timezone.utc),
        }
