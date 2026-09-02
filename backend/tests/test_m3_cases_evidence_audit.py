from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Rule, AuditLog
from app.models.case import CaseStatus
from app.models.rule import RuleAction as ModelRuleAction
from app.schemas.case import CaseStatus as SchemaCaseStatus, CaseFilter
from app.schemas.evidence import EvidenceFilter
from app.services.case_service import CaseService
from app.services.audit_service import AuditService


@pytest.fixture(scope="session")
def db() -> Session:
    """Session-scoped database session for tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def db_session(db: Session) -> Session:
    """Per-test database session."""
    yield db
    db.rollback()


@pytest.fixture(autouse=True)
def clean_db(db: Session):
    db.execute(text("TRUNCATE TABLE audit_log, evidence, cases, transactions, rules, merchants, devices, customers RESTART IDENTITY CASCADE"))
    db.commit()
    yield
    db.execute(text("TRUNCATE TABLE audit_log, evidence, cases, transactions, rules, merchants, devices, customers RESTART IDENTITY CASCADE"))
    db.commit()


@pytest.fixture
def sample_rules(db_session: Session):
    rules = [
        Rule(
            name="block_high_amount",
            dsl_expression="amount > 10000",
            action=ModelRuleAction.BLOCK,
            priority=100,
            enabled=True,
        ),
        Rule(
            name="review_medium_amount",
            dsl_expression="amount > 1000",
            action=ModelRuleAction.REVIEW,
            priority=50,
            enabled=True,
        ),
    ]
    db_session.add_all(rules)
    db_session.commit()
    return rules


@pytest.fixture
def sample_transaction(db_session: Session, sample_rules):
    from app.services.transaction_service import TransactionService
    service = TransactionService(db_session)
    return service.ingest({
        "provider_event_id": "evt_case_test_001",
        "amount": Decimal("50.00"),  # ALLOW amount - no auto case creation
        "currency": "USD",
        "customer_external_id": "cust_case_001",
        "merchant_name": "Test Merchant",
        "merchant_category_code": "5411",
    })


@pytest.fixture
def sample_case(db_session: Session, sample_transaction):
    from app.services.case_service import CaseService
    service = CaseService(db_session)
    return service.create_case(
        transaction_id=sample_transaction.transaction_id,
        status=CaseStatus.OPEN,
        assignee=None,
        actor="test_actor",
    )


class TestCaseCreation:
    def test_create_case_from_transaction(self, db_session: Session, sample_transaction):
        service = CaseService(db_session)
        case = service.create_case(
            transaction_id=sample_transaction.transaction_id,
            status=CaseStatus.OPEN,
            assignee="analyst_1",
            actor="test_actor",
        )
        assert case is not None
        assert case.transaction_id == sample_transaction.transaction_id
        assert case.status == CaseStatus.OPEN
        assert case.assignee == "analyst_1"

    def test_duplicate_case_rejected(self, db_session: Session, sample_transaction):
        service = CaseService(db_session)
        service.create_case(sample_transaction.transaction_id, CaseStatus.OPEN, actor="test")
        with pytest.raises(ValueError, match="already exists"):
            service.create_case(sample_transaction.transaction_id, CaseStatus.OPEN, actor="test")

    def test_case_created_audit_log(self, db_session: Session, sample_transaction):
        service = CaseService(db_session)
        case = service.create_case(sample_transaction.transaction_id, CaseStatus.OPEN, actor="test_actor")
        audit_logs = db_session.query(AuditLog).filter_by(resource_type="case", resource_id=str(case.id)).all()
        assert len(audit_logs) == 1
        assert audit_logs[0].action == "CASE_CREATED"


class TestCaseRetrieval:
    def test_get_case(self, db_session: Session, sample_case):
        service = CaseService(db_session)
        case = service.get_case(sample_case.id)
        assert case is not None
        assert case.id == sample_case.id

    def test_get_nonexistent_case(self, db_session: Session):
        service = CaseService(db_session)
        case = service.get_case(UUID("00000000-0000-0000-0000-000000000000"))
        assert case is None

    def test_get_case_detail(self, db_session: Session, sample_case, sample_transaction):
        service = CaseService(db_session)
        detail = service.get_case_detail(sample_case.id)
        assert detail is not None
        assert detail.id == sample_case.id
        assert detail.transaction is not None
        assert detail.transaction["provider_event_id"] == sample_transaction.provider_event_id
        assert detail.evidence_count == 0


class TestCaseListing:
    def test_list_cases_empty(self, db_session: Session):
        service = CaseService(db_session)
        result = service.list_cases(CaseFilter())
        assert result.total == 0
        assert len(result.items) == 0

    def test_list_cases_with_filter(self, db_session: Session, sample_case, sample_transaction):
        from app.services.case_service import CaseService
        service = CaseService(db_session)

        # Create another case (use ALLOW amount to avoid auto-case creation)
        txn_service = None
        from app.services.transaction_service import TransactionService
        txn_service = TransactionService(db_session)
        txn2 = txn_service.ingest({
            "provider_event_id": "evt_list_002",
            "amount": Decimal("50.00"),
            "currency": "USD",
            "customer_external_id": "cust_list_002",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })
        service.create_case(txn2.transaction_id, CaseStatus.OPEN, assignee="analyst_2", actor="test")

        # Filter by assignee "analyst_2" - should find the newly created case
        result = service.list_cases(CaseFilter(assignee="analyst_2"))
        assert result.total == 1
        assert result.items[0].assignee == "analyst_2"

        # Filter by assignee None - should find sample_case (which has no assignee)
        result = service.list_cases(CaseFilter(assignee=None))
        assert result.total == 1
        assert result.items[0].assignee is None

        # Filter by status OPEN - should find both cases
        result = service.list_cases(CaseFilter(status=SchemaCaseStatus.OPEN))
        assert result.total == 2

        # Pagination
        result = service.list_cases(CaseFilter(page=1, page_size=1))
        assert len(result.items) == 1
        assert result.total_pages == 2


class TestCaseAssignment:
    def test_assign_case(self, db_session: Session, sample_case):
        service = CaseService(db_session)
        case = service.assign_case(sample_case.id, "new_analyst", actor="test_actor")
        assert case.assignee == "new_analyst"

        # Check audit log
        audit_logs = db_session.query(AuditLog).filter_by(resource_type="case", resource_id=str(sample_case.id)).all()
        assign_logs = [log for log in audit_logs if log.action == "CASE_ASSIGNED"]
        assert len(assign_logs) == 1
        assert assign_logs[0].after_json["assignee"] == "new_analyst"

    def test_reassign_case(self, db_session: Session, sample_case):
        service = CaseService(db_session)
        sample_case.assignee = "old_analyst"
        db_session.flush()

        service.assign_case(sample_case.id, "new_analyst", actor="test_actor")
        assert sample_case.assignee == "new_analyst"


class TestCaseStatusTransitions:
    def test_valid_transitions(self, db_session: Session, sample_case):
        service = CaseService(db_session)

        # OPEN -> IN_PROGRESS
        service.change_status(sample_case.id, SchemaCaseStatus.IN_PROGRESS, actor="test")
        assert sample_case.status == CaseStatus.IN_PROGRESS

        # IN_PROGRESS -> CLOSED_APPROVED
        service.change_status(sample_case.id, SchemaCaseStatus.CLOSED_APPROVED, actor="test")
        assert sample_case.status == CaseStatus.CLOSED_APPROVED

    def test_invalid_transition_rejected(self, db_session: Session, sample_case):
        service = CaseService(db_session)

        # CLOSED_APPROVED cannot transition
        service.change_status(sample_case.id, SchemaCaseStatus.CLOSED_APPROVED, actor="test")
        with pytest.raises(ValueError):
            service.change_status(sample_case.id, SchemaCaseStatus.IN_PROGRESS, actor="test")

    def test_status_change_audit_log(self, db_session: Session, sample_case):
        service = CaseService(db_session)
        service.change_status(sample_case.id, SchemaCaseStatus.IN_PROGRESS, actor="test_actor")

        audit_logs = db_session.query(AuditLog).filter_by(resource_type="case", resource_id=str(sample_case.id)).all()
        status_logs = [log for log in audit_logs if log.action == "CASE_STATUS_CHANGED"]
        assert len(status_logs) == 1
        assert status_logs[0].before_json["status"] == "open"
        assert status_logs[0].after_json["status"] == "in_progress"


class TestEvidenceManagement:
    def test_add_evidence(self, db_session: Session, sample_case):
        service = CaseService(db_session)
        evidence = service.add_evidence(
            sample_case.id,
            source_type="transaction",
            source_id="txn_123",
            payload={"key": "value"},
            actor="test_actor",
        )
        assert evidence.case_id == sample_case.id
        assert evidence.source_type == "transaction"
        assert evidence.source_id == "txn_123"
        assert evidence.payload == {"key": "value"}

    def test_evidence_isolation(self, db_session: Session, sample_transaction):
        service = CaseService(db_session)
        from app.services.transaction_service import TransactionService
        txn_service = TransactionService(db_session)
        
        # Create two cases
        case1 = service.create_case(sample_transaction.transaction_id, CaseStatus.OPEN, actor="test")
        
        from app.services.transaction_service import TransactionService
        txn2 = txn_service.ingest({
            "provider_event_id": "evt_iso_002",
            "amount": Decimal("50.00"),  # ALLOW amount - no auto case creation
            "currency": "USD",
            "customer_external_id": "cust_iso_002",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })
        case2 = service.create_case(txn2.transaction_id, CaseStatus.OPEN, actor="test")

        # Add evidence to case1
        service.add_evidence(case1.id, "transaction", "txn_1", {"data": 1}, actor="test")
        
        # List evidence for case2 should be empty
        from app.schemas.evidence import EvidenceFilter
        result = service.list_evidence(case2.id, EvidenceFilter())
        assert result.total == 0

        # List evidence for case1 should have 1
        result = service.list_evidence(case1.id, EvidenceFilter())
        assert result.total == 1

    def test_evidence_audit_log(self, db_session: Session, sample_case):
        service = CaseService(db_session)
        service.add_evidence(sample_case.id, "transaction", "txn_123", {"key": "value"}, actor="test_actor")

        audit_logs = db_session.query(AuditLog).filter_by(action="EVIDENCE_ADDED").all()
        assert len(audit_logs) == 1
        assert audit_logs[0].after_json["source_type"] == "transaction"
        assert audit_logs[0].after_json["source_id"] == "txn_123"


class TestEvidenceListing:
    def test_list_evidence_with_filter(self, db_session: Session, sample_case):
        service = CaseService(db_session)
        service.add_evidence(sample_case.id, "transaction", "txn_1", {}, actor="test")
        service.add_evidence(sample_case.id, "device", "dev_1", {}, actor="test")
        service.add_evidence(sample_case.id, "customer", "cust_1", {}, actor="test")

        result = service.list_evidence(sample_case.id, EvidenceFilter(source_type="transaction"))
        assert result.total == 1
        assert result.items[0].source_type == "transaction"

        result = service.list_evidence(sample_case.id, EvidenceFilter())
        assert result.total == 3


class TestAuditService:
    def test_log_creates_entry(self, db_session: Session):
        service = AuditService(db_session)
        entry = service.log("actor1", "TEST_ACTION", "resource", "res_1", before={"a": 1}, after={"a": 2})
        assert entry.actor == "actor1"
        assert entry.action == "TEST_ACTION"
        assert entry.prev_hash is None  # First entry

    def test_hash_chain(self, db_session: Session):
        service = AuditService(db_session)
        e1 = service.log("a1", "ACT1", "r", "1")
        e2 = service.log("a2", "ACT2", "r", "2")
        db_session.flush()

        # Verify chain
        assert e1.prev_hash is None
        assert e2.prev_hash is not None

        # Verify computed hash matches stored
        assert e2.prev_hash == service.compute_hash(e1)

    def test_verify_chain_valid(self, db_session: Session):
        service = AuditService(db_session)
        service.log("a1", "ACT1", "r", "1")
        service.log("a2", "ACT2", "r", "2")
        service.log("a3", "ACT3", "r", "3")

        is_valid, error = service.verify_chain()
        assert is_valid is True
        assert error is None

    def test_verify_chain_tampered(self, db_session: Session):
        service = AuditService(db_session)
        e1 = service.log("a1", "ACT1", "r", "1")
        _ = service.log("a2", "ACT2", "r", "2")
        db_session.flush()

        # Tamper with e1
        e1.actor = "tampered"
        db_session.flush()

        is_valid, error = service.verify_chain()
        assert is_valid is False
        assert "Hash chain broken" in error

    def test_audit_log_filtering(self, db_session: Session):
        service = AuditService(db_session)
        service.log("actor1", "ACTION_1", "res", "1")
        service.log("actor2", "ACTION_2", "res", "2")
        service.log("actor1", "ACTION_1", "res", "3")

        items, total = service.get_audit_logs(actor="actor1")
        assert total == 2
        assert all(e.actor == "actor1" for e in items)

        items, total = service.get_audit_logs(action="ACTION_2")
        assert total == 1


class TestAuditAPIFiltering:
    def test_api_filtering(self, db_session: Session, sample_case):
        from app.services.audit_service import AuditService
        service = AuditService(db_session)
        case_service = CaseService(db_session)

        # Create a fresh case to avoid audit logs from sample_case fixture
        from app.services.transaction_service import TransactionService
        txn_service = TransactionService(db_session)
        txn = txn_service.ingest({
            "provider_event_id": "evt_api_filter_001",
            "amount": Decimal("50.00"),
            "currency": "USD",
            "customer_external_id": "cust_api_filter_001",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })
        fresh_case = case_service.create_case(txn.transaction_id, CaseStatus.OPEN, actor="test_actor")

        case_service.add_evidence(fresh_case.id, "txn", "txn_1", {}, actor="analyst_1")
        case_service.change_status(fresh_case.id, SchemaCaseStatus.IN_PROGRESS, actor="analyst_2")

        # Filter by actor - only EVIDENCE_ADDED has actor="analyst_1"
        items, total = service.get_audit_logs(actor="analyst_1")
        assert total == 1
        assert items[0].actor == "analyst_1"

        # Filter by action - only EVIDENCE_ADDED
        items, total = service.get_audit_logs(action="EVIDENCE_ADDED")
        assert total == 1
        assert items[0].action == "EVIDENCE_ADDED"

        # Filter by resource_type - only EVIDENCE_ADDED has resource_type="evidence"
        items, total = service.get_audit_logs(resource_type="evidence")
        assert total == 1
        assert items[0].resource_type == "evidence"

        # Pagination - fresh_case has 3 audit logs: CASE_CREATED, EVIDENCE_ADDED, CASE_STATUS_CHANGED
        items, total = service.get_audit_logs(page=1, page_size=1)
        assert len(items) == 1
        assert total >= 3  # At least 3 audit logs


class TestCaseStatusTransitionsComplete:
    def test_all_valid_transitions(self, db_session: Session, sample_case):
        service = CaseService(db_session)

        # OPEN -> IN_PROGRESS
        service.change_status(sample_case.id, SchemaCaseStatus.IN_PROGRESS, actor="test")
        assert sample_case.status == CaseStatus.IN_PROGRESS

        # IN_PROGRESS -> OPEN (reopen)
        service.change_status(sample_case.id, SchemaCaseStatus.OPEN, actor="test")
        assert sample_case.status == CaseStatus.OPEN

        # OPEN -> ESCALATED
        service.change_status(sample_case.id, SchemaCaseStatus.ESCALATED, actor="test")
        assert sample_case.status == CaseStatus.ESCALATED

        # ESCALATED -> IN_PROGRESS
        service.change_status(sample_case.id, SchemaCaseStatus.IN_PROGRESS, actor="test")
        assert sample_case.status == CaseStatus.IN_PROGRESS

        # IN_PROGRESS -> CLOSED_DENIED
        service.change_status(sample_case.id, SchemaCaseStatus.CLOSED_DENIED, actor="test")
        assert sample_case.status == CaseStatus.CLOSED_DENIED

    def test_closed_cannot_transition(self, db_session: Session, sample_case):
        service = CaseService(db_session)
        
        # CLOSED_APPROVED is terminal - no outgoing transitions
        service.change_status(sample_case.id, SchemaCaseStatus.CLOSED_APPROVED, actor="test")
        assert sample_case.status == CaseStatus.CLOSED_APPROVED
        
        with pytest.raises(ValueError):
            service.change_status(sample_case.id, SchemaCaseStatus.IN_PROGRESS, actor="test")
        
        with pytest.raises(ValueError):
            service.change_status(sample_case.id, SchemaCaseStatus.CLOSED_DENIED, actor="test")
        
        with pytest.raises(ValueError):
            service.change_status(sample_case.id, SchemaCaseStatus.OPEN, actor="test")
        
        with pytest.raises(ValueError):
            service.change_status(sample_case.id, SchemaCaseStatus.ESCALATED, actor="test")

        # CLOSED_DENIED is also terminal - need a fresh case to test
        from app.services.transaction_service import TransactionService
        txn_service = TransactionService(db_session)
        txn = txn_service.ingest({
            "provider_event_id": "evt_closed_denied_test",
            "amount": Decimal("50.00"),
            "currency": "USD",
            "customer_external_id": "cust_closed_denied_test",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })
        case2 = CaseService(db_session).create_case(txn.transaction_id, CaseStatus.OPEN, actor="test")
        CaseService(db_session).change_status(case2.id, SchemaCaseStatus.CLOSED_DENIED, actor="test")
        assert case2.status == CaseStatus.CLOSED_DENIED
        
        with pytest.raises(ValueError):
            CaseService(db_session).change_status(case2.id, SchemaCaseStatus.IN_PROGRESS, actor="test")
        
        with pytest.raises(ValueError):
            CaseService(db_session).change_status(case2.id, SchemaCaseStatus.OPEN, actor="test")
        
        with pytest.raises(ValueError):
            CaseService(db_session).change_status(case2.id, SchemaCaseStatus.CLOSED_APPROVED, actor="test")