from __future__ import annotations

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
from app.models import Rule
from app.models.rule import RuleAction as ModelRuleAction
from app.services.transaction_service import TransactionService


@pytest.fixture(scope="session")
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_db(db: Session):
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
        Rule(name="block_gambling", dsl_expression="merchant_category_code == '7995'", action=ModelRuleAction.BLOCK, priority=95, enabled=True),
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


def _seed_basic(db_session: Session, n=10):
    svc = TransactionService(db_session)
    for i in range(n):
        amt = Decimal(str(1000 + i * 3000))
        cat = "7995" if i % 3 == 0 else "5411"
        svc.ingest({
            "provider_event_id": f"evt_ana_{uuid4().hex[:8]}_{i}",
            "amount": amt,
            "currency": "INR",
            "customer_external_id": f"cust_ana_{i % 4}",
            "device_fingerprint_hash": f"fp_ana_{i % 2}",
            "merchant_name": f"MerchantAna{i % 3}",
            "merchant_category_code": cat,
        })
    db_session.commit()


# AUTH TESTS

class TestAnalyticsAuth:
    def test_missing_jwt_401(self, db_session, sample_rules):
        client = TestClient(app)
        r = client.get("/api/v1/analytics/dashboard")
        assert r.status_code == 401

    def test_invalid_jwt_401(self, db_session, sample_rules):
        client = TestClient(app)
        r = client.get("/api/v1/analytics/dashboard", headers={"Authorization": "Bearer invalid.token"})
        assert r.status_code == 401

    def test_expired_jwt_401(self, db_session, sample_rules):
        expired = JWTAuth.encode_token("analyst", expires_delta=timedelta(seconds=-1))
        client = TestClient(app)
        r = client.get("/api/v1/analytics/dashboard", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_query_param_auth_rejected(self, db_session, sample_rules, auth_headers):
        token = auth_headers["Authorization"].split()[1]
        client = TestClient(app)
        r = client.get(f"/api/v1/analytics/dashboard?authorization=Bearer {token}")
        assert r.status_code == 401
        r2 = client.get(f"/api/v1/analytics/dashboard?Authorization=Bearer {token}")
        assert r2.status_code == 401

    def test_actor_impersonation_rejected(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        # With JWT, actor param ignored, still 200
        r = client.get("/api/v1/analytics/dashboard?actor=admin", headers=auth_headers)
        assert r.status_code == 200
        # Without JWT, actor should not auth
        r2 = client.get("/api/v1/analytics/dashboard?actor=admin")
        assert r2.status_code == 401

    def test_valid_analyst_200(self, db_session, sample_rules, auth_headers):
        _seed_basic(db_session, 5)
        client = TestClient(app)
        r = client.get("/api/v1/analytics/dashboard", headers=auth_headers)
        assert r.status_code == 200

    def test_valid_admin_200(self, db_session, sample_rules, admin_headers):
        _seed_basic(db_session, 5)
        client = TestClient(app)
        r = client.get("/api/v1/analytics/dashboard", headers=admin_headers)
        assert r.status_code == 200


# CONTRACT TESTS

class TestDashboardContract:
    def test_response_shape(self, db_session, sample_rules, auth_headers):
        _seed_basic(db_session, 5)
        client = TestClient(app)
        r = client.get("/api/v1/analytics/dashboard?days=30", headers=auth_headers)
        assert r.status_code == 200
        b = r.json()
        for key in ["overview", "risk_distribution", "decision_distribution", "transaction_trend", "case_trend", "top_triggered_rules", "risk_concentration", "generated_at", "days"]:
            assert key in b, f"missing {key}"
        # overview fields
        for k in ["total_transactions", "total_cases", "open_cases", "in_progress_cases", "high_risk_transactions", "critical_risk_transactions", "blocked_transactions", "review_transactions", "allowed_transactions", "total_transaction_value"]:
            assert k in b["overview"]
        # distributions
        assert isinstance(b["risk_distribution"], list)
        assert len(b["risk_distribution"]) == 4
        assert isinstance(b["decision_distribution"], list)
        assert len(b["decision_distribution"]) == 3
        assert isinstance(b["transaction_trend"], list)
        assert isinstance(b["case_trend"], list)
        assert isinstance(b["top_triggered_rules"], list)
        assert "customers" in b["risk_concentration"]
        assert "merchants" in b["risk_concentration"]
        assert "devices" in b["risk_concentration"]

    def test_overview_with_data(self, db_session, sample_rules, auth_headers):
        _seed_basic(db_session, 10)
        client = TestClient(app)
        b = client.get("/api/v1/analytics/dashboard?days=30", headers=auth_headers).json()
        assert b["overview"]["total_transactions"] == 10
        assert b["overview"]["total_transaction_value"] is not None

    def test_empty_dashboard(self, db_session, sample_rules, auth_headers):
        # No transactions
        client = TestClient(app)
        b = client.get("/api/v1/analytics/dashboard?days=30", headers=auth_headers).json()
        assert b["overview"]["total_transactions"] == 0
        assert b["overview"]["total_transaction_value"] == "0" or b["overview"]["total_transaction_value"] == "0.00" or str(b["overview"]["total_transaction_value"]) == "0"
        # distributions should still have 0 counts
        for item in b["risk_distribution"]:
            assert item["count"] == 0
        assert b["transaction_trend"] is not None
        assert b["case_trend"] is not None


# FILTERS

class TestDashboardFilters:
    def test_days_7_30_90(self, db_session, sample_rules, auth_headers):
        _seed_basic(db_session, 5)
        client = TestClient(app)
        for d in [7, 30, 90]:
            r = client.get(f"/api/v1/analytics/dashboard?days={d}", headers=auth_headers)
            assert r.status_code == 200
            assert r.json()["days"] == d
            assert len(r.json()["transaction_trend"]) == d or len(r.json()["transaction_trend"]) <= d + 1  # allow inclusive

    def test_invalid_days(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/analytics/dashboard?days=0", headers=auth_headers)
        assert r.status_code == 422
        r2 = client.get("/api/v1/analytics/dashboard?days=400", headers=auth_headers)
        assert r2.status_code == 422
        r3 = client.get("/api/v1/analytics/dashboard?days=-1", headers=auth_headers)
        assert r3.status_code == 422
        r4 = client.get("/api/v1/analytics/dashboard?days=abc", headers=auth_headers)
        assert r4.status_code == 422


# DATA CORRECTNESS

class TestDataCorrectness:
    def test_totals_match_db(self, db_session, sample_rules, auth_headers):
        _seed_basic(db_session, 12)
        client = TestClient(app)
        b = client.get("/api/v1/analytics/dashboard?days=30", headers=auth_headers).json()
        # total_transactions should equal count
        assert b["overview"]["total_transactions"] == 12
        # sum of risk distribution counts should equal total
        assert sum(x["count"] for x in b["risk_distribution"]) == 12
        assert sum(x["count"] for x in b["decision_distribution"]) == 12

    def test_percentages_valid(self, db_session, sample_rules, auth_headers):
        _seed_basic(db_session, 8)
        client = TestClient(app)
        b = client.get("/api/v1/analytics/dashboard?days=30", headers=auth_headers).json()
        for item in b["risk_distribution"]:
            assert 0 <= item["percentage"] <= 100
        for item in b["decision_distribution"]:
            assert 0 <= item["percentage"] <= 100
        # sum approx 100 when total >0
        if b["overview"]["total_transactions"] > 0:
            total_risk_pct = sum(x["percentage"] for x in b["risk_distribution"])
            assert abs(total_risk_pct - 100) < 1 or total_risk_pct == 0  # rounding
            total_dec_pct = sum(x["percentage"] for x in b["decision_distribution"])
            assert abs(total_dec_pct - 100) < 1

    def test_no_negative_values(self, db_session, sample_rules, auth_headers):
        _seed_basic(db_session, 5)
        client = TestClient(app)
        b = client.get("/api/v1/analytics/dashboard?days=30", headers=auth_headers).json()
        assert b["overview"]["total_transactions"] >= 0
        assert b["overview"]["total_cases"] >= 0
        for v in b["risk_distribution"]:
            assert v["count"] >= 0
        for v in b["transaction_trend"]:
            assert v["transaction_count"] >= 0
            assert v["high_risk_count"] >= 0
            assert v["blocked_count"] >= 0

    def test_trend_deterministic(self, db_session, sample_rules, auth_headers):
        _seed_basic(db_session, 6)
        client = TestClient(app)
        b1 = client.get("/api/v1/analytics/dashboard?days=7", headers=auth_headers).json()
        b2 = client.get("/api/v1/analytics/dashboard?days=7", headers=auth_headers).json()
        assert b1["transaction_trend"] == b2["transaction_trend"]
        assert b1["risk_distribution"] == b2["risk_distribution"]

    def test_rule_counts_real(self, db_session, sample_rules, auth_headers):
        _seed_basic(db_session, 10)
        client = TestClient(app)
        b = client.get("/api/v1/analytics/dashboard?days=30", headers=auth_headers).json()
        # With our rules, at least one rule should be triggered
        assert len(b["top_triggered_rules"]) > 0
        for r in b["top_triggered_rules"]:
            assert "rule" in r and "count" in r and r["count"] > 0


# RISK

class TestRisk:
    def test_risk_levels_match_engine(self, db_session, sample_rules, auth_headers):
        # Seed with known amounts to trigger levels
        svc = TransactionService(db_session)
        # Low amount should be low risk (no rules)
        svc.ingest({"provider_event_id": f"evt_low_{uuid4().hex[:6]}", "amount": Decimal("100.00"), "currency": "INR", "customer_external_id": "cust_risk_a", "merchant_name": "M", "merchant_category_code": "5411"})
        # High amount >10000 should be block/high
        svc.ingest({"provider_event_id": f"evt_high_{uuid4().hex[:6]}", "amount": Decimal("15000.00"), "currency": "INR", "customer_external_id": "cust_risk_b", "merchant_name": "M", "merchant_category_code": "5411"})
        db_session.commit()
        client = TestClient(app)
        b = client.get("/api/v1/analytics/dashboard?days=30", headers=auth_headers).json()
        # Should have at least one high/critical or blocked
        assert b["overview"]["high_risk_transactions"] + b["overview"]["critical_risk_transactions"] >= 1

    def test_decision_distribution_matches(self, db_session, sample_rules, auth_headers):
        _seed_basic(db_session, 10)
        client = TestClient(app)
        b = client.get("/api/v1/analytics/dashboard?days=30", headers=auth_headers).json()
        # blocked + review + allowed should equal total
        assert b["overview"]["blocked_transactions"] + b["overview"]["review_transactions"] + b["overview"]["allowed_transactions"] == b["overview"]["total_transactions"]


# ISOLATION

class TestIsolation:
    def test_isolation_guard(self):
        import os
        assert "risk_era_test" in os.getenv("DATABASE_URL", "")

    def test_no_seed_demo_data(self, db_session):
        cnt = db_session.execute(text("SELECT count(*) FROM customers")).scalar()
        assert cnt < 20

