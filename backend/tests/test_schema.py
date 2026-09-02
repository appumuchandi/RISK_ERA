from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.database import engine, SessionLocal
from app.models import (
    Customer,
    Device,
    Merchant,
    Transaction,
    Rule,
    Case,
    Evidence,
)


@pytest.fixture(autouse=True)
def clean_db():
    """Clean all tables before each test to ensure isolation."""
    with SessionLocal() as db:
        db.execute(text("TRUNCATE TABLE evidence, cases, transactions, rules, merchants, devices, customers, audit_log RESTART IDENTITY CASCADE"))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(text("TRUNCATE TABLE evidence, cases, transactions, rules, merchants, devices, customers, audit_log RESTART IDENTITY CASCADE"))
        db.commit()


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


class TestSchemaExists:
    def test_all_tables_exist(self):
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        expected = {
            "customers",
            "devices",
            "merchants",
            "transactions",
            "rules",
            "cases",
            "evidence",
            "audit_log",
            "alembic_version",
        }
        assert expected.issubset(tables)

    def test_customers_table_structure(self):
        inspector = inspect(engine)
        cols = {c["name"]: c for c in inspector.get_columns("customers")}
        assert "id" in cols
        assert "external_id" in cols
        assert "risk_tier" in cols
        assert "kyc_status" in cols
        assert "created_at" in cols
        assert cols["external_id"]["nullable"] is False
        assert cols["risk_tier"]["nullable"] is False
        assert cols["kyc_status"]["nullable"] is False

    def test_devices_table_structure(self):
        inspector = inspect(engine)
        cols = {c["name"]: c for c in inspector.get_columns("devices")}
        assert "fingerprint_hash" in cols
        assert "ip" in cols
        assert "user_agent" in cols
        assert "risk_score" in cols
        assert cols["fingerprint_hash"]["nullable"] is False
        assert cols["ip"]["nullable"] is True
        assert cols["risk_score"]["nullable"] is True

    def test_merchants_table_structure(self):
        inspector = inspect(engine)
        cols = {c["name"]: c for c in inspector.get_columns("merchants")}
        assert "name" in cols
        assert "category_code" in cols
        assert "risk_level" in cols
        assert cols["name"]["nullable"] is False
        assert cols["category_code"]["nullable"] is False

    def test_transactions_table_structure(self):
        inspector = inspect(engine)
        cols = {c["name"]: c for c in inspector.get_columns("transactions")}
        assert "provider_event_id" in cols
        assert "amount" in cols
        assert "currency" in cols
        assert "status" in cols
        assert "customer_id" in cols
        assert "device_id" in cols
        assert "merchant_id" in cols
        assert "raw_payload" in cols
        assert cols["provider_event_id"]["nullable"] is False
        assert cols["amount"]["nullable"] is False
        assert cols["currency"]["nullable"] is False
        assert cols["customer_id"]["nullable"] is False
        assert cols["merchant_id"]["nullable"] is False
        assert cols["device_id"]["nullable"] is True
        assert cols["raw_payload"]["nullable"] is False

    def test_rules_table_structure(self):
        inspector = inspect(engine)
        cols = {c["name"]: c for c in inspector.get_columns("rules")}
        assert "name" in cols
        assert "dsl_expression" in cols
        assert "action" in cols
        assert "priority" in cols
        assert "enabled" in cols
        assert "version" in cols
        assert cols["name"]["nullable"] is False
        assert cols["dsl_expression"]["nullable"] is False
        assert cols["action"]["nullable"] is False

    def test_cases_table_structure(self):
        inspector = inspect(engine)
        cols = {c["name"]: c for c in inspector.get_columns("cases")}
        assert "transaction_id" in cols
        assert "status" in cols
        assert "assignee" in cols
        assert "created_at" in cols
        assert "updated_at" in cols
        assert cols["transaction_id"]["nullable"] is False
        assert cols["status"]["nullable"] is False

    def test_evidence_table_structure(self):
        inspector = inspect(engine)
        cols = {c["name"]: c for c in inspector.get_columns("evidence")}
        assert "case_id" in cols
        assert "source_type" in cols
        assert "source_id" in cols
        assert "payload" in cols
        assert "retrieved_at" in cols
        assert cols["case_id"]["nullable"] is False
        assert cols["source_type"]["nullable"] is False
        assert cols["source_id"]["nullable"] is False
        assert cols["payload"]["nullable"] is False

    def test_audit_log_table_structure(self):
        inspector = inspect(engine)
        cols = {c["name"]: c for c in inspector.get_columns("audit_log")}
        assert "actor" in cols
        assert "action" in cols
        assert "resource_type" in cols
        assert "resource_id" in cols
        assert "before_json" in cols
        assert "after_json" in cols
        assert "prev_hash" in cols
        assert "created_at" in cols
        assert cols["actor"]["nullable"] is False
        assert cols["action"]["nullable"] is False
        assert cols["resource_type"]["nullable"] is False
        assert cols["resource_id"]["nullable"] is False


class TestForeignKeys:
    def test_transaction_customer_fk(self):
        inspector = inspect(engine)
        fks = inspector.get_foreign_keys("transactions")
        customer_fk = next((fk for fk in fks if "customer_id" in fk["constrained_columns"]), None)
        assert customer_fk is not None
        assert customer_fk["referred_table"] == "customers"
        assert customer_fk["options"].get("ondelete") == "RESTRICT"

    def test_transaction_device_fk(self):
        inspector = inspect(engine)
        fks = inspector.get_foreign_keys("transactions")
        device_fk = next((fk for fk in fks if "device_id" in fk["constrained_columns"]), None)
        assert device_fk is not None
        assert device_fk["referred_table"] == "devices"
        assert device_fk["options"].get("ondelete") == "SET NULL"

    def test_transaction_merchant_fk(self):
        inspector = inspect(engine)
        fks = inspector.get_foreign_keys("transactions")
        merchant_fk = next((fk for fk in fks if "merchant_id" in fk["constrained_columns"]), None)
        assert merchant_fk is not None
        assert merchant_fk["referred_table"] == "merchants"
        assert merchant_fk["options"].get("ondelete") == "RESTRICT"

    def test_case_transaction_fk(self):
        inspector = inspect(engine)
        fks = inspector.get_foreign_keys("cases")
        tx_fk = next((fk for fk in fks if "transaction_id" in fk["constrained_columns"]), None)
        assert tx_fk is not None
        assert tx_fk["referred_table"] == "transactions"
        assert tx_fk["options"].get("ondelete") == "RESTRICT"

    def test_evidence_case_fk(self):
        inspector = inspect(engine)
        fks = inspector.get_foreign_keys("evidence")
        case_fk = next((fk for fk in fks if "case_id" in fk["constrained_columns"]), None)
        assert case_fk is not None
        assert case_fk["referred_table"] == "cases"
        assert case_fk["options"].get("ondelete") == "CASCADE"


class TestUniqueConstraints:
    def test_provider_event_id_unique(self, db_session):
        customer = Customer(external_id="cust_1", risk_tier="standard", kyc_status="verified")
        device = Device(fingerprint_hash="fp_1")
        merchant = Merchant(name="Merchant 1", category_code="5411", risk_level="standard")
        db_session.add_all([customer, device, merchant])
        db_session.flush()

        tx1 = Transaction(
            provider_event_id="evt_123",
            amount=Decimal("100.00"),
            currency="USD",
            customer_id=customer.id,
            device_id=device.id,
            merchant_id=merchant.id,
            raw_payload={},
        )
        db_session.add(tx1)
        db_session.commit()

        tx2 = Transaction(
            provider_event_id="evt_123",
            amount=Decimal("50.00"),
            currency="USD",
            customer_id=customer.id,
            device_id=device.id,
            merchant_id=merchant.id,
            raw_payload={},
        )
        db_session.add(tx2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_customer_external_id_unique(self, db_session):
        c1 = Customer(external_id="ext_1", risk_tier="standard", kyc_status="pending")
        db_session.add(c1)
        db_session.commit()

        c2 = Customer(external_id="ext_1", risk_tier="high", kyc_status="verified")
        db_session.add(c2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_rule_name_unique(self, db_session):
        r1 = Rule(name="rule_1", dsl_expression="amount > 1000", action="review", priority=1)
        db_session.add(r1)
        db_session.commit()

        r2 = Rule(name="rule_1", dsl_expression="amount > 500", action="block", priority=2)
        db_session.add(r2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_case_transaction_id_unique(self, db_session):
        customer = Customer(external_id="cust_2", risk_tier="standard", kyc_status="verified")
        device = Device(fingerprint_hash="fp_2")
        merchant = Merchant(name="Merchant 2", category_code="5411", risk_level="standard")
        db_session.add_all([customer, device, merchant])
        db_session.flush()

        tx = Transaction(
            provider_event_id="evt_456",
            amount=Decimal("100.00"),
            currency="USD",
            customer_id=customer.id,
            device_id=device.id,
            merchant_id=merchant.id,
            raw_payload={},
        )
        db_session.add(tx)
        db_session.flush()

        case1 = Case(transaction_id=tx.id, status="open")
        db_session.add(case1)
        db_session.commit()

        case2 = Case(transaction_id=tx.id, status="in_progress")
        db_session.add(case2)
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestIndexes:
    def test_transaction_provider_event_id_index(self):
        inspector = inspect(engine)
        idxs = inspector.get_indexes("transactions")
        idx_names = [idx["name"] for idx in idxs]
        assert any("provider_event_id" in name for name in idx_names)

    def test_customer_external_id_index(self):
        inspector = inspect(engine)
        idxs = inspector.get_indexes("customers")
        idx_names = [idx["name"] for idx in idxs]
        assert any("external_id" in name for name in idx_names)

    def test_device_fingerprint_hash_index(self):
        inspector = inspect(engine)
        idxs = inspector.get_indexes("devices")
        idx_names = [idx["name"] for idx in idxs]
        assert any("fingerprint_hash" in name for name in idx_names)


class TestModelRelationships:
    def test_customer_transactions_relationship(self, db_session):
        customer = Customer(external_id="cust_rel", risk_tier="standard", kyc_status="verified")
        device = Device(fingerprint_hash="fp_rel")
        merchant = Merchant(name="Merchant Rel", category_code="5411", risk_level="standard")
        db_session.add_all([customer, device, merchant])
        db_session.flush()

        tx = Transaction(
            provider_event_id="evt_rel",
            amount=Decimal("100.00"),
            currency="USD",
            customer_id=customer.id,
            device_id=device.id,
            merchant_id=merchant.id,
            raw_payload={},
        )
        db_session.add(tx)
        db_session.commit()
        db_session.refresh(customer)

        assert len(customer.transactions.all()) == 1
        assert customer.transactions.first().id == tx.id

    def test_case_evidence_cascade_delete(self, db_session):
        customer = Customer(external_id="cust_cascade", risk_tier="standard", kyc_status="verified")
        device = Device(fingerprint_hash="fp_cascade")
        merchant = Merchant(name="Merchant Cascade", category_code="5411", risk_level="standard")
        db_session.add_all([customer, device, merchant])
        db_session.flush()

        tx = Transaction(
            provider_event_id="evt_cascade",
            amount=Decimal("100.00"),
            currency="USD",
            customer_id=customer.id,
            device_id=device.id,
            merchant_id=merchant.id,
            raw_payload={},
        )
        db_session.add(tx)
        db_session.flush()

        case = Case(transaction_id=tx.id, status="open")
        db_session.add(case)
        db_session.flush()

        evidence = Evidence(case_id=case.id, source_type="transaction", source_id=str(tx.id), payload={})
        db_session.add(evidence)
        db_session.commit()

        db_session.delete(case)
        db_session.commit()

        remaining = db_session.query(Evidence).filter_by(case_id=case.id).all()
        assert len(remaining) == 0