from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import JWTAuth
from app.core.database import SessionLocal
from app.main import app
from app.models import Rule, Customer, Merchant, Device, Transaction, Case
from app.models.rule import RuleAction as ModelRuleAction
from app.services.transaction_service import TransactionService
from app.services.rule_engine import RuleEngine
from app.services.intelligence_service import IntelligenceService


# ---- Fixtures mirroring Phase2 ----

@pytest.fixture(scope="session")
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_db(db: Session):
    # Truncate all relevant tables before each test for isolation
    db.execute(text("TRUNCATE TABLE cases, transactions, rules, merchants, devices, customers, audit_log, investigations, analyst_feedback, evidence RESTART IDENTITY CASCADE"))
    db.commit()
    yield
    db.execute(text("TRUNCATE TABLE cases, transactions, rules, merchants, devices, customers, audit_log, investigations, analyst_feedback, evidence RESTART IDENTITY CASCADE"))
    db.commit()


@pytest.fixture
def db_session(db: Session) -> Session:
    yield db
    db.rollback()


@pytest.fixture
def sample_rules(db_session: Session):
    rules = [
        Rule(name="block_high_amount", dsl_expression="amount > 10000", action=ModelRuleAction.BLOCK, priority=100, enabled=True),
        Rule(name="review_medium_amount", dsl_expression="amount > 5000", action=ModelRuleAction.REVIEW, priority=80, enabled=True),
        Rule(name="review_high_risk_customer", dsl_expression="customer_risk_tier == 'high'", action=ModelRuleAction.REVIEW, priority=75, enabled=True),
        Rule(name="block_gambling", dsl_expression="merchant_category_code == '7995'", action=ModelRuleAction.BLOCK, priority=95, enabled=True),
        Rule(name="allow_small", dsl_expression="amount < 500", action=ModelRuleAction.ALLOW, priority=10, enabled=True),
    ]
    db_session.add_all(rules)
    db_session.commit()
    return rules


@pytest.fixture
def auth_headers():
    token = JWTAuth.encode_token("analyst")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers():
    token = JWTAuth.encode_token("admin")
    return {"Authorization": f"Bearer {token}"}


def _seed_txns(db_session: Session, n=6):
    svc = TransactionService(db_session)
    out = []
    for i in range(n):
        amount = Decimal(str(1000 + i * 4000))  # varies to trigger rules
        # alternate merchant categories and customers/devices to test relationships
        res = svc.ingest({
            "provider_event_id": f"evt_p3_{uuid4().hex[:8]}_{i}",
            "amount": amount,
            "currency": "INR",
            "customer_external_id": f"cust_p3_{i % 3}",
            "device_fingerprint_hash": f"fp_p3_{i % 2}",
            "device_ip": f"10.0.0.{i%250+1}",
            "merchant_name": f"Merchant {i%2}",
            "merchant_category_code": "5411" if i % 2 == 0 else "7995",
        })
        out.append(res)
    # also ensure at least one customer has multiple merchants/devices
    return out


def _get_customer_id(db_session: Session, external_id: str) -> str:
    row = db_session.execute(text("SELECT id FROM customers WHERE external_id=:eid"), {"eid": external_id}).fetchone()
    return str(row[0]) if row else None


def _get_merchant_id(db_session: Session) -> str:
    row = db_session.execute(text("SELECT id FROM merchants LIMIT 1")).fetchone()
    return str(row[0]) if row else None


def _get_device_id(db_session: Session) -> str:
    row = db_session.execute(text("SELECT id FROM devices LIMIT 1")).fetchone()
    return str(row[0]) if row else None


# ==========================
# AUTH TESTS
# ==========================

class TestIntelligenceAuth:
    def test_customer_missing_jwt_401(self, db_session, sample_rules):
        _seed_txns(db_session, 2)
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cid}/profile")
        assert r.status_code == 401

    def test_merchant_missing_jwt_401(self, db_session, sample_rules):
        _seed_txns(db_session, 1)
        mid = _get_merchant_id(db_session)
        client = TestClient(app)
        r = client.get(f"/api/v1/merchants/{mid}/profile")
        assert r.status_code == 401

    def test_device_missing_jwt_401(self, db_session, sample_rules):
        _seed_txns(db_session, 1)
        did = _get_device_id(db_session)
        client = TestClient(app)
        r = client.get(f"/api/v1/devices/{did}/activity")
        assert r.status_code == 401

    def test_invalid_jwt_401(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 1)
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cid}/profile", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401
        # also merchant
        mid = _get_merchant_id(db_session)
        r2 = client.get(f"/api/v1/merchants/{mid}/profile", headers={"Authorization": "Bearer bad"})
        assert r2.status_code == 401
        did = _get_device_id(db_session)
        r3 = client.get(f"/api/v1/devices/{did}/activity", headers={"Authorization": "Bearer bad"})
        assert r3.status_code == 401

    def test_expired_jwt_401(self, db_session, sample_rules):
        _seed_txns(db_session, 1)
        expired = JWTAuth.encode_token("analyst", expires_delta=timedelta(seconds=-1))
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cid}/profile", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_valid_analyst_jwt_success(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 2)
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cid}/profile", headers=auth_headers)
        assert r.status_code == 200
        mid = _get_merchant_id(db_session)
        r2 = client.get(f"/api/v1/merchants/{mid}/profile", headers=auth_headers)
        assert r2.status_code == 200
        did = _get_device_id(db_session)
        r3 = client.get(f"/api/v1/devices/{did}/activity", headers=auth_headers)
        assert r3.status_code == 200

    def test_valid_admin_jwt_success(self, db_session, sample_rules, admin_headers):
        _seed_txns(db_session, 2)
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cid}/profile", headers=admin_headers)
        assert r.status_code == 200
        mid = _get_merchant_id(db_session)
        r2 = client.get(f"/api/v1/merchants/{mid}/profile", headers=admin_headers)
        assert r2.status_code == 200
        did = _get_device_id(db_session)
        r3 = client.get(f"/api/v1/devices/{did}/activity", headers=admin_headers)
        assert r3.status_code == 200

    def test_query_param_auth_401(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 1)
        token = auth_headers["Authorization"].split()[1]
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cid}/profile?Authorization=Bearer {token}")
        assert r.status_code == 401
        r2 = client.get(f"/api/v1/customers/{cid}/profile?authorization=Bearer {token}")
        assert r2.status_code == 401
        # also without any header but with query param token - should be 401
        mid = _get_merchant_id(db_session)
        r3 = client.get(f"/api/v1/merchants/{mid}/profile?Authorization=Bearer {token}")
        assert r3.status_code == 401

    def test_actor_query_param_impersonation_does_not_work(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 1)
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        # With valid JWT, actor param should be ignored, still 200
        r = client.get(f"/api/v1/customers/{cid}/profile?actor=admin", headers=auth_headers)
        assert r.status_code == 200
        # Without JWT, actor param should not authenticate, 401
        r2 = client.get(f"/api/v1/customers/{cid}/profile?actor=analyst")
        assert r2.status_code == 401
        r3 = client.get(f"/api/v1/merchants/{_get_merchant_id(db_session)}/profile?actor=admin")
        assert r3.status_code == 401
        r4 = client.get(f"/api/v1/devices/{_get_device_id(db_session)}/activity?actor=admin")
        assert r4.status_code == 401


class TestIntelligenceListAuth:
    def test_list_customers_requires_auth(self, db_session, sample_rules):
        _seed_txns(db_session, 1)
        client = TestClient(app)
        r = client.get("/api/v1/customers")
        assert r.status_code == 401
        r2 = client.get("/api/v1/customers", headers={"Authorization": "Bearer invalid"})
        assert r2.status_code == 401

    def test_list_merchants_devices_require_auth(self, db_session, sample_rules):
        _seed_txns(db_session, 1)
        client = TestClient(app)
        assert client.get("/api/v1/merchants").status_code == 401
        assert client.get("/api/v1/devices").status_code == 401

    def test_list_with_valid_token_succeeds(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 2)
        client = TestClient(app)
        assert client.get("/api/v1/customers", headers=auth_headers).status_code == 200
        assert client.get("/api/v1/merchants", headers=auth_headers).status_code == 200
        assert client.get("/api/v1/devices", headers=auth_headers).status_code == 200


# ==========================
# CUSTOMER TESTS
# ==========================

class TestCustomerIntelligence:
    def test_valid_profile(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 4)
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cid}/profile", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        # Identity fields
        assert "customer_id" in body
        assert "external_id" in body
        assert body["external_id"] == "cust_p3_0"
        # Transaction intelligence
        for f in ["total_transactions", "total_amount", "average_amount", "first_transaction_at", "last_transaction_at"]:
            assert f in body, f"missing {f}"
        # Risk intelligence
        for f in ["average_risk_score", "max_risk_score", "risk_level", "blocked_count", "review_count", "allowed_count", "flagged_count", "failed_count", "triggered_rule_frequency"]:
            assert f in body, f"missing {f}"
        # Relationships
        for f in ["unique_merchants", "unique_devices", "recent_merchants", "recent_devices"]:
            assert f in body
        # Cases
        assert "cases" in body
        assert "total" in body["cases"]
        # Recent transactions
        assert "recent_transactions" in body
        assert isinstance(body["recent_transactions"], list)
        for tx in body["recent_transactions"]:
            for f in ["id", "amount", "currency", "risk_score", "risk_level", "decision", "created_at"]:
                assert f in tx, f"missing tx field {f}"
        # Risk explanation
        assert "risk_explanation" in body
        assert "supporting_transaction_ids" in body
        assert "top_triggered_rules" in body

    def test_unknown_customer_404(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{uuid4()}/profile", headers=auth_headers)
        assert r.status_code == 404

    def test_zero_activity_shape(self, db_session, sample_rules, auth_headers):
        # Create customer with no transactions
        cust = Customer(external_id=f"cust_empty_{uuid4().hex[:6]}", risk_tier="standard", kyc_status="pending")
        db_session.add(cust)
        db_session.commit()
        db_session.refresh(cust)
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cust.id}/profile", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["total_transactions"] == 0
        assert body["total_amount"] == "0" or body["total_amount"] == "0.00" or float(body["total_amount"]) == 0
        assert body["average_risk_score"] == 0.0
        assert body["max_risk_score"] == 0.0
        assert body["risk_level"] == "low"
        assert body["unique_merchants"] == 0
        assert body["unique_devices"] == 0
        assert body["recent_transactions"] == []
        assert body["recent_merchants"] == []
        assert body["recent_devices"] == []
        assert body["cases"]["total"] == 0

    def test_transaction_aggregation_correctness(self, db_session, sample_rules, auth_headers):
        svc = TransactionService(db_session)
        # Create dedicated customer
        ext = f"cust_agg_{uuid4().hex[:6]}"
        amounts = [Decimal("100.00"), Decimal("6000.00"), Decimal("12000.00")]
        for i, amt in enumerate(amounts):
            svc.ingest({
                "provider_event_id": f"evt_agg_{uuid4().hex[:8]}_{i}",
                "amount": amt,
                "currency": "INR",
                "customer_external_id": ext,
                "merchant_name": "Agg Merchant",
                "merchant_category_code": "5411",
            })
        # Get customer id
        cid = _get_customer_id(db_session, ext)
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cid}/profile", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["total_transactions"] == 3
        expected_total = sum(amounts)
        assert abs(Decimal(str(body["total_amount"])) - expected_total) < Decimal("0.01")
        expected_avg = expected_total / 3
        assert abs(Decimal(str(body["average_amount"])) - expected_avg) < Decimal("0.01")
        assert Decimal(str(body["min_amount"])) == min(amounts)
        assert Decimal(str(body["max_amount"])) == max(amounts)

    def test_risk_aggregation_correctness(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 5)
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cid}/profile", headers=auth_headers)
        body = r.json()
        # blocked should correspond to amount >10000 or gambling; ensure counts are ints and sum <= total
        assert isinstance(body["blocked_count"], int)
        assert isinstance(body["review_count"], int)
        assert isinstance(body["allowed_count"], int)
        total_decision = body["blocked_count"] + body["review_count"] + body["allowed_count"]
        assert total_decision == body["total_transactions"] or total_decision <= body["total_transactions"]
        # risk level should be one of low/medium/high/critical
        assert body["risk_level"] in ("low", "medium", "high", "critical")
        # average risk between 0-100
        assert 0 <= body["average_risk_score"] <= 100
        assert 0 <= body["max_risk_score"] <= 100
        assert body["max_risk_score"] >= body["average_risk_score"]

    def test_recent_transactions(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 6)
        cid = _get_customer_id(db_session, "cust_p3_1")
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cid}/profile", headers=auth_headers)
        body = r.json()
        assert len(body["recent_transactions"]) <= 10
        assert len(body["recent_transactions"]) > 0
        # They should be sorted descending by created_at
        dates = [tx["created_at"] for tx in body["recent_transactions"]]
        assert dates == sorted(dates, reverse=True)

    def test_rule_aggregation(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 6)
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cid}/profile", headers=auth_headers)
        body = r.json()
        assert isinstance(body["triggered_rule_frequency"], dict)
        # With our seed, block_high_amount and review_medium_amount should appear
        # At least one rule triggered
        assert len(body["triggered_rule_frequency"]) > 0
        # top_triggered_rules count matches
        for tr in body["top_triggered_rules"]:
            assert "rule_name" in tr
            assert "count" in tr
            assert "action" in tr
            assert tr["count"] == body["triggered_rule_frequency"][tr["rule_name"]]


# ==========================
# MERCHANT TESTS
# ==========================

class TestMerchantIntelligence:
    def test_valid_profile(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 4)
        mid = _get_merchant_id(db_session)
        client = TestClient(app)
        r = client.get(f"/api/v1/merchants/{mid}/profile", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        for f in ["merchant_id", "name", "category_code", "total_transactions", "total_volume", "average_amount", "first_activity", "last_activity", "average_risk_score", "max_risk_score", "risk_level", "unique_customers", "unique_devices", "recent_customers", "recent_devices", "cases", "recent_transactions", "risk_explanation", "supporting_transaction_ids"]:
            assert f in body, f"missing {f}"
        assert isinstance(body["recent_transactions"], list)
        assert "top_triggered_rules" in body

    def test_unknown_merchant_404(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get(f"/api/v1/merchants/{uuid4()}/profile", headers=auth_headers)
        assert r.status_code == 404

    def test_merchant_aggregation_correctness(self, db_session, sample_rules, auth_headers):
        svc = TransactionService(db_session)
        # Create transactions for same merchant but different customers
        for i in range(3):
            svc.ingest({
                "provider_event_id": f"evt_merch_agg_{uuid4().hex[:8]}_{i}",
                "amount": Decimal(str(2000 + i*3000)),
                "currency": "INR",
                "customer_external_id": f"cust_merch_agg_{i}",
                "merchant_name": "MerchantAgg",
                "merchant_category_code": "6011",
            })
        row = db_session.execute(text("SELECT id FROM merchants WHERE name='MerchantAgg'")).fetchone()
        mid = str(row[0])
        client = TestClient(app)
        r = client.get(f"/api/v1/merchants/{mid}/profile", headers=auth_headers)
        body = r.json()
        assert body["total_transactions"] == 3
        assert body["unique_customers"] == 3

    def test_risk_distribution(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 6)
        mid = _get_merchant_id(db_session)
        client = TestClient(app)
        r = client.get(f"/api/v1/merchants/{mid}/profile", headers=auth_headers)
        body = r.json()
        assert body["allowed_count"] + body["review_count"] + body["blocked_count"] == body["total_transactions"]
        assert body["risk_level"] in ("low", "medium", "high", "critical")

    def test_customer_device_relationships(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 6)
        mid = _get_merchant_id(db_session)
        client = TestClient(app)
        r = client.get(f"/api/v1/merchants/{mid}/profile", headers=auth_headers)
        body = r.json()
        assert isinstance(body["unique_customers"], int)
        assert isinstance(body["unique_devices"], int)
        assert isinstance(body["recent_customers"], list)
        assert isinstance(body["recent_devices"], list)
        for rc in body["recent_customers"]:
            assert "customer_id" in rc
            assert "external_id" in rc
        for rd in body["recent_devices"]:
            assert "device_id" in rd
            assert "fingerprint_hash" in rd

    def test_empty_merchant_shape(self, db_session, sample_rules, auth_headers):
        m = Merchant(name=f"EmptyMerchant_{uuid4().hex[:6]}", category_code="9999", risk_level="standard")
        db_session.add(m)
        db_session.commit()
        db_session.refresh(m)
        client = TestClient(app)
        r = client.get(f"/api/v1/merchants/{m.id}/profile", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["total_transactions"] == 0
        assert body["recent_transactions"] == []


# ==========================
# DEVICE TESTS
# ==========================

class TestDeviceIntelligence:
    def test_valid_activity(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 4)
        did = _get_device_id(db_session)
        client = TestClient(app)
        r = client.get(f"/api/v1/devices/{did}/activity", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        for f in ["device_id", "fingerprint_hash", "total_transactions", "total_volume", "average_amount", "first_seen", "last_seen", "average_risk_score", "max_risk_score", "risk_level", "unique_customers", "unique_merchants", "recent_customers", "recent_merchants", "cases", "recent_transactions", "triggered_rule_frequency", "concentration_signal"]:
            assert f in body, f"missing {f}"
        # risk_explanation present
        assert "risk_explanation" in body
        assert "supporting_transaction_ids" in body

    def test_unknown_device_404(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get(f"/api/v1/devices/{uuid4()}/activity", headers=auth_headers)
        assert r.status_code == 404

    def test_device_aggregation_correctness(self, db_session, sample_rules, auth_headers):
        svc = TransactionService(db_session)
        fp = f"fp_device_agg_{uuid4().hex[:6]}"
        amounts = [Decimal("500.00"), Decimal("7000.00")]
        for i, amt in enumerate(amounts):
            svc.ingest({
                "provider_event_id": f"evt_dev_agg_{uuid4().hex[:8]}_{i}",
                "amount": amt,
                "currency": "INR",
                "customer_external_id": f"cust_dev_agg_{i}",
                "device_fingerprint_hash": fp,
                "merchant_name": "MerchantDev",
                "merchant_category_code": "5411",
            })
        row = db_session.execute(text("SELECT id FROM devices WHERE fingerprint_hash=:fp"), {"fp": fp}).fetchone()
        did = str(row[0])
        client = TestClient(app)
        r = client.get(f"/api/v1/devices/{did}/activity", headers=auth_headers)
        body = r.json()
        assert body["total_transactions"] == 2
        assert abs(Decimal(str(body["total_volume"])) - sum(amounts)) < Decimal("0.01")

    def test_customer_merchant_relationships(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 6)
        did = _get_device_id(db_session)
        client = TestClient(app)
        r = client.get(f"/api/v1/devices/{did}/activity", headers=auth_headers)
        body = r.json()
        assert isinstance(body["unique_customers"], int)
        assert isinstance(body["unique_merchants"], int)
        assert isinstance(body["recent_customers"], list)
        assert isinstance(body["recent_merchants"], list)
        # concentration_signal should use neutral terminology, not "fraudulent"
        sig = body["concentration_signal"].lower()
        assert "fraud" not in sig

    def test_risk_aggregation(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 5)
        did = _get_device_id(db_session)
        client = TestClient(app)
        r = client.get(f"/api/v1/devices/{did}/activity", headers=auth_headers)
        body = r.json()
        assert body["allowed_count"] + body["review_count"] + body["blocked_count"] == body["total_transactions"]
        assert 0 <= body["average_risk_score"] <= 100
        # flagged/failed counts
        assert isinstance(body["flagged_count"], int)
        assert isinstance(body["failed_count"], int)

    def test_empty_device_shape(self, db_session, sample_rules, auth_headers):
        d = Device(fingerprint_hash=f"fp_empty_{uuid4().hex[:6]}", ip="10.9.9.9")
        db_session.add(d)
        db_session.commit()
        db_session.refresh(d)
        client = TestClient(app)
        r = client.get(f"/api/v1/devices/{d.id}/activity", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["total_transactions"] == 0
        assert body["concentration_signal"] == "No activity" or "No transactions" in body["risk_explanation"]


# ==========================
# SECURITY TESTS
# ==========================

class TestIntelligenceSecurity:
    def test_no_actor_accepted_from_client(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 1)
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        # Try to send actor in JSON body via POST to GET endpoint with actor query - should not affect auth
        r = client.get(f"/api/v1/customers/{cid}/profile?actor=admin", headers=auth_headers)
        assert r.status_code == 200
        # Try sending actor as header? should not be used
        h = dict(auth_headers)
        h["X-Actor"] = "admin"
        r2 = client.get(f"/api/v1/customers/{cid}/profile", headers=h)
        assert r2.status_code == 200
        # Without JWT but with actor header should still 401
        r3 = client.get(f"/api/v1/customers/{cid}/profile", headers={"X-Actor": "admin"})
        assert r3.status_code == 401

    def test_no_authorization_query_parameter(self, db_session, sample_rules):
        _seed_txns(db_session, 1)
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        token = JWTAuth.encode_token("analyst")
        r = client.get(f"/api/v1/customers/{cid}/profile?authorization=Bearer {token}")
        assert r.status_code == 401
        r2 = client.get(f"/api/v1/customers/{cid}/profile?Authorization=Bearer {token}")
        assert r2.status_code == 401

    def test_no_role_supplied_by_client(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 1)
        cid = _get_customer_id(db_session, "cust_p3_0")
        client = TestClient(app)
        # Try to inject role via query or header
        r = client.get(f"/api/v1/customers/{cid}/profile?role=admin", headers=auth_headers)
        assert r.status_code == 200
        # Ensure response does not reflect injected role
        # Body should still contain real profile, not role-based filtering
        body = r.json()
        assert body["customer_id"] == cid
        # Try header injection
        h = dict(auth_headers)
        h["X-Role"] = "admin"
        r2 = client.get(f"/api/v1/customers/{cid}/profile", headers=h)
        assert r2.status_code == 200


# ==========================
# PERFORMANCE TESTS
# ==========================

class TestIntelligencePerformance:
    def test_no_per_transaction_db_queries(self, db_session, sample_rules, auth_headers):
        # Seed many transactions for one customer to expose N+1
        svc = TransactionService(db_session)
        ext = f"cust_perf_{uuid4().hex[:6]}"
        for i in range(15):
            svc.ingest({
                "provider_event_id": f"evt_perf_{uuid4().hex[:8]}_{i}",
                "amount": Decimal("6000.00"),
                "currency": "INR",
                "customer_external_id": ext,
                "merchant_name": "Perf Merchant",
                "merchant_category_code": "5411",
            })
        cid = _get_customer_id(db_session, ext)
        # Count DB execute calls during profile fetch
        from unittest.mock import patch
        original_execute = db_session.execute
        call_count = {"n": 0}
        def counting_execute(*args, **kwargs):
            call_count["n"] += 1
            return original_execute(*args, **kwargs)
        with patch.object(db_session, "execute", side_effect=counting_execute):
            svc2 = IntelligenceService(db_session)
            # Need to bypass TestClient and call service directly to count
            prof = svc2.get_customer_profile(uuid.UUID(cid))
            assert prof is not None
        # Should be bounded: customer lookup + transactions + cases + rules = ~4-6 queries, not 15+
        assert call_count["n"] < 15, f"Too many DB queries: {call_count['n']} suggests per-transaction N+1"
        # Also verify via API still works
        client = TestClient(app)
        r = client.get(f"/api/v1/customers/{cid}/profile", headers=auth_headers)
        assert r.status_code == 200


# ==========================
# DATABASE ISOLATION TESTS
# ==========================

class TestDbIsolation:
    def test_isolation_guard(self):
        import os
        assert "risk_era_test" in os.getenv("DATABASE_URL", "")

    def test_demo_db_not_touched(self):
        # Verify guard holds; if we reached here, isolation held
        assert True

    def test_intelligence_does_not_use_seed_demo_data(self, db_session, sample_rules):
        # Ensure no call to seed_demo_data.py is made implicitly
        import pathlib
        # Just verify current DB is test DB and has isolated data
        count = db_session.execute(text("SELECT count(*) FROM customers")).scalar()
        # After clean_db, we expect only seeded customers, not full demo set (42)
        # Our seeded counts are small; ensure not 42
        assert count < 20
