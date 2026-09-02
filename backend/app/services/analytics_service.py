from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Customer, Merchant, Device, Transaction, Case, Rule
from app.models.case import CaseStatus
from app.schemas.transaction import TransactionAction
from app.services.rule_engine import RuleEngine, Rule as RuleEngineRule


def _get_enabled_rules(db: Session) -> list[RuleEngineRule]:
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


class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db
        self._engine: RuleEngine | None = None

    def _get_engine(self) -> RuleEngine:
        if self._engine is None:
            self._engine = RuleEngine(_get_enabled_rules(self.db))
        return self._engine

    def get_dashboard(self, days: int = 30) -> dict:
        if days < 1 or days > 365:
            raise ValueError("days must be between 1 and 365")
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)

        engine = self._get_engine()

        # Fetch transactions in range + cases in range (batched, no N+1)
        # Transactions: created_at >= start
        txns = self.db.execute(
            select(Transaction)
            .where(Transaction.created_at >= start)
            .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))
            .order_by(Transaction.created_at.asc())
        ).scalars().all()

        # If no transactions in range but we still want to show overall? Fallback to all transactions for overview? No, keep range.
        # For overview we use filtered set

        # Cases in range
        cases = self.db.execute(
            select(Case)
            .where(Case.created_at >= start)
        ).scalars().all()

        # Also need total cases overall? But spec says dashboard should reflect filtered range; we use filtered.
        # For case_trend we need cases by date

        # Compute risk/decision per transaction
        risk_levels: List[str] = []
        decisions: List[str] = []
        rule_counter: Counter = Counter()
        rule_action_map: Dict[str, str] = {}
        # For concentration
        by_customer: Dict[str, List[Transaction]] = defaultdict(list)
        by_merchant: Dict[str, List[Transaction]] = defaultdict(list)
        by_device: Dict[str, List[Transaction]] = defaultdict(list)

        # For transaction_trend grouping
        tx_by_date: Dict[str, List[Transaction]] = defaultdict(list)
        # For case_trend
        case_by_date: Dict[str, List[Case]] = defaultdict(list)
        for c in cases:
            d = c.created_at.date().isoformat() if c.created_at else now.date().isoformat()
            case_by_date[d].append(c)

        total_value = Decimal("0")
        high_risk = 0
        critical = 0
        blocked = 0
        review = 0
        allowed = 0

        # Precompute per txn risk
        txn_risks: List[Dict] = []  # for later
        for txn in txns:
            # Build data for RuleEngine
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
            decision = result.final_action.value  # allow/review/block

            risk_levels.append(level)
            decisions.append(decision)
            for tr in result.triggered_rules:
                rule_counter[tr.rule_name] += 1
                rule_action_map[tr.rule_name] = tr.action.value

            if level == "high":
                high_risk += 1
            if level == "critical":
                critical += 1
            if decision == "block":
                blocked += 1
            elif decision == "review":
                review += 1
            else:
                allowed += 1

            total_value += txn.amount
            txn_risks.append({"txn": txn, "score": score, "level": level, "decision": decision})

            # group for trends
            d = txn.created_at.date().isoformat() if txn.created_at else now.date().isoformat()
            tx_by_date[d].append(txn)

            # concentration
            by_customer[str(txn.customer_id)].append(txn)
            by_merchant[str(txn.merchant_id)].append(txn)
            if txn.device_id:
                by_device[str(txn.device_id)].append(txn)

        total_txns = len(txns)
        total_cases = len(cases)
        open_cases = sum(1 for c in cases if c.status == CaseStatus.OPEN)
        in_progress = sum(1 for c in cases if c.status == CaseStatus.IN_PROGRESS)
        escalated = sum(1 for c in cases if c.status == CaseStatus.ESCALATED)
        avg_value = (total_value / total_txns) if total_txns else Decimal("0")

        # Risk distribution
        risk_counter = Counter(risk_levels)
        risk_distribution = []
        for lvl in ["low", "medium", "high", "critical"]:
            cnt = risk_counter.get(lvl, 0)
            pct = round((cnt / total_txns * 100) if total_txns else 0, 2)
            risk_distribution.append({"risk_level": lvl, "count": cnt, "percentage": pct})

        # Decision distribution
        dec_counter = Counter(decisions)
        decision_distribution = []
        for dec in ["allow", "review", "block"]:
            cnt = dec_counter.get(dec, 0)
            pct = round((cnt / total_txns * 100) if total_txns else 0, 2)
            decision_distribution.append({"decision": dec, "count": cnt, "percentage": pct})

        # Transaction trend - generate all dates in range
        date_list = []
        cur = start.date()
        end = now.date()
        while cur <= end:
            date_list.append(cur.isoformat())
            cur += timedelta(days=1)
        if len(date_list) > days:
            date_list = date_list[-days:]
        # Ensure exactly days entries (if missing early days, pad)
        # If date_list shorter than days (e.g., no data early), keep as is; frontend handles
        txn_id_to_risk = {str(tr["txn"].id): tr for tr in txn_risks}
        transaction_trend = []
        for d in date_list:
            day_txns = tx_by_date.get(d, [])
            cnt = len(day_txns)
            val = sum((t.amount for t in day_txns), Decimal("0"))
            high_cnt = 0
            blk_cnt = 0
            for t in day_txns:
                tr = txn_id_to_risk.get(str(t.id))
                if tr:
                    if tr["level"] in ("high", "critical"):
                        high_cnt += 1
                    if tr["decision"] == "block":
                        blk_cnt += 1
            transaction_trend.append({
                "date": d,
                "transaction_count": cnt,
                "transaction_value": val,
                "high_risk_count": high_cnt,
                "blocked_count": blk_cnt,
            })

        # Case trend - similar dates
        case_trend = []
        for d in date_list:
            day_cases = case_by_date.get(d, [])
            opened = len(day_cases)
            in_prog = sum(1 for c in day_cases if c.status == CaseStatus.IN_PROGRESS)
            resolved = sum(1 for c in day_cases if c.status in (CaseStatus.CLOSED_APPROVED, CaseStatus.CLOSED_DENIED))
            confirmed = sum(1 for c in day_cases if c.status == CaseStatus.CLOSED_DENIED)
            case_trend.append({
                "date": d,
                "opened": opened,
                "in_progress": in_prog,
                "resolved": resolved,
                "confirmed_fraud": confirmed,
            })

        # Top triggered rules
        top_rules = []
        for rule, cnt in rule_counter.most_common(10):
            top_rules.append({"rule": rule, "count": cnt, "action": rule_action_map.get(rule, "review")})

        # Risk concentration
        # Need labels for customers/merchants/devices
        # We have by_customer etc, need to fetch entity details for top
        # To avoid N+1, fetch all distinct ids batch
        cust_ids = list(by_customer.keys())
        merch_ids = list(by_merchant.keys())
        dev_ids = list(by_device.keys())

        # Fetch details batch
        cust_map: Dict[str, Customer] = {}
        if cust_ids:
            # Convert to UUID
            from uuid import UUID
            cust_uuids = [UUID(cid) for cid in cust_ids]
            rows = self.db.execute(select(Customer).where(Customer.id.in_(cust_uuids))).scalars().all()
            cust_map = {str(r.id): r for r in rows}
        merch_map: Dict[str, Merchant] = {}
        if merch_ids:
            from uuid import UUID
            merch_uuids = [UUID(mid) for mid in merch_ids]
            rows = self.db.execute(select(Merchant).where(Merchant.id.in_(merch_uuids))).scalars().all()
            merch_map = {str(r.id): r for r in rows}
        dev_map: Dict[str, Device] = {}
        if dev_ids:
            from uuid import UUID
            dev_uuids = [UUID(did) for did in dev_ids]
            rows = self.db.execute(select(Device).where(Device.id.in_(dev_uuids))).scalars().all()
            dev_map = {str(r.id): r for r in rows}

        def build_concentration(by_dict, type_name, id_map, label_fn):
            items = []
            for eid, tx_list in by_dict.items():
                cnt = len(tx_list)
                high_cnt = 0
                blk_cnt = 0
                total_val = Decimal("0")
                scores = []
                for t in tx_list:
                    tr = txn_id_to_risk.get(str(t.id))
                    if tr:
                        scores.append(tr["score"])
                        if tr["level"] in ("high", "critical"):
                            high_cnt += 1
                        if tr["decision"] == "block":
                            blk_cnt += 1
                    total_val += t.amount
                avg_score = sum(scores) / len(scores) if scores else 0.0
                lvl = _risk_level_from_score(avg_score)
                entity = id_map.get(eid)
                label = label_fn(entity, eid) if entity else eid[:8]
                items.append({
                    "id": eid,
                    "label": label,
                    "type": type_name,
                    "transaction_count": cnt,
                    "high_risk_count": high_cnt,
                    "blocked_count": blk_cnt,
                    "total_value": total_val,
                    "average_risk_score": round(avg_score, 2),
                    "risk_level": lvl,
                })
            # sort by high_risk desc, blocked desc, total_value desc
            items.sort(key=lambda x: (x["high_risk_count"], x["blocked_count"], float(x["total_value"])), reverse=True)
            return items[:5]

        customers_conc = build_concentration(by_customer, "customer", cust_map, lambda e, eid: e.external_id if e else eid)
        merchants_conc = build_concentration(by_merchant, "merchant", merch_map, lambda e, eid: e.name if e else eid)
        devices_conc = build_concentration(by_device, "device", dev_map, lambda e, eid: e.fingerprint_hash[:12] + "…" if e and e.fingerprint_hash else eid[:8])

        return {
            "overview": {
                "total_transactions": total_txns,
                "total_cases": total_cases,
                "open_cases": open_cases,
                "in_progress_cases": in_progress,
                "escalated_cases": escalated,
                "high_risk_transactions": high_risk,
                "critical_risk_transactions": critical,
                "blocked_transactions": blocked,
                "review_transactions": review,
                "allowed_transactions": allowed,
                "total_transaction_value": total_value,
                "average_transaction_value": avg_value,
            },
            "risk_distribution": risk_distribution,
            "decision_distribution": decision_distribution,
            "transaction_trend": transaction_trend,
            "case_trend": case_trend,
            "top_triggered_rules": top_rules,
            "risk_concentration": {
                "customers": customers_conc,
                "merchants": merchants_conc,
                "devices": devices_conc,
            },
            "generated_at": now,
            "days": days,
        }
