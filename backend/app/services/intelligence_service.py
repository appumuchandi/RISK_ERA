from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from app.models import Customer, Merchant, Device, Transaction, Case, Rule
from app.models.transaction import TransactionStatus
from app.models.case import CaseStatus
from app.schemas.transaction import TransactionAction
from app.services.rule_engine import RuleEngine, Rule as RuleEngineRule


def _get_enabled_rules(db: Session) -> list[RuleEngineRule]:
    stmt = select(Rule).where(Rule.enabled).order_by(Rule.priority)
    rows = db.execute(stmt).scalars().all()
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


def _compute_risk_for_txn(txn: Transaction, engine: RuleEngine):
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
    decision = result.final_action
    triggered_names = [r.rule_name for r in result.triggered_rules]
    triggered_full = result.triggered_rules
    return score, level, decision, triggered_names, triggered_full


def _case_summary_from_cases(cases: list[Case]) -> dict:
    counts = Counter()
    for c in cases:
        try:
            counts[c.status.value] += 1
        except Exception:
            counts[str(c.status)] += 1
    return {
        "total": len(cases),
        "open": counts.get("open", 0),
        "in_progress": counts.get("in_progress", 0),
        "escalated": counts.get("escalated", 0),
        "closed_approved": counts.get("closed_approved", 0),
        "closed_denied": counts.get("closed_denied", 0),
    }


class IntelligenceService:
    def __init__(self, db: Session):
        self.db = db
        self._engine: Optional[RuleEngine] = None
        self._cached_rules: Optional[list[RuleEngineRule]] = None

    def _engine_cached(self) -> RuleEngine:
        if self._engine is None:
            self._engine = RuleEngine(self._get_cached_rules())
        return self._engine

    def _get_cached_rules(self) -> list[RuleEngineRule]:
        if self._cached_rules is None:
            self._cached_rules = _get_enabled_rules(self.db)
        return self._cached_rules

    # --- Customer ---

    def get_customer_profile(self, customer_id: UUID):
        customer = self.db.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()
        if not customer:
            return None

        # Fetch transactions for customer with relationships
        txns = self.db.execute(
            select(Transaction)
            .where(Transaction.customer_id == customer_id)
            .options(selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.customer), selectinload(Transaction.case))
            .order_by(Transaction.created_at.desc())
        ).scalars().all()

        engine = self._engine_cached()

        # Compute per-txn risk
        risk_scores: List[float] = []
        triggered_counter = Counter()
        triggered_first_txn: Dict[str, UUID] = {}
        decision_counts = Counter()
        status_counts = Counter()
        recent_merchants_map: Dict[UUID, dict] = {}
        recent_devices_map: Dict[UUID, dict] = {}
        recent_txns_data = []

        total_amount = Decimal("0")
        min_amount: Optional[Decimal] = None
        max_amount: Optional[Decimal] = None
        amounts: List[Decimal] = []

        for txn in txns:
            score, level, decision, triggered_names, triggered_full = _compute_risk_for_txn(txn, engine)
            risk_scores.append(score)
            for name in triggered_names:
                triggered_counter[name] += 1
                if name not in triggered_first_txn:
                    triggered_first_txn[name] = txn.id
            decision_counts[decision.value] += 1
            status_counts[txn.status.value] += 1
            total_amount += txn.amount
            amounts.append(txn.amount)
            if min_amount is None or txn.amount < min_amount:
                min_amount = txn.amount
            if max_amount is None or txn.amount > max_amount:
                max_amount = txn.amount

            # relationships
            if txn.merchant_id and txn.merchant_id not in recent_merchants_map and txn.merchant:
                recent_merchants_map[txn.merchant_id] = {
                    "merchant_id": str(txn.merchant_id),
                    "name": txn.merchant.name,
                    "category_code": txn.merchant.category_code,
                    "last_used": txn.created_at.isoformat(),
                }
            if txn.device_id and txn.device_id not in recent_devices_map and txn.device:
                recent_devices_map[txn.device_id] = {
                    "device_id": str(txn.device_id),
                    "fingerprint_hash": txn.device.fingerprint_hash,
                    "ip": txn.device.ip,
                    "last_used": txn.created_at.isoformat(),
                }

        # Cases for customer
        cases = []
        if txns:
            txn_ids = [t.id for t in txns]
            cases = self.db.execute(select(Case).where(Case.transaction_id.in_(txn_ids))).scalars().all()

        case_summary = _case_summary_from_cases(cases)

        # Recent transactions (10)
        recent_sorted = sorted(txns, key=lambda t: t.created_at, reverse=True)[:10]
        recent_transactions = []
        supporting_ids: List[UUID] = []
        for txn in recent_sorted:
            score, level, decision, triggered_names, _ = _compute_risk_for_txn(txn, engine)
            # Need merchant name
            recent_transactions.append({
                "id": txn.id,
                "provider_event_id": txn.provider_event_id,
                "amount": txn.amount,
                "currency": txn.currency,
                "status": txn.status.value,
                "merchant_name": txn.merchant.name if txn.merchant else None,
                "merchant_id": txn.merchant_id,
                "device_id": txn.device_id,
                "risk_score": round(score, 2),
                "risk_level": level,
                "decision": decision.value,
                "triggered_rules": triggered_names,
                "created_at": txn.created_at,
                "has_case": txn.case is not None,
                "case_id": txn.case.id if txn.case else None,
            })
            if score >= 60:
                supporting_ids.append(txn.id)

        # Risk explanation
        if not txns:
            risk_explanation = "No transactions observed for this customer."
            avg_score = 0.0
            max_score = 0.0
            risk_level = "low"
        else:
            avg_score = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0
            max_score = max(risk_scores) if risk_scores else 0.0
            risk_level = _risk_level_from_score(avg_score)
            # Build explanation from real data
            parts = []
            if decision_counts.get("block", 0) > 0:
                parts.append(f"{decision_counts['block']} blocked transaction(s)")
            if decision_counts.get("review", 0) > 0:
                parts.append(f"{decision_counts['review']} review-flagged")
            if triggered_counter:
                top = triggered_counter.most_common(2)
                parts.append(f"top rules: {', '.join([f'{k} ({v})' for k, v in top])}")
            if len(set(recent_merchants_map)) > 3:
                parts.append(f"{len(recent_merchants_map)} merchants")
            if len(set(recent_devices_map)) > 1:
                parts.append(f"{len(recent_devices_map)} devices")
            if not parts:
                parts.append("no high-risk patterns in available transactions")
            risk_explanation = " · ".join(parts) + "."
            # supporting includes high-risk txns and top rule example
            if triggered_first_txn:
                for _, tid in list(triggered_first_txn.items())[:3]:
                    if tid not in supporting_ids:
                        supporting_ids.append(tid)
            supporting_ids = supporting_ids[:5]

        # Unique counts
        unique_merchants = len(set(t.merchant_id for t in txns))
        unique_devices = len(set(t.device_id for t in txns if t.device_id))

        # Top triggered rules summary - reuse cached rules to avoid extra DB queries
        cached_rules = self._get_cached_rules()
        rule_action_map = {r.name: r.action.value for r in cached_rules}
        top_triggered = []
        for name, cnt in triggered_counter.most_common(5):
            top_triggered.append({
                "rule_name": name,
                "count": cnt,
                "action": rule_action_map.get(name, "review"),
                "example_transaction_id": triggered_first_txn.get(name),
            })

        # Amounts avg
        avg_amount = (total_amount / len(txns)) if txns else Decimal("0")
        first_at = min((t.created_at for t in txns), default=None)
        last_at = max((t.created_at for t in txns), default=None)

        # Build response dict matching schema
        return {
            "customer_id": customer.id,
            "external_id": customer.external_id,
            "risk_tier": customer.risk_tier,
            "kyc_status": customer.kyc_status,
            "created_at": customer.created_at,
            "total_transactions": len(txns),
            "total_amount": total_amount,
            "average_amount": avg_amount,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "first_transaction_at": first_at,
            "last_transaction_at": last_at,
            "average_risk_score": round(avg_score, 2) if txns else 0.0,
            "max_risk_score": round(max_score, 2) if txns else 0.0,
            "risk_level": risk_level if txns else "low",
            "blocked_count": decision_counts.get("block", 0),
            "review_count": decision_counts.get("review", 0),
            "allowed_count": decision_counts.get("allow", 0),
            "flagged_count": status_counts.get("flagged", 0),
            "failed_count": status_counts.get("failed", 0),
            "triggered_rule_frequency": dict(triggered_counter),
            "top_triggered_rules": top_triggered,
            "unique_merchants": unique_merchants,
            "unique_devices": unique_devices,
            "recent_merchants": list(recent_merchants_map.values())[:5],
            "recent_devices": list(recent_devices_map.values())[:5],
            "cases": case_summary,
            "recent_transactions": recent_transactions,
            "risk_explanation": risk_explanation,
            "supporting_transaction_ids": supporting_ids,
        }

    def list_customers(self, page: int, page_size: int, search: Optional[str] = None, risk_tier: Optional[str] = None):
        # Base query
        base = select(Customer)
        count_stmt = select(func.count(Customer.id))

        if search:
            like = f"%{search}%"
            base = base.where(Customer.external_id.ilike(like))
            count_stmt = count_stmt.where(Customer.external_id.ilike(like))
        if risk_tier:
            base = base.where(Customer.risk_tier == risk_tier)
            count_stmt = count_stmt.where(Customer.risk_tier == risk_tier)

        total = self.db.execute(count_stmt).scalar() or 0
        total_pages = (total + page_size - 1) // page_size if total else 0
        base = base.order_by(Customer.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        customers = self.db.execute(base).scalars().all()

        if not customers:
            return {"items": [], "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}

        # Fetch transactions for these customers in one query
        cust_ids = [c.id for c in customers]
        txns = self.db.execute(
            select(Transaction)
            .where(Transaction.customer_id.in_(cust_ids))
            .options(selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.customer), selectinload(Transaction.case))
        ).scalars().all()

        # Group
        by_customer: Dict[UUID, List[Transaction]] = defaultdict(list)
        for t in txns:
            by_customer[t.customer_id].append(t)

        engine = self._engine_cached()
        # For case counts, fetch cases for these txn ids
        all_txn_ids = [t.id for t in txns]
        cases = []
        if all_txn_ids:
            cases = self.db.execute(select(Case).where(Case.transaction_id.in_(all_txn_ids))).scalars().all()
        cases_by_txn = {c.transaction_id: c for c in cases}
        # Count cases per customer
        cases_per_customer = Counter()
        for t in txns:
            if t.id in cases_by_txn:
                cases_per_customer[t.customer_id] += 1

        items = []
        for cust in customers:
            c_txns = by_customer.get(cust.id, [])
            total_amt = sum((t.amount for t in c_txns), Decimal("0"))
            if c_txns:
                scores = []
                for t in c_txns:
                    s, _, _, _, _ = _compute_risk_for_txn(t, engine)
                    scores.append(s)
                avg_score = sum(scores) / len(scores) if scores else 0.0
                risk_level = _risk_level_from_score(avg_score)
            else:
                avg_score = 0.0
                risk_level = "low"
            unique_merchants = len(set(t.merchant_id for t in c_txns))
            unique_devices = len(set(t.device_id for t in c_txns if t.device_id))
            items.append({
                "customer_id": cust.id,
                "external_id": cust.external_id,
                "risk_tier": cust.risk_tier,
                "kyc_status": cust.kyc_status,
                "created_at": cust.created_at,
                "total_transactions": len(c_txns),
                "total_amount": total_amt,
                "average_risk_score": round(float(avg_score), 2),
                "risk_level": risk_level,
                "unique_merchants": unique_merchants,
                "unique_devices": unique_devices,
                "total_cases": cases_per_customer.get(cust.id, 0),
            })

        return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}

    # --- Merchant ---

    def get_merchant_profile(self, merchant_id: UUID):
        merchant = self.db.execute(select(Merchant).where(Merchant.id == merchant_id)).scalar_one_or_none()
        if not merchant:
            return None

        txns = self.db.execute(
            select(Transaction)
            .where(Transaction.merchant_id == merchant_id)
            .options(selectinload(Transaction.customer), selectinload(Transaction.device), selectinload(Transaction.merchant), selectinload(Transaction.case))
            .order_by(Transaction.created_at.desc())
        ).scalars().all()

        engine = self._engine_cached()
        risk_scores = []
        triggered_counter = Counter()
        triggered_first: Dict[str, UUID] = {}
        decision_counts = Counter()
        status_counts = Counter()
        recent_customers_map: Dict[UUID, dict] = {}
        recent_devices_map: Dict[UUID, dict] = {}

        total_volume = Decimal("0")
        min_amount: Optional[Decimal] = None
        max_amount: Optional[Decimal] = None

        for txn in txns:
            score, _, decision, triggered_names, _ = _compute_risk_for_txn(txn, engine)
            risk_scores.append(score)
            for n in triggered_names:
                triggered_counter[n] += 1
                if n not in triggered_first:
                    triggered_first[n] = txn.id
            decision_counts[decision.value] += 1
            status_counts[txn.status.value] += 1
            total_volume += txn.amount
            if min_amount is None or txn.amount < min_amount:
                min_amount = txn.amount
            if max_amount is None or txn.amount > max_amount:
                max_amount = txn.amount
            if txn.customer_id not in recent_customers_map and txn.customer:
                recent_customers_map[txn.customer_id] = {"customer_id": str(txn.customer_id), "external_id": txn.customer.external_id, "risk_tier": txn.customer.risk_tier, "last_used": txn.created_at.isoformat()}
            if txn.device_id and txn.device_id not in recent_devices_map and txn.device:
                recent_devices_map[txn.device_id] = {"device_id": str(txn.device_id), "fingerprint_hash": txn.device.fingerprint_hash, "ip": txn.device.ip, "last_used": txn.created_at.isoformat()}

        cases = []
        if txns:
            txn_ids = [t.id for t in txns]
            cases = self.db.execute(select(Case).where(Case.transaction_id.in_(txn_ids))).scalars().all()
        case_summary = _case_summary_from_cases(cases)

        recent_sorted = sorted(txns, key=lambda t: t.created_at, reverse=True)[:10]
        recent_transactions = []
        supporting: List[UUID] = []
        for txn in recent_sorted:
            score, level, decision, triggered_names, _ = _compute_risk_for_txn(txn, engine)
            recent_transactions.append({
                "id": txn.id,
                "provider_event_id": txn.provider_event_id,
                "amount": txn.amount,
                "currency": txn.currency,
                "status": txn.status.value,
                "merchant_name": merchant.name,
                "merchant_id": txn.merchant_id,
                "device_id": txn.device_id,
                "risk_score": round(score, 2),
                "risk_level": level,
                "decision": decision.value,
                "triggered_rules": triggered_names,
                "created_at": txn.created_at,
                "has_case": txn.case is not None,
                "case_id": txn.case.id if txn.case else None,
            })
            if score >= 60:
                supporting.append(txn.id)

        if not txns:
            avg_score = 0.0
            max_score = 0.0
            risk_level = "low"
            risk_explanation = "No transactions for this merchant."
        else:
            avg_score = sum(risk_scores) / len(risk_scores)
            max_score = max(risk_scores)
            risk_level = _risk_level_from_score(avg_score)
            parts = []
            if decision_counts.get("block", 0):
                parts.append(f"{decision_counts['block']} blocked")
            if decision_counts.get("review", 0):
                parts.append(f"{decision_counts['review']} review")
            if triggered_counter:
                top = triggered_counter.most_common(2)
                parts.append(f"top rules {', '.join([f'{k} ({v})' for k,v in top])}")
            if len(recent_customers_map) > 10:
                parts.append(f"{len(recent_customers_map)} customers")
            if not parts:
                parts.append("no elevated patterns")
            risk_explanation = " · ".join(parts) + "."
            for _, tid in list(triggered_first.items())[:3]:
                if tid not in supporting:
                    supporting.append(tid)
            supporting = supporting[:5]

        unique_customers = len(set(t.customer_id for t in txns))
        unique_devices = len(set(t.device_id for t in txns if t.device_id))
        cached_rules = self._get_cached_rules()
        rule_action_map = {r.name: r.action.value for r in cached_rules}
        top_triggered = []
        for name, cnt in triggered_counter.most_common(5):
            top_triggered.append({"rule_name": name, "count": cnt, "action": rule_action_map.get(name, "review"), "example_transaction_id": triggered_first.get(name)})

        avg_amount = (total_volume / len(txns)) if txns else Decimal("0")
        first_at = min((t.created_at for t in txns), default=None)
        last_at = max((t.created_at for t in txns), default=None)

        return {
            "merchant_id": merchant.id,
            "name": merchant.name,
            "category_code": merchant.category_code,
            "risk_level_merchant": merchant.risk_level,
            "created_at": merchant.created_at,
            "total_transactions": len(txns),
            "total_volume": total_volume,
            "average_amount": avg_amount,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "first_activity": first_at,
            "last_activity": last_at,
            "average_risk_score": round(avg_score, 2) if txns else 0.0,
            "max_risk_score": round(max_score, 2) if txns else 0.0,
            "risk_level": risk_level if txns else "low",
            "allowed_count": decision_counts.get("allow", 0),
            "review_count": decision_counts.get("review", 0),
            "blocked_count": decision_counts.get("block", 0),
            "flagged_count": status_counts.get("flagged", 0),
            "failed_count": status_counts.get("failed", 0),
            "triggered_rule_frequency": dict(triggered_counter),
            "top_triggered_rules": top_triggered,
            "unique_customers": unique_customers,
            "unique_devices": unique_devices,
            "recent_customers": list(recent_customers_map.values())[:5],
            "recent_devices": list(recent_devices_map.values())[:5],
            "cases": case_summary,
            "recent_transactions": recent_transactions,
            "risk_explanation": risk_explanation,
            "supporting_transaction_ids": supporting,
        }

    def list_merchants(self, page: int, page_size: int, search: Optional[str] = None):
        base = select(Merchant)
        count_stmt = select(func.count(Merchant.id))
        if search:
            like = f"%{search}%"
            base = base.where(Merchant.name.ilike(like) | Merchant.category_code.ilike(like))
            count_stmt = count_stmt.where(Merchant.name.ilike(like) | Merchant.category_code.ilike(like))
        total = self.db.execute(count_stmt).scalar() or 0
        total_pages = (total + page_size - 1)//page_size if total else 0
        base = base.order_by(Merchant.created_at.desc()).offset((page-1)*page_size).limit(page_size)
        merchants = self.db.execute(base).scalars().all()
        if not merchants:
            return {"items": [], "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}
        m_ids = [m.id for m in merchants]
        txns = self.db.execute(select(Transaction).where(Transaction.merchant_id.in_(m_ids)).options(selectinload(Transaction.customer), selectinload(Transaction.device), selectinload(Transaction.merchant), selectinload(Transaction.case))).scalars().all()
        by_merchant: Dict[UUID, List[Transaction]] = defaultdict(list)
        for t in txns:
            by_merchant[t.merchant_id].append(t)
        engine = self._engine_cached()
        all_txn_ids = [t.id for t in txns]
        cases = []
        if all_txn_ids:
            cases = self.db.execute(select(Case).where(Case.transaction_id.in_(all_txn_ids))).scalars().all()
        cases_by_txn = {c.transaction_id: c for c in cases}
        cases_per_merchant = Counter()
        for t in txns:
            if t.id in cases_by_txn:
                cases_per_merchant[t.merchant_id] += 1

        items = []
        for m in merchants:
            m_txns = by_merchant.get(m.id, [])
            total_vol = sum((t.amount for t in m_txns), Decimal("0"))
            if m_txns:
                scores = []
                for t in m_txns:
                    s, _, _, _, _ = _compute_risk_for_txn(t, engine)
                    scores.append(s)
                avg = sum(scores)/len(scores)
                level = _risk_level_from_score(avg)
            else:
                avg = 0.0
                level = "low"
            uniq_cust = len(set(t.customer_id for t in m_txns))
            uniq_dev = len(set(t.device_id for t in m_txns if t.device_id))
            items.append({
                "merchant_id": m.id,
                "name": m.name,
                "category_code": m.category_code,
                "risk_level": m.risk_level,
                "created_at": m.created_at,
                "total_transactions": len(m_txns),
                "total_volume": total_vol,
                "average_risk_score": round(float(avg),2),
                "risk_level_computed": level,
                "unique_customers": uniq_cust,
                "unique_devices": uniq_dev,
                "total_cases": cases_per_merchant.get(m.id, 0),
            })
        return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}

    # --- Device ---

    def get_device_activity(self, device_id: UUID):
        device = self.db.execute(select(Device).where(Device.id == device_id)).scalar_one_or_none()
        if not device:
            return None
        txns = self.db.execute(
            select(Transaction)
            .where(Transaction.device_id == device_id)
            .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))
            .order_by(Transaction.created_at.desc())
        ).scalars().all()
        engine = self._engine_cached()
        risk_scores = []
        triggered_counter = Counter()
        triggered_first: Dict[str, UUID] = {}
        decision_counts = Counter()
        status_counts = Counter()
        recent_customers_map: Dict[UUID, dict] = {}
        recent_merchants_map: Dict[UUID, dict] = {}
        total_volume = Decimal("0")
        min_amount: Optional[Decimal] = None
        max_amount: Optional[Decimal] = None

        for txn in txns:
            score, _, decision, triggered_names, _ = _compute_risk_for_txn(txn, engine)
            risk_scores.append(score)
            for n in triggered_names:
                triggered_counter[n] += 1
                if n not in triggered_first:
                    triggered_first[n] = txn.id
            decision_counts[decision.value] += 1
            status_counts[txn.status.value] += 1
            total_volume += txn.amount
            if min_amount is None or txn.amount < min_amount:
                min_amount = txn.amount
            if max_amount is None or txn.amount > max_amount:
                max_amount = txn.amount
            if txn.customer_id not in recent_customers_map and txn.customer:
                recent_customers_map[txn.customer_id] = {"customer_id": str(txn.customer_id), "external_id": txn.customer.external_id, "risk_tier": txn.customer.risk_tier, "last_used": txn.created_at.isoformat()}
            if txn.merchant_id not in recent_merchants_map and txn.merchant:
                recent_merchants_map[txn.merchant_id] = {"merchant_id": str(txn.merchant_id), "name": txn.merchant.name, "category_code": txn.merchant.category_code, "last_used": txn.created_at.isoformat()}

        cases = []
        if txns:
            txn_ids = [t.id for t in txns]
            cases = self.db.execute(select(Case).where(Case.transaction_id.in_(txn_ids))).scalars().all()
        case_summary = _case_summary_from_cases(cases)

        recent_sorted = sorted(txns, key=lambda t: t.created_at, reverse=True)[:10]
        recent_transactions = []
        supporting: List[UUID] = []
        for txn in recent_sorted:
            score, level, decision, triggered_names, _ = _compute_risk_for_txn(txn, engine)
            recent_transactions.append({
                "id": txn.id,
                "provider_event_id": txn.provider_event_id,
                "amount": txn.amount,
                "currency": txn.currency,
                "status": txn.status.value,
                "merchant_name": txn.merchant.name if txn.merchant else None,
                "merchant_id": txn.merchant_id,
                "device_id": txn.device_id,
                "risk_score": round(score,2),
                "risk_level": level,
                "decision": decision.value,
                "triggered_rules": triggered_names,
                "created_at": txn.created_at,
                "has_case": txn.case is not None,
                "case_id": txn.case.id if txn.case else None,
            })
            if score >= 60:
                supporting.append(txn.id)

        if not txns:
            avg_score = 0.0
            max_score = 0.0
            risk_level = "low"
            explanation = "No transactions observed for this device."
            concentration = "No activity"
        else:
            avg_score = sum(risk_scores)/len(risk_scores)
            max_score = max(risk_scores)
            risk_level = _risk_level_from_score(avg_score)
            # Concentration signal - neutral terminology
            uniq_cust = len(set(t.customer_id for t in txns))
            uniq_merch = len(set(t.merchant_id for t in txns))
            if uniq_cust > 5:
                concentration = f"Elevated concentration — {uniq_cust} customers share this device"
            elif uniq_cust > 1:
                concentration = f"Moderate concentration — {uniq_cust} customers, {uniq_merch} merchants"
            else:
                concentration = f"Single-customer device — {uniq_merch} merchant(s)"
            parts = [concentration]
            if decision_counts.get("block",0):
                parts.append(f"{decision_counts['block']} blocked")
            if decision_counts.get("review",0):
                parts.append(f"{decision_counts['review']} review")
            if triggered_counter:
                top = triggered_counter.most_common(1)[0]
                parts.append(f"top rule {top[0]} ({top[1]})")
            explanation = " · ".join(parts) + "."
            for _, tid in list(triggered_first.items())[:2]:
                if tid not in supporting:
                    supporting.append(tid)
            supporting = supporting[:5]

        uniq_cust = len(set(t.customer_id for t in txns))
        uniq_merch = len(set(t.merchant_id for t in txns))
        cached_rules = self._get_cached_rules()
        rule_action_map = {r.name: r.action.value for r in cached_rules}
        top_triggered=[]
        for name,cnt in triggered_counter.most_common(5):
            top_triggered.append({"rule_name": name, "count": cnt, "action": rule_action_map.get(name, "review"), "example_transaction_id": triggered_first.get(name)})

        avg_amount = (total_volume/len(txns)) if txns else Decimal("0")
        first_at = min((t.created_at for t in txns), default=None)
        last_at = max((t.created_at for t in txns), default=None)

        # Need concentration for response as well
        if not txns:
            conc_signal = "No activity"
        else:
            uniq_c = len(set(t.customer_id for t in txns))
            uniq_m = len(set(t.merchant_id for t in txns))
            if uniq_c > 5:
                conc_signal = f"Elevated concentration — {uniq_c} customers share this device"
            elif uniq_c > 1:
                conc_signal = f"Moderate concentration — {uniq_c} customers, {uniq_m} merchants"
            else:
                conc_signal = f"Single-customer device — {uniq_m} merchant(s)"

        return {
            "device_id": device.id,
            "fingerprint_hash": device.fingerprint_hash,
            "ip": device.ip,
            "user_agent": device.user_agent,
            "risk_score_device": float(device.risk_score) if device.risk_score is not None else None,
            "created_at": device.created_at,
            "total_transactions": len(txns),
            "total_volume": total_volume,
            "average_amount": avg_amount,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "first_seen": first_at,
            "last_seen": last_at,
            "average_risk_score": round(avg_score,2) if txns else 0.0,
            "max_risk_score": round(max_score,2) if txns else 0.0,
            "risk_level": risk_level if txns else "low",
            "allowed_count": decision_counts.get("allow",0),
            "review_count": decision_counts.get("review",0),
            "blocked_count": decision_counts.get("block",0),
            "flagged_count": status_counts.get("flagged",0),
            "failed_count": status_counts.get("failed",0),
            "triggered_rule_frequency": dict(triggered_counter),
            "top_triggered_rules": top_triggered,
            "unique_customers": len(set(t.customer_id for t in txns)),
            "unique_merchants": len(set(t.merchant_id for t in txns)),
            "recent_customers": list(recent_customers_map.values())[:5],
            "recent_merchants": list(recent_merchants_map.values())[:5],
            "cases": case_summary,
            "recent_transactions": recent_transactions,
            "risk_explanation": explanation if txns else "No transactions observed for this device.",
            "supporting_transaction_ids": supporting,
            "concentration_signal": conc_signal,
        }

    def list_devices(self, page: int, page_size: int, search: Optional[str]=None):
        base = select(Device)
        count_stmt = select(func.count(Device.id))
        if search:
            like = f"%{search}%"
            base = base.where(Device.fingerprint_hash.ilike(like) | Device.ip.ilike(like))
            count_stmt = count_stmt.where(Device.fingerprint_hash.ilike(like) | Device.ip.ilike(like))
        total = self.db.execute(count_stmt).scalar() or 0
        total_pages = (total + page_size -1)//page_size if total else 0
        base = base.order_by(Device.created_at.desc()).offset((page-1)*page_size).limit(page_size)
        devices = self.db.execute(base).scalars().all()
        if not devices:
            return {"items": [], "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}
        d_ids = [d.id for d in devices]
        txns = self.db.execute(select(Transaction).where(Transaction.device_id.in_(d_ids)).options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))).scalars().all()
        by_device: Dict[UUID, List[Transaction]] = defaultdict(list)
        for t in txns:
            if t.device_id:
                by_device[t.device_id].append(t)
        engine = self._engine_cached()
        all_txn_ids = [t.id for t in txns]
        cases=[]
        if all_txn_ids:
            cases=self.db.execute(select(Case).where(Case.transaction_id.in_(all_txn_ids))).scalars().all()
        cases_by_txn={c.transaction_id: c for c in cases}
        cases_per_device=Counter()
        for t in txns:
            if t.id in cases_by_txn:
                if t.device_id:
                    cases_per_device[t.device_id]+=1
        items=[]
        for d in devices:
            d_txns=by_device.get(d.id, [])
            total_vol=sum((t.amount for t in d_txns), Decimal("0"))
            if d_txns:
                scores=[]
                for t in d_txns:
                    s,_,_,_,_= _compute_risk_for_txn(t, engine)
                    scores.append(s)
                avg=sum(scores)/len(scores)
                level=_risk_level_from_score(avg)
            else:
                avg=0.0
                level="low"
            uniq_cust=len(set(t.customer_id for t in d_txns))
            uniq_merch=len(set(t.merchant_id for t in d_txns))
            items.append({
                "device_id": d.id,
                "fingerprint_hash": d.fingerprint_hash,
                "ip": d.ip,
                "user_agent": d.user_agent,
                "risk_score_device": float(d.risk_score) if d.risk_score is not None else None,
                "created_at": d.created_at,
                "total_transactions": len(d_txns),
                "total_volume": total_vol,
                "average_risk_score": round(float(avg),2),
                "risk_level": level,
                "unique_customers": uniq_cust,
                "unique_merchants": uniq_merch,
                "total_cases": cases_per_device.get(d.id,0),
            })
        return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}
