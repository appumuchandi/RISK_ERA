from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, Union
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Case,
    Customer,
    Device,
    Merchant,
    Transaction,
    Rule,
)
from app.models.transaction import TransactionStatus
from app.models.case import CaseStatus
from app.schemas.transaction import (
    TransactionAction,
    TransactionIngestRequest,
    TransactionIngestResponse,
    TriggeredRule,
)
from app.services.rule_engine import RuleEngine, Rule as RuleEngineRule


class TransactionService:
    def __init__(self, db: Session):
        self.db = db

    def ingest(self, request: Union[TransactionIngestRequest, dict]) -> TransactionIngestResponse:
        if isinstance(request, dict):
            request = TransactionIngestRequest(**request)
        existing_txn = self._get_by_provider_event_id(request.provider_event_id)
        if existing_txn:
            return self._build_response(existing_txn, is_new_transaction=False)

        customer = self._resolve_customer(request.customer_external_id)
        device = self._resolve_device(
            request.device_fingerprint_hash,
            request.device_ip,
            request.device_user_agent,
        )
        merchant = self._resolve_merchant(
            request.merchant_name,
            request.merchant_category_code,
        )

        rules = self._get_enabled_rules()
        rule_engine = RuleEngine(rules)

        transaction_data = {
            "amount": request.amount,
            "currency": request.currency,
            "customer_risk_tier": customer.risk_tier,
            "customer_kyc_status": customer.kyc_status,
            "device_risk_score": device.risk_score if device else None,
            "merchant_category_code": merchant.category_code,
            "merchant_risk_level": merchant.risk_level,
        }

        engine_result = rule_engine.evaluate(transaction_data)
        final_action = engine_result.final_action
        triggered_rules = engine_result.triggered_rules
        risk_score = engine_result.risk_score

        status_map = {
            TransactionAction.ALLOW: TransactionStatus.AUTHORIZED,
            TransactionAction.REVIEW: TransactionStatus.FLAGGED,
            TransactionAction.BLOCK: TransactionStatus.FAILED,
        }
        txn_status = status_map[final_action]

        txn = Transaction(
            provider_event_id=request.provider_event_id,
            amount=request.amount,
            currency=request.currency,
            status=txn_status,
            customer_id=customer.id,
            device_id=device.id if device else None,
            merchant_id=merchant.id,
            raw_payload=request.raw_payload,
        )
        self.db.add(txn)

        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            existing_txn = self._get_by_provider_event_id(request.provider_event_id)
            if existing_txn:
                return self._build_response(existing_txn, is_new_transaction=False)
            raise

        case_id = None
        if final_action in (TransactionAction.REVIEW, TransactionAction.BLOCK):
            case = self._create_case(txn.id, final_action)
            case_id = case.id

        self.db.commit()
        self.db.refresh(txn)

        return TransactionIngestResponse(
            transaction_id=txn.id,
            provider_event_id=txn.provider_event_id,
            action=final_action,
            risk_score=risk_score,
            triggered_rules=[
                TriggeredRule(
                    rule_id=r.rule_id,
                    rule_name=r.rule_name,
                    action=r.action,
                    priority=r.priority,
                    dsl_expression=r.dsl_expression,
                )
                for r in triggered_rules
            ],
            case_id=case_id,
            is_new_transaction=True,
        )

    def _get_by_provider_event_id(self, provider_event_id: str) -> Optional[Transaction]:
        stmt = select(Transaction).where(Transaction.provider_event_id == provider_event_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def _resolve_customer(self, external_id: str) -> Customer:
        stmt = select(Customer).where(Customer.external_id == external_id)
        customer = self.db.execute(stmt).scalar_one_or_none()
        if customer:
            return customer

        customer = Customer(
            external_id=external_id,
            risk_tier="standard",
            kyc_status="pending",
        )
        self.db.add(customer)
        self.db.flush()
        return customer

    def _resolve_device(
        self, fingerprint_hash: Optional[str], ip: Optional[str], user_agent: Optional[str]
    ) -> Optional[Device]:
        if not fingerprint_hash:
            return None

        stmt = select(Device).where(Device.fingerprint_hash == fingerprint_hash)
        device = self.db.execute(stmt).scalar_one_or_none()
        if device:
            if ip and not device.ip:
                device.ip = ip
            if user_agent and not device.user_agent:
                device.user_agent = user_agent
            self.db.flush()
            return device

        device = Device(
            fingerprint_hash=fingerprint_hash,
            ip=ip,
            user_agent=user_agent,
            risk_score=None,
        )
        self.db.add(device)
        self.db.flush()
        return device

    def _resolve_merchant(self, name: str, category_code: str) -> Merchant:
        stmt = select(Merchant).where(
            Merchant.name == name,
            Merchant.category_code == category_code,
        )
        merchant = self.db.execute(stmt).scalar_one_or_none()
        if merchant:
            return merchant

        merchant = Merchant(
            name=name,
            category_code=category_code,
            risk_level="standard",
        )
        self.db.add(merchant)
        self.db.flush()
        return merchant

    def _get_enabled_rules(self) -> list[RuleEngineRule]:
        stmt = select(Rule).where(Rule.enabled).order_by(Rule.priority)
        rules = self.db.execute(stmt).scalars().all()
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
            for r in rules
        ]

    def _create_case(self, transaction_id: UUID, action: TransactionAction) -> Case:
        status_map = {
            TransactionAction.REVIEW: CaseStatus.IN_PROGRESS,
            TransactionAction.BLOCK: CaseStatus.OPEN,
        }
        case = Case(
            transaction_id=transaction_id,
            status=status_map[action],
        )
        self.db.add(case)
        self.db.flush()
        return case

    def _build_response(self, txn: Transaction, is_new_transaction: bool) -> TransactionIngestResponse:
        case_id = None
        if txn.case:
            case_id = txn.case.id

        return TransactionIngestResponse(
            transaction_id=txn.id,
            provider_event_id=txn.provider_event_id,
            action=self._map_status_to_action(txn.status),
            risk_score=None,
            triggered_rules=[],
            case_id=case_id,
            is_new_transaction=is_new_transaction,
        )

    def _map_status_to_action(self, status: TransactionStatus) -> TransactionAction:
        mapping = {
            TransactionStatus.AUTHORIZED: TransactionAction.ALLOW,
            TransactionStatus.FLAGGED: TransactionAction.REVIEW,
            TransactionStatus.FAILED: TransactionAction.BLOCK,
        }
        return mapping.get(status, TransactionAction.ALLOW)

    # --- Transaction intelligence ---

    # Allow-listed sorting fields — never interpolate user input directly into SQL
    SORT_FIELD_MAP = {
        "created_at": "created_at",
        "amount": "amount",
        "risk_score": "risk_score",  # computed, sorted in Python
        "provider_event_id": "provider_event_id",
        "status": "status",
    }

    @staticmethod
    def _risk_level_from_score(score: float) -> str:
        if score >= 85:
            return "critical"
        if score >= 60:
            return "high"
        if score >= 25:
            return "medium"
        return "low"

    def _compute_risk_for_transaction(self, txn: Transaction, rule_engine: RuleEngine) -> tuple[float, str, TransactionAction, list]:
        """Compute deterministic risk for a transaction using the shared RuleEngine."""
        # Build transaction_data from ORM relationships (avoid N+1 via selectin)
        # Customer/Merchant/Device are already selectin-loaded
        customer = txn.customer if hasattr(txn, "customer") and txn.customer else None
        merchant = txn.merchant if hasattr(txn, "merchant") and txn.merchant else None
        device = txn.device if hasattr(txn, "device") and txn.device else None

        data = {
            "amount": txn.amount,
            "currency": txn.currency,
            "customer_risk_tier": customer.risk_tier if customer else "standard",
            "customer_kyc_status": customer.kyc_status if customer else "pending",
            "device_risk_score": float(device.risk_score) if device and device.risk_score is not None else None,
            "merchant_category_code": merchant.category_code if merchant else "",
            "merchant_risk_level": merchant.risk_level if merchant else "standard",
        }
        result = rule_engine.evaluate(data)
        risk_score = result.risk_score if result.risk_score is not None else 0.0
        risk_level = self._risk_level_from_score(risk_score)
        triggered = [
            TriggeredRule(
                rule_id=r.rule_id,
                rule_name=r.rule_name,
                action=r.action,
                priority=r.priority,
                dsl_expression=r.dsl_expression,
            )
            for r in result.triggered_rules
        ]
        return risk_score, risk_level, result.final_action, triggered

    def list_transactions(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        # Filters
        risk: Optional[str] = None,
        min_amount: Optional[Decimal] = None,
        max_amount: Optional[Decimal] = None,
        customer_id: Optional[UUID] = None,
        merchant_id: Optional[UUID] = None,
        device_id: Optional[UUID] = None,
        status: Optional[str] = None,
        provider_event_id: Optional[str] = None,
        search: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> dict:
        """List transactions with intelligence (risk, triggered rules) and filters.

        Returns dict with items, total, page, page_size, total_pages.
        Risk filtering/sorting is computed via RuleEngine deterministically.
        """
        # Validate sort
        if sort_by not in self.SORT_FIELD_MAP:
            raise ValueError(f"Invalid sort_by: {sort_by}. Allowed: {list(self.SORT_FIELD_MAP.keys())}")
        if sort_order not in ("asc", "desc"):
            raise ValueError(f"Invalid sort_order: {sort_order}. Must be asc or desc")

        if risk is not None and risk not in ("low", "medium", "high", "critical"):
            raise ValueError(f"Invalid risk: {risk}. Allowed: low, medium, high, critical")

        # Validate amount range
        if min_amount is not None and max_amount is not None and min_amount > max_amount:
            raise ValueError("min_amount cannot be greater than max_amount")

        # Validate dates
        if from_date and to_date and from_date > to_date:
            raise ValueError("from_date cannot be after to_date")

        # Build base query with DB-filterable fields
        stmt = select(Transaction)

        if status:
            # Validate status against enum
            valid_statuses = {e.value for e in TransactionStatus}
            if status not in valid_statuses:
                raise ValueError(f"Invalid status: {status}. Allowed: {sorted(valid_statuses)}")
            stmt = stmt.where(Transaction.status == status)

        if min_amount is not None:
            stmt = stmt.where(Transaction.amount >= min_amount)
        if max_amount is not None:
            stmt = stmt.where(Transaction.amount <= max_amount)

        if customer_id:
            stmt = stmt.where(Transaction.customer_id == customer_id)
        if merchant_id:
            stmt = stmt.where(Transaction.merchant_id == merchant_id)
        if device_id:
            stmt = stmt.where(Transaction.device_id == device_id)

        if provider_event_id:
            stmt = stmt.where(Transaction.provider_event_id == provider_event_id)

        if search:
            # Search over provider_event_id (ILIKE) — indexed via btree, safe via param binding
            stmt = stmt.where(Transaction.provider_event_id.ilike(f"%{search}%"))

        if from_date:
            stmt = stmt.where(Transaction.created_at >= from_date)
        if to_date:
            stmt = stmt.where(Transaction.created_at <= to_date)

        # Deterministic ordering for DB fields — add secondary id order
        # For risk_score we will sort in Python, so default DB order is created_at desc + id
        if sort_by in ("created_at", "amount", "provider_event_id", "status"):
            col = getattr(Transaction, sort_by)
            order_col = col.desc() if sort_order == "desc" else col.asc()
            stmt = stmt.order_by(order_col, Transaction.id.desc())
        else:
            # risk_score sorting handled post-computation; still add deterministic DB order before compute
            stmt = stmt.order_by(Transaction.created_at.desc(), Transaction.id.desc())

        # Execute — fetch all filtered rows (231 rows baseline, safe to fetch all then paginate after risk compute)
        # For larger datasets, this would need keyset pagination + materialized risk_score column
        all_txns = self.db.execute(stmt).scalars().all()

        # Compute risk intelligence for each transaction exactly once
        rules = self._get_enabled_rules()
        engine = RuleEngine(rules)

        enriched: list[dict] = []
        for txn in all_txns:
            risk_score, risk_level, decision, triggered = self._compute_risk_for_transaction(txn, engine)
            # Apply risk filter post-computation (cannot be done in SQL without persisted column)
            if risk is not None and risk_level != risk:
                continue
            # Build enriched dict for sorting/pagination
            enriched.append({
                "txn": txn,
                "risk_score": risk_score,
                "risk_level": risk_level,
                "decision": decision,
                "triggered_rules": triggered,
            })

        # Sorting for risk_score (and any re-sort for consistency)
        reverse = sort_order == "desc"
        if sort_by == "risk_score":
            enriched.sort(key=lambda x: (x["risk_score"], x["txn"].created_at), reverse=reverse)
            # Ensure deterministic secondary id order
            # Python sort is stable, so we already have deterministic order from DB id
        elif sort_by == "amount":
            # Already ordered by DB, but risk filter may have changed order — re-sort in Python to guarantee correctness after filtering
            enriched.sort(key=lambda x: (float(x["txn"].amount), x["txn"].id.int if hasattr(x["txn"].id, "int") else str(x["txn"].id)), reverse=reverse)
        elif sort_by == "created_at":
            enriched.sort(key=lambda x: (x["txn"].created_at, str(x["txn"].id)), reverse=reverse)
        elif sort_by in ("provider_event_id", "status"):
            key_field = sort_by
            enriched.sort(key=lambda x: (getattr(x["txn"], key_field), str(x["txn"].id)), reverse=reverse)

        total = len(enriched)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        start = (page - 1) * page_size
        end = start + page_size
        page_slice = enriched[start:end]

        from app.schemas.transaction import TransactionListItem

        items: list[TransactionListItem] = []
        for entry in page_slice:
            txn = entry["txn"]
            # Denormalized fields from relationships (selectin-loaded, no N+1)
            cust_ext = txn.customer.external_id if txn.customer else None
            merch_name = txn.merchant.name if txn.merchant else None
            merch_cat = txn.merchant.category_code if txn.merchant else None
            has_case = txn.case is not None
            case_id = txn.case.id if has_case else None
            case_status = txn.case.status.value if has_case and txn.case.status else None

            items.append(
                TransactionListItem(
                    id=txn.id,
                    provider_event_id=txn.provider_event_id,
                    amount=txn.amount,
                    currency=txn.currency,
                    status=txn.status.value if hasattr(txn.status, "value") else str(txn.status),
                    customer_id=txn.customer_id,
                    device_id=txn.device_id,
                    merchant_id=txn.merchant_id,
                    raw_payload=txn.raw_payload or {},
                    created_at=txn.created_at,
                    risk_score=round(float(entry["risk_score"]), 2),
                    risk_level=entry["risk_level"],
                    decision=entry["decision"],
                    triggered_rules=entry["triggered_rules"],
                    has_case=has_case,
                    case_id=case_id,
                    case_status=case_status,
                    customer_external_id=cust_ext,
                    merchant_name=merch_name,
                    merchant_category_code=merch_cat,
                )
            )

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }