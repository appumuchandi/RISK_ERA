from __future__ import annotations

import pytest
from uuid import uuid4
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Evidence, Rule
from app.models.case import CaseStatus as SchemaCaseStatus
from app.models.rule import RuleAction as ModelRuleAction
from app.services.evidence_grounding import EvidenceGroundingValidator
from app.schemas.investigation import Finding


@pytest.fixture(scope="session")
def db() -> Session:
    """Session-scoped database session for tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_db(db: Session):
    """Clean all tables before each test to ensure isolation."""
    db.execute(text("TRUNCATE TABLE evidence, cases, transactions, rules, merchants, devices, customers, audit_log, investigations RESTART IDENTITY CASCADE"))
    db.commit()
    yield
    db.execute(text("TRUNCATE TABLE evidence, cases, transactions, rules, merchants, devices, customers, audit_log, investigations RESTART IDENTITY CASCADE"))
    db.commit()


@pytest.fixture
def db_session(db: Session) -> Session:
    """Per-test database session."""
    yield db
    db.rollback()


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
        status=SchemaCaseStatus.OPEN,
        assignee=None,
        actor="test_actor",
    )


class TestEvidenceGroundingValidator:
    def test_valid_findings_pass(self, db_session: Session, sample_case):
        validator = EvidenceGroundingValidator(db_session)
        
        # Create evidence for the sample_case
        ev1 = Evidence(id=uuid4(), case_id=sample_case.id, source_type="transaction", source_id="txn_1", payload={})
        ev2 = Evidence(id=uuid4(), case_id=sample_case.id, source_type="device", source_id="dev_1", payload={})
        db_session.add_all([ev1, ev2])
        db_session.commit()
        
        findings = [
            Finding(finding_id="f1", description="test", evidence_ids=[str(ev1.id)], confidence=1.0, source="tool"),
            Finding(finding_id="f2", description="test2", evidence_ids=[str(ev2.id)], confidence=1.0, source="tool"),
        ]
        
        is_valid, errors = validator.validate_findings(findings)
        assert is_valid is True
        assert errors == []

    def test_invalid_evidence_ids_fail(self, db_session: Session, sample_case):
        validator = EvidenceGroundingValidator(db_session)
        
        # Try to validate finding with non-existent evidence ID
        findings = [
            Finding(finding_id="f1", description="test", evidence_ids=["00000000-0000-0000-0000-000000000000"], confidence=1.0, source="tool"),
        ]
        
        is_valid, errors = validator.validate_findings(findings)
        assert is_valid is False
        assert len(errors) == 1
        assert "non-existent evidence ID" in errors[0]

    def test_empty_findings_pass(self, db_session: Session):
        validator = EvidenceGroundingValidator(db_session)
        findings = []
        is_valid, errors = validator.validate_findings(findings)
        assert is_valid is True
        assert errors == []

    def test_mixed_valid_invalid_evidence_ids(self, db_session: Session, sample_case):
        validator = EvidenceGroundingValidator(db_session)
        
        # Create one valid evidence
        ev1 = Evidence(id=uuid4(), case_id=sample_case.id, source_type="transaction", source_id="txn_1", payload={})
        db_session.add(ev1)
        db_session.commit()
        
        # Create finding with both valid and invalid evidence IDs
        findings = [
            Finding(finding_id="f1", description="test", evidence_ids=[str(ev1.id)], confidence=1.0, source="tool"),
            Finding(finding_id="f2", description="test2", evidence_ids=["00000000-0000-0000-0000-000000000000"], confidence=1.0, source="tool"),
        ]
        
        is_valid, errors = validator.validate_findings(findings)
        assert is_valid is False
        assert len(errors) == 1
        assert "non-existent evidence ID" in errors[0]