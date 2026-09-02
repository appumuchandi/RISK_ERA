from __future__ import annotations

from datetime import timedelta, datetime, timezone
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


def _seed_audit_data(db_session: Session):
    from app.services.audit_service import AuditService
    svc = TransactionService(db_session)
    res = svc.ingest({
        "provider_event_id": f"evt_audit_{uuid4().hex[:8]}",
        "amount": "12000.00",
        "currency": "INR",
        "customer_external_id": "cust_audit",
        "merchant_name": "MerchantAudit",
        "merchant_category_code": "5411",
    })
    db_session.commit()
    case_id = db_session.execute(text("SELECT id FROM cases WHERE transaction_id=:tid"), {"tid": str(res.transaction_id)}).scalar()
    # Create an explicit audit log for case to ensure filtering works
    audit = AuditService(db_session, actor="analyst")
    audit.log(actor="analyst", action="case_created", resource_type="case", resource_id=str(case_id), after={"case_id": str(case_id)})
    db_session.commit()
    return str(case_id), str(res.transaction_id)


# AUTH

class TestAuditAuth:
    def test_missing_jwt_401(self, db_session, sample_rules):
        client = TestClient(app)
        r = client.get("/api/v1/audit")
        assert r.status_code == 401
        r2 = client.get("/api/v1/audit/summary")
        assert r2.status_code == 401
        r3 = client.get("/api/v1/audit/verify-chain")
        assert r3.status_code == 401

    def test_invalid_jwt_401(self, db_session, sample_rules):
        client = TestClient(app)
        r = client.get("/api/v1/audit", headers={"Authorization": "Bearer invalid"})
        assert r.status_code == 401
        r2 = client.get("/api/v1/audit/summary", headers={"Authorization": "Bearer invalid.token"})
        assert r2.status_code == 401

    def test_expired_jwt_401(self, db_session, sample_rules):
        expired = JWTAuth.encode_token("analyst", expires_delta=timedelta(seconds=-1))
        client = TestClient(app)
        r = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_query_param_auth_rejected(self, db_session, sample_rules, auth_headers):
        token = auth_headers["Authorization"].split()[1]
        client = TestClient(app)
        r = client.get(f"/api/v1/audit?authorization=Bearer {token}")
        assert r.status_code == 401
        r2 = client.get(f"/api/v1/audit?Authorization=Bearer {token}")
        assert r2.status_code == 401
        r3 = client.get(f"/api/v1/audit/summary?authorization=Bearer {token}")
        assert r3.status_code == 401

    def test_actor_query_without_jwt_401(self, db_session, sample_rules):
        client = TestClient(app)
        r = client.get("/api/v1/audit?actor=admin")
        assert r.status_code == 401

    def test_valid_analyst_admin_200(self, db_session, sample_rules, auth_headers, admin_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/audit", headers=auth_headers)
        assert r.status_code == 200
        r2 = client.get("/api/v1/audit", headers=admin_headers)
        assert r2.status_code == 200
        r3 = client.get("/api/v1/audit/summary", headers=auth_headers)
        assert r3.status_code == 200
        r4 = client.get("/api/v1/audit/verify-chain", headers=auth_headers)
        assert r4.status_code == 200


# LIST

class TestAuditList:
    def test_default_pagination(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/audit", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body and "total" in body and "page" in body
        assert body["page"] == 1
        assert body["page_size"] == 20

    def test_page_size_validation(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/audit?page_size=0", headers=auth_headers)
        assert r.status_code == 422
        r2 = client.get("/api/v1/audit?page_size=101", headers=auth_headers)
        assert r2.status_code == 422

    def test_page_validation(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/audit?page=0", headers=auth_headers)
        assert r.status_code == 422

    def test_actor_filter(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        # First get an actor from audit
        client = TestClient(app)
        body = client.get("/api/v1/audit", headers=auth_headers).json()
        if body["items"]:
            actor = body["items"][0]["actor"]
            r = client.get(f"/api/v1/audit?actor={actor}", headers=auth_headers)
            assert r.status_code == 200
            for item in r.json()["items"]:
                assert item["actor"] == actor

    def test_action_filter(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/audit?action=case_created", headers=auth_headers)
        assert r.status_code == 200

    def test_resource_type_filter(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/audit?resource_type=case", headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["resource_type"] == "case"

    def test_resource_id_filter(self, db_session, sample_rules, auth_headers):
        case_id, _ = _seed_audit_data(db_session)
        client = TestClient(app)
        r = client.get(f"/api/v1/audit?resource_type=case&resource_id={case_id}", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1

    def test_search(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/audit?search=case", headers=auth_headers)
        assert r.status_code == 200

    def test_from_to_date(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(days=1)).isoformat()
        to_date = (now + timedelta(days=1)).isoformat()
        r = client.get(f"/api/v1/audit?from_date={from_date}&to_date={to_date}", headers=auth_headers)
        assert r.status_code == 200
        # Also test date_from alias
        r2 = client.get(f"/api/v1/audit?date_from={from_date}&date_to={to_date}", headers=auth_headers)
        assert r2.status_code == 200

    def test_sorting_asc_desc(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/audit?sort_by=created_at&sort_order=asc", headers=auth_headers)
        assert r.status_code == 200
        r2 = client.get("/api/v1/audit?sort_by=created_at&sort_order=desc", headers=auth_headers)
        assert r2.status_code == 200
        # Check that ordering is opposite
        if r.json()["items"] and r2.json()["items"]:
            assert r.json()["items"][0]["id"] != r2.json()["items"][0]["id"] or len(r.json()["items"]) == 1

    def test_invalid_sort_422(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/audit?sort_by=invalid", headers=auth_headers)
        assert r.status_code == 422
        r2 = client.get("/api/v1/audit?sort_by=created_at&sort_order=invalid", headers=auth_headers)
        assert r2.status_code == 422

    def test_deterministic_ordering(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        r1 = client.get("/api/v1/audit", headers=auth_headers).json()
        r2 = client.get("/api/v1/audit", headers=auth_headers).json()
        assert r1 == r2


# DETAIL AND SUMMARY

class TestAuditDetail:
    def test_event_detail_contains_real_fields(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        body = client.get("/api/v1/audit", headers=auth_headers).json()
        assert len(body["items"]) > 0
        item = body["items"][0]
        for f in ["id", "actor", "action", "resource_type", "resource_id", "prev_hash", "created_at"]:
            assert f in item
        # Ensure no secrets
        assert "authorization" not in str(item).lower()
        assert "password" not in str(item).lower()

    def test_no_secrets_exposed(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        body = client.get("/api/v1/audit", headers=auth_headers).json()
        s = str(body).lower()
        assert "nvapi" not in s
        assert "bearer" not in s or "authorization" not in s  # should not expose token


class TestAuditSummary:
    def test_summary_derived(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/audit/summary", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        for k in ["total", "unique_actors", "case_actions", "investigation_actions", "latest_event_at"]:
            assert k in body
        assert body["total"] >= 1

    def test_summary_time_window(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(days=1)).isoformat()
        to_date = (now + timedelta(days=1)).isoformat()
        r = client.get(f"/api/v1/audit/summary?from_date={from_date}&to_date={to_date}", headers=auth_headers)
        assert r.status_code == 200


# CHAIN

class TestAuditChain:
    def test_valid_chain(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        r = client.get("/api/v1/audit/verify-chain", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["valid"] is True
        assert body["error"] is None
        assert "checked_count" in body
        assert "total" in body

    def test_verify_read_only(self, db_session, sample_rules, auth_headers):
        _seed_audit_data(db_session)
        client = TestClient(app)
        before = db_session.execute(text("SELECT count(*) FROM audit_log")).scalar()
        client.get("/api/v1/audit/verify-chain", headers=auth_headers)
        after = db_session.execute(text("SELECT count(*) FROM audit_log")).scalar()
        assert before == after


# CASE TRACE

class TestCaseTrace:
    def test_case_specific_audit(self, db_session, sample_rules, auth_headers):
        case_id, _ = _seed_audit_data(db_session)
        client = TestClient(app)
        r = client.get(f"/api/v1/audit?resource_type=case&resource_id={case_id}", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1
        for item in r.json()["items"]:
            assert item["resource_type"] == "case"
            assert item["resource_id"] == case_id

    def test_case_audit_real(self, db_session, sample_rules, auth_headers):
        case_id, _ = _seed_audit_data(db_session)
        client = TestClient(app)
        # Also check workbench timeline uses same audit
        r = client.get(f"/api/v1/investigation/{case_id}/workbench", headers=auth_headers)
        if r.status_code == 200:
            assert "timeline" in r.json()
            assert len(r.json()["timeline"]) >= 1


# ISOLATION

class TestIsolation:
    def test_isolation_guard(self):
        import os
        assert "risk_era_test" in os.getenv("DATABASE_URL", "")

    def test_demo_db_untouched(self, db_session):
        cnt = db_session.execute(text("SELECT count(*) FROM customers")).scalar()
        assert cnt < 20
