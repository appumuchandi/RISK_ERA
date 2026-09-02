from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Customer, Device, Merchant, Rule, Case
from app.models.rule import RuleAction as ModelRuleAction
from app.models.case import CaseStatus
from app.schemas.transaction import TransactionAction
from app.services.transaction_service import TransactionService


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
    db.execute(text("TRUNCATE TABLE cases, transactions, rules, merchants, devices, customers, audit_log RESTART IDENTITY CASCADE"))
    db.commit()
    yield
    db.execute(text("TRUNCATE TABLE cases, transactions, rules, merchants, devices, customers, audit_log RESTART IDENTITY CASCADE"))
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
        Rule(
            name="review_high_risk_customer",
            dsl_expression="customer_risk_tier == 'high'",
            action=ModelRuleAction.REVIEW,
            priority=75,
            enabled=True,
        ),
        Rule(
            name="block_gambling",
            dsl_expression="merchant_category_code == '7995'",
            action=ModelRuleAction.BLOCK,
            priority=200,
            enabled=True,
        ),
        Rule(
            name="allow_small",
            dsl_expression="amount < 100",
            action=ModelRuleAction.ALLOW,
            priority=10,
            enabled=True,
        ),
    ]
    db_session.add_all(rules)
    db_session.commit()
    return rules


class TestIngestNewTransaction:
    def test_new_transaction_allow(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_001",
            "amount": Decimal("50.00"),
            "currency": "USD",
            "customer_external_id": "cust_001",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.is_new_transaction is True
        assert response.action == TransactionAction.ALLOW
        assert response.case_id is None
        assert len(response.triggered_rules) == 1
        assert response.triggered_rules[0].rule_name == "allow_small"

    def test_new_transaction_review(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_002",
            "amount": Decimal("5000.00"),
            "currency": "USD",
            "customer_external_id": "cust_002",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.is_new_transaction is True
        assert response.action == TransactionAction.REVIEW
        assert response.case_id is not None
        assert len(response.triggered_rules) >= 1
        rule_names = {r.rule_name for r in response.triggered_rules}
        assert "review_medium_amount" in rule_names

    def test_new_transaction_block(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_003",
            "amount": Decimal("15000.00"),
            "currency": "USD",
            "customer_external_id": "cust_003",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.is_new_transaction is True
        assert response.action == TransactionAction.BLOCK
        assert response.case_id is not None
        assert len(response.triggered_rules) >= 1
        rule_names = {r.rule_name for r in response.triggered_rules}
        assert "block_high_amount" in rule_names


class TestIngestDuplicateTransaction:
    def test_duplicate_returns_existing(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        first = service.ingest({
            "provider_event_id": "evt_dup_001",
            "amount": Decimal("5000.00"),
            "currency": "USD",
            "customer_external_id": "cust_dup_001",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        second = service.ingest({
            "provider_event_id": "evt_dup_001",
            "amount": Decimal("5000.00"),
            "currency": "USD",
            "customer_external_id": "cust_dup_001",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert first.is_new_transaction is True
        assert second.is_new_transaction is False
        assert first.transaction_id == second.transaction_id
        assert first.action == second.action
        assert first.case_id == second.case_id

    def test_duplicate_different_amount_ignored(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        service.ingest({
            "provider_event_id": "evt_dup_002",
            "amount": Decimal("100.00"),
            "currency": "USD",
            "customer_external_id": "cust_dup_002",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        response = service.ingest({
            "provider_event_id": "evt_dup_002",
            "amount": Decimal("999999.00"),
            "currency": "EUR",
            "customer_external_id": "different_customer",
            "merchant_name": "Different Merchant",
            "merchant_category_code": "5411",
        })

        assert response.is_new_transaction is False
        assert response.action == TransactionAction.ALLOW


class TestIngestConcurrentDuplicates:
    def test_concurrent_duplicate_handling(self, db_session: Session, sample_rules):
        import threading

        results = []
        barrier = threading.Barrier(5)

        def ingest(thread_id):
            barrier.wait()
            from app.core.database import SessionLocal
            local_session = SessionLocal()
            try:
                service = TransactionService(local_session)
                result = service.ingest({
                    "provider_event_id": "evt_concurrent_001",
                    "amount": Decimal("5000.00"),
                    "currency": "USD",
                    "customer_external_id": f"cust_concurrent_{thread_id:03d}",
                    "merchant_name": "Test Merchant",
                    "merchant_category_code": "5411",
                })
                results.append(result)
            finally:
                local_session.close()

        threads = [threading.Thread(target=ingest, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 5
        transaction_ids = {r.transaction_id for r in results}
        assert len(transaction_ids) == 1
        new_counts = sum(1 for r in results if r.is_new_transaction)
        assert new_counts == 1


class TestIngestCustomerEnrichment:
    def test_missing_customer_created(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_cust_001",
            "amount": Decimal("500.00"),
            "currency": "USD",
            "customer_external_id": "new_customer_001",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.is_new_transaction is True
        customer = db_session.query(Customer).filter_by(external_id="new_customer_001").first()
        assert customer is not None
        assert customer.risk_tier == "standard"
        assert customer.kyc_status == "pending"

    def test_existing_customer_reused(self, db_session: Session, sample_rules):
        customer = Customer(external_id="existing_cust", risk_tier="high", kyc_status="verified")
        db_session.add(customer)
        db_session.commit()

        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_cust_002",
            "amount": Decimal("500.00"),
            "currency": "USD",
            "customer_external_id": "existing_cust",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.is_new_transaction is True
        assert response.triggered_rules is not None
        rule_names = {r.rule_name for r in response.triggered_rules}
        assert "review_high_risk_customer" in rule_names

    def test_customer_external_id_unique(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        service.ingest({
            "provider_event_id": "evt_cust_003",
            "amount": Decimal("100.00"),
            "currency": "USD",
            "customer_external_id": "unique_cust",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        service.ingest({
            "provider_event_id": "evt_cust_004",
            "amount": Decimal("200.00"),
            "currency": "USD",
            "customer_external_id": "unique_cust",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        customers = db_session.query(Customer).filter_by(external_id="unique_cust").all()
        assert len(customers) == 1


class TestIngestDeviceEnrichment:
    def test_missing_device_created(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_dev_001",
            "amount": Decimal("500.00"),
            "currency": "USD",
            "customer_external_id": "cust_dev_001",
            "device_fingerprint_hash": "fp_new_001",
            "device_ip": "192.168.1.1",
            "device_user_agent": "Test Agent",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.is_new_transaction is True
        device = db_session.query(Device).filter_by(fingerprint_hash="fp_new_001").first()
        assert device is not None
        assert device.ip == "192.168.1.1"
        assert device.user_agent == "Test Agent"

    def test_existing_device_reused(self, db_session: Session, sample_rules):
        device = Device(fingerprint_hash="fp_existing", ip="10.0.0.1", user_agent="Old Agent", risk_score=0.8)
        db_session.add(device)
        db_session.commit()

        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_dev_002",
            "amount": Decimal("500.00"),
            "currency": "USD",
            "customer_external_id": "cust_dev_002",
            "device_fingerprint_hash": "fp_existing",
            "device_ip": "192.168.1.1",
            "device_user_agent": "New Agent",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.is_new_transaction is True
        db_session.refresh(device)
        assert device.ip == "10.0.0.1"
        assert device.user_agent == "Old Agent"
        assert device.risk_score == Decimal("0.80")

    def test_no_device_fingerprint_skips_device(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_dev_003",
            "amount": Decimal("500.00"),
            "currency": "USD",
            "customer_external_id": "cust_dev_003",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.is_new_transaction is True
        devices = db_session.query(Device).all()
        assert len(devices) == 0


class TestIngestMerchantEnrichment:
    def test_missing_merchant_created(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_merch_001",
            "amount": Decimal("500.00"),
            "currency": "USD",
            "customer_external_id": "cust_merch_001",
            "merchant_name": "New Merchant",
            "merchant_category_code": "5411",
        })

        assert response.is_new_transaction is True
        merchant = db_session.query(Merchant).filter_by(name="New Merchant", category_code="5411").first()
        assert merchant is not None
        assert merchant.risk_level == "standard"

    def test_existing_merchant_reused(self, db_session: Session, sample_rules):
        merchant = Merchant(name="Existing Merchant", category_code="5411", risk_level="high")
        db_session.add(merchant)
        db_session.commit()

        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_merch_002",
            "amount": Decimal("500.00"),
            "currency": "USD",
            "customer_external_id": "cust_merch_002",
            "merchant_name": "Existing Merchant",
            "merchant_category_code": "5411",
        })

        assert response.is_new_transaction is True
        merchants = db_session.query(Merchant).filter_by(name="Existing Merchant", category_code="5411").all()
        assert len(merchants) == 1


class TestIngestNoMatchingRules:
    def test_no_rules_returns_allow(self, db_session: Session):
        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_norules_001",
            "amount": Decimal("5000.00"),
            "currency": "USD",
            "customer_external_id": "cust_norules_001",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.action == TransactionAction.ALLOW
        assert response.case_id is None
        assert len(response.triggered_rules) == 0


class TestIngestRulePrecedence:
    def test_block_overrides_review(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_prec_001",
            "amount": Decimal("15000.00"),
            "currency": "USD",
            "customer_external_id": "cust_prec_001",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "7995",
        })

        assert response.action == TransactionAction.BLOCK
        rule_names = {r.rule_name for r in response.triggered_rules}
        assert "block_high_amount" in rule_names
        assert "block_gambling" in rule_names


class TestIngestDisabledRules:
    def test_disabled_rules_not_evaluated(self, db_session: Session):
        rule = Rule(
            name="disabled_block",
            dsl_expression="amount > 100",
            action=ModelRuleAction.BLOCK,
            priority=100,
            enabled=False,
        )
        db_session.add(rule)
        db_session.commit()

        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_disabled_001",
            "amount": Decimal("5000.00"),
            "currency": "USD",
            "customer_external_id": "cust_disabled_001",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.action == TransactionAction.ALLOW
        rule_names = {r.rule_name for r in response.triggered_rules}
        assert "disabled_block" not in rule_names


class TestIngestRulePriority:
    def test_priority_order_evaluation(self, db_session: Session):
        rule1 = Rule(name="low_priority", dsl_expression="amount > 100", action=ModelRuleAction.REVIEW, priority=1, enabled=True)
        rule2 = Rule(name="high_priority", dsl_expression="amount > 1000", action=ModelRuleAction.BLOCK, priority=100, enabled=True)
        db_session.add_all([rule1, rule2])
        db_session.commit()

        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_prio_001",
            "amount": Decimal("500.00"),
            "currency": "USD",
            "customer_external_id": "cust_prio_001",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.action == TransactionAction.REVIEW
        rule_names = {r.rule_name for r in response.triggered_rules}
        assert "low_priority" in rule_names
        assert "high_priority" not in rule_names

        response2 = service.ingest({
            "provider_event_id": "evt_prio_002",
            "amount": Decimal("1500.00"),
            "currency": "USD",
            "customer_external_id": "cust_prio_002",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response2.action == TransactionAction.BLOCK
        rule_names = {r.rule_name for r in response2.triggered_rules}
        assert "high_priority" in rule_names


class TestIngestCaseCreation:
    def test_review_creates_case(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_case_001",
            "amount": Decimal("5000.00"),
            "currency": "USD",
            "customer_external_id": "cust_case_001",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.action == TransactionAction.REVIEW
        assert response.case_id is not None

        case = db_session.query(Case).filter_by(id=response.case_id).first()
        assert case is not None
        assert case.status == CaseStatus.IN_PROGRESS
        assert case.transaction_id == response.transaction_id

    def test_block_creates_case(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_case_002",
            "amount": Decimal("15000.00"),
            "currency": "USD",
            "customer_external_id": "cust_case_002",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.action == TransactionAction.BLOCK
        assert response.case_id is not None

        case = db_session.query(Case).filter_by(id=response.case_id).first()
        assert case is not None
        assert case.status == CaseStatus.OPEN

    def test_allow_no_case(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        response = service.ingest({
            "provider_event_id": "evt_case_003",
            "amount": Decimal("50.00"),
            "currency": "USD",
            "customer_external_id": "cust_case_003",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert response.action == TransactionAction.ALLOW
        assert response.case_id is None
        cases = db_session.query(Case).all()
        assert len(cases) == 0

    def test_idempotent_retry_no_duplicate_case(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        first = service.ingest({
            "provider_event_id": "evt_case_004",
            "amount": Decimal("5000.00"),
            "currency": "USD",
            "customer_external_id": "cust_case_004",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        second = service.ingest({
            "provider_event_id": "evt_case_004",
            "amount": Decimal("5000.00"),
            "currency": "USD",
            "customer_external_id": "cust_case_004",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })

        assert first.case_id == second.case_id
        cases = db_session.query(Case).filter_by(transaction_id=first.transaction_id).all()
        assert len(cases) == 1


class TestIngestInvalidInput:
    def test_invalid_amount_rejected(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        with pytest.raises(ValueError):
            service.ingest({
                "provider_event_id": "evt_invalid_001",
                "amount": Decimal("-100.00"),
                "currency": "USD",
                "customer_external_id": "cust_invalid_001",
                "merchant_name": "Test Merchant",
                "merchant_category_code": "5411",
            })

    def test_invalid_currency_rejected(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        with pytest.raises(ValueError):
            service.ingest({
                "provider_event_id": "evt_invalid_002",
                "amount": Decimal("100.00"),
                "currency": "INVALID",
                "customer_external_id": "cust_invalid_002",
                "merchant_name": "Test Merchant",
                "merchant_category_code": "5411",
            })

    def test_missing_customer_external_id_rejected(self, db_session: Session, sample_rules):
        service = TransactionService(db_session)

        with pytest.raises(ValueError):
            service.ingest({
                "provider_event_id": "evt_invalid_003",
                "amount": Decimal("100.00"),
                "currency": "USD",
                "customer_external_id": "",
                "merchant_name": "Test Merchant",
                "merchant_category_code": "5411",
            })


class TestIngestDatabaseFailure:
    def test_db_failure_handled(self, db_session: Session, sample_rules, monkeypatch):
        from sqlalchemy.exc import OperationalError

        def mock_commit(*args, **kwargs):
            raise OperationalError("DB error", None, None)

        monkeypatch.setattr(db_session, "commit", mock_commit)

        service = TransactionService(db_session)

        with pytest.raises(OperationalError):
            service.ingest({
                "provider_event_id": "evt_db_fail_001",
                "amount": Decimal("100.00"),
                "currency": "USD",
                "customer_external_id": "cust_db_fail_001",
                "merchant_name": "Test Merchant",
                "merchant_category_code": "5411",
            })


class TestIngestPerformance:
    def test_ingestion_performance(self, db_session: Session, sample_rules):
        import time

        service = TransactionService(db_session)

        start = time.perf_counter()
        for i in range(10):
            service.ingest({
                "provider_event_id": f"evt_perf_{i}",
                "amount": Decimal("500.00"),
                "currency": "USD",
                "customer_external_id": f"cust_perf_{i}",
                "merchant_name": "Test Merchant",
                "merchant_category_code": "5411",
            })
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 10) * 1000
        assert avg_ms < 200


class TestRuleEnginePerformance:
    def test_rule_engine_evaluation_performance(self, sample_rules):
        import time

        from app.services.rule_engine import RuleEngine, Rule

        rules = [
            Rule(
                id=r.id,
                name=r.name,
                dsl_expression=r.dsl_expression,
                action=TransactionAction(r.action.value),
                priority=r.priority,
                enabled=r.enabled,
                version=r.version,
            )
            for r in sample_rules
        ]
        engine = RuleEngine(rules)

        transaction_data = {
            "amount": Decimal("5000.00"),
            "currency": "USD",
            "customer_risk_tier": "high",
            "customer_kyc_status": "verified",
            "device_risk_score": 0.8,
            "merchant_category_code": "7995",
            "merchant_risk_level": "high",
        }

        start = time.perf_counter()
        for _ in range(100):
            engine.evaluate(transaction_data)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 100) * 1000
        assert avg_ms < 50