from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, Transaction, Evidence
from app.models.case import CaseStatus as ModelCaseStatus
from app.schemas.case import CaseUpdate, CaseResponse, CaseDetail, CaseListResponse, CaseFilter, CaseStatus as SchemaCaseStatus
from app.schemas.evidence import EvidenceResponse, EvidenceListResponse, EvidenceFilter
from app.services.audit_service import AuditService


class CaseService:
    VALID_STATUS_TRANSITIONS = {
        SchemaCaseStatus.OPEN: [SchemaCaseStatus.IN_PROGRESS, SchemaCaseStatus.CLOSED_APPROVED, SchemaCaseStatus.CLOSED_DENIED, SchemaCaseStatus.ESCALATED],
        SchemaCaseStatus.IN_PROGRESS: [SchemaCaseStatus.CLOSED_APPROVED, SchemaCaseStatus.CLOSED_DENIED, SchemaCaseStatus.ESCALATED, SchemaCaseStatus.OPEN],
        SchemaCaseStatus.ESCALATED: [SchemaCaseStatus.IN_PROGRESS, SchemaCaseStatus.CLOSED_APPROVED, SchemaCaseStatus.CLOSED_DENIED],
        SchemaCaseStatus.CLOSED_APPROVED: [],
        SchemaCaseStatus.CLOSED_DENIED: [],
    }

    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    def create_case(self, transaction_id: UUID, status: SchemaCaseStatus, assignee: Optional[str] = None, actor: str = "system") -> Case:
        txn = self.db.execute(select(Transaction).where(Transaction.id == transaction_id)).scalar_one_or_none()
        if not txn:
            raise ValueError("Transaction not found")

        existing = self.db.execute(select(Case).where(Case.transaction_id == transaction_id)).scalar_one_or_none()
        if existing:
            raise ValueError("Case already exists for this transaction")

        case = Case(
            transaction_id=transaction_id,
            status=ModelCaseStatus(status.value),
            assignee=assignee,
        )
        self.db.add(case)
        self.db.flush()

        self.audit.log(
            actor=actor,
            action="CASE_CREATED",
            resource_type="case",
            resource_id=str(case.id),
            before=None,
            after={"status": status.value, "assignee": assignee, "transaction_id": str(transaction_id)},
        )

        return case

    def get_case(self, case_id: UUID) -> Optional[Case]:
        stmt = select(Case).where(Case.id == case_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_case_detail(self, case_id: UUID) -> Optional[CaseDetail]:
        case = self.get_case(case_id)
        if not case:
            return None

        evidence_count = len(list(case.evidence))
        txn = self.db.execute(select(Transaction).where(Transaction.id == case.transaction_id)).scalar_one()

        return CaseDetail(
            id=case.id,
            transaction_id=case.transaction_id,
            status=SchemaCaseStatus(case.status.value),
            assignee=case.assignee,
            created_at=case.created_at,
            updated_at=case.updated_at,
            transaction={
                "id": str(txn.id),
                "provider_event_id": txn.provider_event_id,
                "amount": str(txn.amount),
                "currency": txn.currency,
                "status": txn.status.value,
            },
            evidence_count=evidence_count,
        )

    def list_cases(self, filters: CaseFilter) -> CaseListResponse:
        stmt = select(Case)

        if filters.status:
            stmt = stmt.where(Case.status == filters.status)
        
        # Check if assignee was explicitly set in the filter (including None)
        if "assignee" in filters.model_fields_set:
            if filters.assignee is None:
                stmt = stmt.where(Case.assignee.is_(None))
            else:
                stmt = stmt.where(Case.assignee == filters.assignee)
        
        if filters.date_from:
            stmt = stmt.where(Case.created_at >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(Case.created_at <= filters.date_to)

        stmt = stmt.order_by(Case.created_at.desc())

        total = self.db.execute(stmt).scalars().all()
        total_count = len(total)

        stmt = stmt.offset((filters.page - 1) * filters.page_size).limit(filters.page_size)
        items = self.db.execute(stmt).scalars().all()

        case_responses = [
            CaseResponse(
                id=c.id,
                transaction_id=c.transaction_id,
                status=SchemaCaseStatus(c.status.value),
                assignee=c.assignee,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in items
        ]

        return CaseListResponse(
            items=case_responses,
            total=total_count,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=(total_count + filters.page_size - 1) // filters.page_size,
        )

    def update_case(self, case_id: UUID, update: CaseUpdate, actor: str) -> Case:
        case = self.get_case(case_id)
        if not case:
            raise ValueError("Case not found")

        before = {"status": case.status.value, "assignee": case.assignee}

        if update.status is not None:
            if update.status not in self.VALID_STATUS_TRANSITIONS.get(SchemaCaseStatus(case.status.value), []):
                raise ValueError(f"Invalid status transition from {case.status.value} to {update.status.value}")
            case.status = ModelCaseStatus(update.status.value)

        if update.assignee is not None:
            case.assignee = update.assignee

        case.updated_at = datetime.utcnow()
        self.db.flush()

        after = {"status": case.status.value, "assignee": case.assignee}

        action = "CASE_STATUS_CHANGED" if update.status is not None else "CASE_ASSIGNED"
        self.audit.log(
            actor=actor,
            action=action,
            resource_type="case",
            resource_id=str(case_id),
            before=before,
            after=after,
        )

        return case

    def assign_case(self, case_id: UUID, assignee: str, actor: str) -> Case:
        return self.update_case(case_id, CaseUpdate(assignee=assignee), actor)

    def change_status(self, case_id: UUID, status: SchemaCaseStatus, actor: str) -> Case:
        return self.update_case(case_id, CaseUpdate(status=status), actor)

    def add_evidence(
        self,
        case_id: UUID,
        source_type: str,
        source_id: str,
        payload: dict,
        actor: str,
    ) -> Evidence:
        case = self.get_case(case_id)
        if not case:
            raise ValueError("Case not found")

        evidence = Evidence(
            case_id=case_id,
            source_type=source_type,
            source_id=source_id,
            payload=payload,
        )
        self.db.add(evidence)
        self.db.flush()

        self.audit.log(
            actor=actor,
            action="EVIDENCE_ADDED",
            resource_type="evidence",
            resource_id=str(evidence.id),
            before=None,
            after={"case_id": str(case_id), "source_type": source_type, "source_id": source_id},
        )

        return evidence

    def get_evidence(self, evidence_id: UUID) -> Optional[Evidence]:
        stmt = select(Evidence).where(Evidence.id == evidence_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_evidence(self, case_id: UUID, filters: EvidenceFilter) -> EvidenceListResponse:
        stmt = select(Evidence).where(Evidence.case_id == case_id)

        if filters.source_type:
            stmt = stmt.where(Evidence.source_type == filters.source_type)

        stmt = stmt.order_by(Evidence.retrieved_at.desc())

        total = self.db.execute(stmt).scalars().all()
        total_count = len(total)

        stmt = stmt.offset((filters.page - 1) * filters.page_size).limit(filters.page_size)
        items = self.db.execute(stmt).scalars().all()

        evidence_responses = [
            EvidenceResponse(
                id=e.id,
                case_id=e.case_id,
                source_type=e.source_type,
                source_id=e.source_id,
                payload=e.payload,
                retrieved_at=e.retrieved_at,
            )
            for e in items
        ]

        return EvidenceListResponse(
            items=evidence_responses,
            total=total_count,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=(total_count + filters.page_size - 1) // filters.page_size,
        )