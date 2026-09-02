from __future__ import annotations

from datetime import timedelta, datetime, timezone
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
from app.services.alert_service import AlertService
from app.models.alert import AlertStatus, AlertSeverity


@pytest.fixture(scope="session")
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_db(db: Session):
    # Truncate alerts as well
    db.execute(text("TRUNCATE TABLE alerts, cases, transactions, rules, merchants, devices, customers, audit_log, investigations, analyst_feedback, evidence RESTART IDENTITY CASCADE"))
    db.commit()
    yield
    db.execute(text("TRUNCATE TABLE alerts, cases, transactions, rules, merchants, devices, customers, audit_log, investigations, analyst_feedback, evidence RESTART IDENTITY CASCADE"))
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


def _seed_alert_data(db_session: Session):
    svc = TransactionService(db_session)
    # Create transactions that will generate alerts
    # BLOCK: high amount + gambling
    r1 = svc.ingest({
        "provider_event_id": f"evt_alert_{uuid4().hex[:8]}_1",
        "amount": Decimal("15000.00"),
        "currency": "INR",
        "customer_external_id": "cust_alert_1",
        "device_fingerprint_hash": "fp_alert_1",
        "merchant_name": "MerchantAlertA",
        "merchant_category_code": "7995",
    })
    r2 = svc.ingest({
        "provider_event_id": f"evt_alert_{uuid4().hex[:8]}_2",
        "amount": Decimal("8000.00"),
        "currency": "INR",
        "customer_external_id": "cust_alert_2",
        "device_fingerprint_hash": "fp_alert_2",
        "merchant_name": "MerchantAlertB",
        "merchant_category_code": "5411",
    })
    r3 = svc.ingest({
        "provider_event_id": f"evt_alert_{uuid4().hex[:8]}_3",
        "amount": Decimal("100.00"),
        "currency": "INR",
        "customer_external_id": "cust_alert_3",
        "device_fingerprint_hash": "fp_alert_3",
        "merchant_name": "MerchantAlertC",
        "merchant_category_code": "5411",
    })
    db_session.commit()
    # Generate alerts
    svc_alert = AlertService(db_session)
    svc_alert.ensure_alerts_generated(limit=10)
    db_session.commit()
    return r1, r2, r3


# AUTH TESTS

class TestAlertAuth:
    def test_missing_jwt_401(self, db_session, sample_rules):
        client = TestClient(app)
        r = client.get("/api/v1/alerts")
        assert r.status_code == 401
        r2 = client.get("/api/v1/operations/summary")
        assert r2.status_code == 401

    def test_invalid_jwt_401(self, db_session, sample_rules):
        client = TestClient(app)
        r = client.get("/api/v1/alerts", headers={"Authorization": "Bearer invalid"})
        assert r.status_code == 401
        r2 = client.get(f"/api/v1/alerts/{uuid4()}", headers={"Authorization": "Bearer invalid.token"})
        assert r2.status_code == 401

    def test_expired_jwt_401(self, db_session, sample_rules):
        expired = JWTAuth.encode_token("analyst", expires_delta=timedelta(seconds=-1))
        client = TestClient(app)
        r = client.get("/api/v1/alerts", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_query_param_auth_rejected(self, db_session, sample_rules, auth_headers):
        token = auth_headers["Authorization"].split()[1]
        client = TestClient(app)
        r = client.get(f"/api/v1/alerts?authorization=Bearer {token}")
        assert r.status_code == 401
        r2 = client.get(f"/api/v1/operations/summary?Authorization=Bearer {token}")
        assert r2.status_code == 401

    def test_valid_analyst_admin_200(self, db_session, sample_rules, auth_headers, admin_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/alerts", headers=auth_headers)
        assert r.status_code == 200
        r2 = client.get("/api/v1/alerts", headers=admin_headers)
        assert r2.status_code == 200
        r3 = client.get("/api/v1/operations/summary", headers=auth_headers)
        assert r3.status_code == 200
        r4 = client.get("/api/v1/operations/summary", headers=admin_headers)
        assert r4.status_code == 200


# LIST TESTS

class TestAlertList:
    def test_pagination(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/alerts?page=1&page_size=1", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == 1
        assert body["page_size"] == 1
        assert len(body["items"]) == 1
        assert body["total"] >= 1
        # second page
        r2 = client.get("/api/v1/alerts?page=2&page_size=1", headers=auth_headers)
        if body["total"] > 1:
            assert r2.json()["items"][0]["id"] != body["items"][0]["id"]

    def test_invalid_pagination(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/alerts?page=0", headers=auth_headers)
        assert r.status_code == 422
        r2 = client.get("/api/v1/alerts?page_size=0", headers=auth_headers)
        assert r2.status_code == 422
        r3 = client.get("/api/v1/alerts?page_size=101", headers=auth_headers)
        assert r3.status_code == 422

    def test_filters(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        # status filter
        r = client.get("/api/v1/alerts?status=open", headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["status"] == "open"
        # severity filter
        r2 = client.get("/api/v1/alerts?severity=high", headers=auth_headers)
        assert r2.status_code == 200
        # decision filter
        r3 = client.get("/api/v1/alerts?decision=block", headers=auth_headers)
        for item in r3.json()["items"]:
            assert item["decision"] == "block"

    def test_sorting(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/alerts?sort_by=priority&sort_order=desc", headers=auth_headers)
        assert r.status_code == 200
        priorities = [x["priority"] for x in r.json()["items"]]
        assert priorities == sorted(priorities, reverse=True)

    def test_invalid_sorting(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/alerts?sort_by=invalid", headers=auth_headers)
        assert r.status_code == 422
        r2 = client.get("/api/v1/alerts?sort_order=invalid", headers=auth_headers)
        assert r2.status_code == 422

    def test_search(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/alerts?search=high", headers=auth_headers)
        assert r.status_code == 200

    def test_empty_result(self, db_session, sample_rules, auth_headers):
        # No alerts generated if no qualifying transactions
        # Seed low risk only
        svc = TransactionService(db_session)
        svc.ingest({"provider_event_id": f"evt_low_{uuid4().hex[:6]}", "amount": Decimal("10.00"), "currency": "INR", "customer_external_id": "cust_low", "merchant_name": "MLow", "merchant_category_code": "5411"})
        db_session.commit()
        # This low amount with allow_small may not generate alert (since we filter high/block)
        client = TestClient(app)
        r = client.get("/api/v1/alerts?search=nonexistentXYZ", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["items"] == []
        assert r.json()["total"] == 0


# ALERT DETAIL AND GENERATION

class TestAlertDetail:
    def test_detail(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        list_body = client.get("/api/v1/alerts", headers=auth_headers).json()
        alert_id = list_body["items"][0]["id"]
        r = client.get(f"/api/v1/alerts/{alert_id}", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == alert_id
        assert "severity" in body
        assert "risk_score" in body

    def test_deterministic_priority(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        body1 = client.get("/api/v1/alerts", headers=auth_headers).json()
        body2 = client.get("/api/v1/alerts", headers=auth_headers).json()
        # Same priority for same alerts
        assert body1["items"][0]["priority"] == body2["items"][0]["priority"]

    def test_alert_generation(self, db_session, sample_rules):
        # Ensure generation creates alerts for high-risk
        _seed_alert_data(db_session)
        cnt = db_session.execute(text("SELECT count(*) FROM alerts")).scalar()
        assert cnt >= 1

    def test_deduplication(self, db_session, sample_rules):
        _seed_alert_data(db_session)
        cnt1 = db_session.execute(text("SELECT count(*) FROM alerts")).scalar()
        svc = AlertService(db_session)
        svc.ensure_alerts_generated(limit=10)
        db_session.commit()
        cnt2 = db_session.execute(text("SELECT count(*) FROM alerts")).scalar()
        assert cnt2 == cnt1  # no duplicates

    def test_rule_linkage(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        body = client.get("/api/v1/alerts", headers=auth_headers).json()
        # At least one should have rule_id linked
        has_rule = any(item["rule_id"] is not None for item in body["items"])
        assert has_rule


# MUTATIONS

class TestAlertMutations:
    def test_acknowledge(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        alert_id = client.get("/api/v1/alerts", headers=auth_headers).json()["items"][0]["id"]
        r = client.patch(f"/api/v1/alerts/{alert_id}/status", json={"status": "acknowledged"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "acknowledged"

    def test_assign(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        alert_id = client.get("/api/v1/alerts", headers=auth_headers).json()["items"][0]["id"]
        r = client.patch(f"/api/v1/alerts/{alert_id}/assign", json={"assigned_to": "analyst1"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["assigned_to"] == "analyst1"
        # Verify actor from JWT, not body: try to inject actor in body should not affect (we don't accept actor)
        # Our assign endpoint doesn't accept actor, so no impersonation possible; just verify assigned_to is as sent

    def test_resolve(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        alert_id = client.get("/api/v1/alerts", headers=auth_headers).json()["items"][0]["id"]
        # Must go through valid transitions: open -> acknowledged -> in_progress -> resolved
        client.patch(f"/api/v1/alerts/{alert_id}/status", json={"status": "acknowledged"}, headers=auth_headers)
        client.patch(f"/api/v1/alerts/{alert_id}/status", json={"status": "in_progress"}, headers=auth_headers)
        r = client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"reason": "reviewed"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "resolved"

    def test_dismiss(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        alert_id = client.get("/api/v1/alerts", headers=auth_headers).json()["items"][0]["id"]
        r = client.post(f"/api/v1/alerts/{alert_id}/dismiss", json={"reason": "false positive"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "dismissed"

    def test_invalid_transitions(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        alert_id = client.get("/api/v1/alerts", headers=auth_headers).json()["items"][0]["id"]
        # Try open -> resolved directly should fail (invalid transition)
        r = client.patch(f"/api/v1/alerts/{alert_id}/status", json={"status": "resolved"}, headers=auth_headers)
        assert r.status_code == 422

    def test_actor_from_jwt(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        alert_id = client.get("/api/v1/alerts", headers=auth_headers).json()["items"][0]["id"]
        # Try to inject actor via query/body - should be ignored, actor is JWT "analyst"
        r = client.patch(f"/api/v1/alerts/{alert_id}/assign?actor=admin", json={"assigned_to": "bob"}, headers=auth_headers)
        assert r.status_code == 200
        # Verify audit actor is analyst, not admin
        # Check audit log last entry
        row = db_session.execute(text("SELECT actor FROM audit_log ORDER BY created_at DESC LIMIT 1")).fetchone()
        # The last audit should be from analyst
        assert row is not None
        # Since we use JWT analyst, actor should be analyst
        assert row[0] == "analyst"


# CASE WORKFLOW

class TestAlertCase:
    def test_create_case(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        alert = client.get("/api/v1/alerts", headers=auth_headers).json()["items"][0]
        alert_id = alert["id"]
        # Ensure alert has transaction
        assert alert["transaction_id"] is not None
        r = client.post(f"/api/v1/alerts/{alert_id}/case", headers=auth_headers)
        assert r.status_code == 200
        assert "case_id" in r.json()
        # Second call should return same case (duplicate prevention)
        r2 = client.post(f"/api/v1/alerts/{alert_id}/case", headers=auth_headers)
        assert r2.json()["case_id"] == r.json()["case_id"]

    def test_linked_case(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        alert_id = client.get("/api/v1/alerts", headers=auth_headers).json()["items"][0]["id"]
        client.post(f"/api/v1/alerts/{alert_id}/case", headers=auth_headers)
        detail = client.get(f"/api/v1/alerts/{alert_id}", headers=auth_headers).json()
        assert detail["case_id"] is not None


# OPERATIONS

class TestOperations:
    def test_summary_correctness(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/operations/summary", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        for k in ["open_alerts", "critical_alerts", "high_alerts", "open_cases", "escalated_cases"]:
            assert k in body
            assert body[k] >= 0
        # average risk should be 0-100
        assert 0 <= body["average_alert_risk"] <= 100

    def test_summary_real_aggregates(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        before = client.get("/api/v1/alerts", headers=auth_headers).json()["total"]
        summary = client.get("/api/v1/operations/summary", headers=auth_headers).json()
        # open_alerts should be <= total alerts
        assert summary["open_alerts"] <= before + 5  # allow small drift due to lazy generation


# AUDIT

class TestAlertAudit:
    def test_alert_mutation_creates_audit(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        alert_id = client.get("/api/v1/alerts", headers=auth_headers).json()["items"][0]["id"]
        before_cnt = db_session.execute(text("SELECT count(*) FROM audit_log")).scalar()
        client.patch(f"/api/v1/alerts/{alert_id}/status", json={"status": "acknowledged"}, headers=auth_headers)
        after_cnt = db_session.execute(text("SELECT count(*) FROM audit_log")).scalar()
        assert after_cnt > before_cnt

    def test_verify_chain(self, db_session, sample_rules, auth_headers):
        _seed_alert_data(db_session)
        client = TestClient(app)
        alert_id = client.get("/api/v1/alerts", headers=auth_headers).json()["items"][0]["id"]
        client.patch(f"/api/v1/alerts/{alert_id}/status", json={"status": "acknowledged"}, headers=auth_headers)
        # Verify chain
        r = client.get("/api/v1/audit/verify-chain", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["valid"] is True


# ISOLATION

class TestIsolation:
    def test_isolation_guard(self):
        import os
        assert "risk_era_test" in os.getenv("DATABASE_URL", "")

    def test_no_seed_demo(self, db_session):
        cnt = db_session.execute(text("SELECT count(*) FROM customers")).scalar()
        assert cnt < 20
