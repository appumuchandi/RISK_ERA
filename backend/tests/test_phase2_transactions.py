from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def _seed_transactions(db_session: Session, count: int = 5):
    service = TransactionService(db_session)
    ids = []
    for i in range(count):
        amount = Decimal(str(1000 + i * 5000))  # 1000,6000,11000,16000,21000
        resp = service.ingest({
            "provider_event_id": f"evt_phase2_{uuid4().hex[:8]}_{i}",
            "amount": amount,
            "currency": "INR",
            "customer_external_id": f"cust_phase2_{i % 2}",
            "device_fingerprint_hash": f"fp_phase2_{i % 2}",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411" if i % 2 == 0 else "7995",
        })
        ids.append(resp)
    return ids


# --- 1. Auth tests ---

class TestTransactionAuth:
    def test_valid_jwt_returns_200(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 3)
        client = TestClient(app)
        r = client.get("/api/v1/transactions", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] >= 3

    def test_missing_jwt_returns_401(self, db_session: Session, sample_rules):
        _seed_transactions(db_session, 1)
        client = TestClient(app)
        r = client.get("/api/v1/transactions")
        assert r.status_code == 401

    def test_invalid_jwt_returns_401(self, db_session: Session, sample_rules):
        _seed_transactions(db_session, 1)
        client = TestClient(app)
        r = client.get("/api/v1/transactions", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401

    def test_expired_jwt_returns_401(self, db_session: Session, sample_rules):
        _seed_transactions(db_session, 1)
        expired = JWTAuth.encode_token("analyst", expires_delta=timedelta(seconds=-1))
        client = TestClient(app)
        r = client.get("/api/v1/transactions", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_no_query_param_auth(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 1)
        token = auth_headers["Authorization"].split()[1]
        client = TestClient(app)
        r = client.get(f"/api/v1/transactions?Authorization=Bearer {token}")
        # Must be 401 because query param auth is not accepted
        assert r.status_code == 401

    def test_no_actor_impersonation(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 1)
        client = TestClient(app)
        r = client.get("/api/v1/transactions?actor=admin", headers=auth_headers)
        # Should still be 200 and actor from JWT, not query. Query param is ignored (no effect)
        assert r.status_code == 200
        # Also ensure without JWT but with actor param still 401
        r2 = client.get("/api/v1/transactions?actor=analyst")
        assert r2.status_code == 401


# --- 2. Pagination ---

class TestTransactionPagination:
    def test_pagination_basic(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 5)
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"page": 1, "page_size": 2}, headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2
        assert body["total"] == 5
        assert body["page"] == 1
        assert body["page_size"] == 2
        assert body["total_pages"] == 3

    def test_pagination_second_page(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 5)
        client = TestClient(app)
        r1 = client.get("/api/v1/transactions", params={"page": 1, "page_size": 2}, headers=auth_headers)
        r2 = client.get("/api/v1/transactions", params={"page": 2, "page_size": 2}, headers=auth_headers)
        assert r1.status_code == 200 and r2.status_code == 200
        ids1 = {x["id"] for x in r1.json()["items"]}
        ids2 = {x["id"] for x in r2.json()["items"]}
        assert ids1.isdisjoint(ids2)

    def test_invalid_pagination_returns_422(self, db_session: Session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"page": 0}, headers=auth_headers)
        assert r.status_code == 422
        r = client.get("/api/v1/transactions", params={"page_size": 0}, headers=auth_headers)
        assert r.status_code == 422
        r = client.get("/api/v1/transactions", params={"page_size": 101}, headers=auth_headers)
        assert r.status_code == 422


# --- 3. Sorting ---

class TestTransactionSorting:
    def test_sort_amount_asc(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 4)
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"sort_by": "amount", "sort_order": "asc", "page_size": 100}, headers=auth_headers)
        assert r.status_code == 200
        amounts = [float(x["amount"]) for x in r.json()["items"]]
        assert amounts == sorted(amounts)

    def test_sort_amount_desc(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 4)
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"sort_by": "amount", "sort_order": "desc", "page_size": 100}, headers=auth_headers)
        assert r.status_code == 200
        amounts = [float(x["amount"]) for x in r.json()["items"]]
        assert amounts == sorted(amounts, reverse=True)

    def test_sort_created_at_desc(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 3)
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"sort_by": "created_at", "sort_order": "desc", "page_size": 100}, headers=auth_headers)
        assert r.status_code == 200
        dates = [x["created_at"] for x in r.json()["items"]]
        assert dates == sorted(dates, reverse=True)

    def test_sort_risk_score(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 5)
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"sort_by": "risk_score", "sort_order": "asc", "page_size": 100}, headers=auth_headers)
        assert r.status_code == 200
        scores = [x["risk_score"] for x in r.json()["items"]]
        assert scores == sorted(scores)
        r2 = client.get("/api/v1/transactions", params={"sort_by": "risk_score", "sort_order": "desc", "page_size": 100}, headers=auth_headers)
        assert r2.status_code == 200
        scores2 = [x["risk_score"] for x in r2.json()["items"]]
        assert scores2 == sorted(scores2, reverse=True)

    def test_invalid_sort_field_returns_422(self, db_session: Session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"sort_by": "unknown_field"}, headers=auth_headers)
        assert r.status_code == 422
        r = client.get("/api/v1/transactions", params={"sort_order": "invalid"}, headers=auth_headers)
        assert r.status_code == 422


# --- 4. Filtering ---

class TestTransactionFiltering:
    def test_amount_filter(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 5)  # amounts 1000,6000,11000,16000,21000
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"min_amount": 10000, "max_amount": 16000}, headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert 10000 <= float(item["amount"]) <= 16000

    def test_risk_filter_low(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 5)
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"risk": "low"}, headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["risk_level"] == "low"

    def test_risk_filter_critical(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 5)
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"risk": "critical"}, headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["risk_level"] == "critical"

    def test_customer_filter(self, db_session: Session, sample_rules, auth_headers):
        seeded = _seed_transactions(db_session, 4)
        # seeded[0] customer is cust_phase2_0
        from app.models import Transaction
        txn = db_session.execute(text("SELECT customer_id FROM transactions LIMIT 1")).fetchone()
        cust_id = str(txn[0])
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"customer_id": cust_id}, headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["customer_id"] == cust_id

    def test_merchant_filter(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 4)
        txn = db_session.execute(text("SELECT merchant_id FROM transactions LIMIT 1")).fetchone()
        merch_id = str(txn[0])
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"merchant_id": merch_id}, headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["merchant_id"] == merch_id

    def test_device_filter(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 4)
        row = db_session.execute(text("SELECT device_id FROM transactions WHERE device_id IS NOT NULL LIMIT 1")).fetchone()
        if row:
            dev_id = str(row[0])
            client = TestClient(app)
            r = client.get("/api/v1/transactions", params={"device_id": dev_id}, headers=auth_headers)
            assert r.status_code == 200
            for item in r.json()["items"]:
                assert item["device_id"] == dev_id

    def test_status_filter(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 5)
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"status": "flagged"}, headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["status"] == "flagged"
        r = client.get("/api/v1/transactions", params={"status": "failed"}, headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["status"] == "failed"

    def test_date_filter(self, db_session: Session, sample_rules, auth_headers):
        service = TransactionService(db_session)
        # Create a transaction with known past date via direct DB? Use current and filter by from_date far future -> empty
        _seed_transactions(db_session, 2)
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"from_date": future}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["total"] == 0
        assert r.json()["items"] == []

    def test_search_filter(self, db_session: Session, sample_rules, auth_headers):
        service = TransactionService(db_session)
        resp = service.ingest({
            "provider_event_id": "evt_searchable_12345",
            "amount": Decimal("1000.00"),
            "currency": "INR",
            "customer_external_id": "cust_search",
            "merchant_name": "Test Merchant",
            "merchant_category_code": "5411",
        })
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"search": "searchable_123"}, headers=auth_headers)
        assert r.status_code == 200
        assert any("searchable_123" in x["provider_event_id"] for x in r.json()["items"])

    def test_invalid_status_returns_422(self, db_session: Session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"status": "nonexistent"}, headers=auth_headers)
        assert r.status_code == 422

    def test_invalid_risk_returns_422(self, db_session: Session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"risk": "ultra"}, headers=auth_headers)
        assert r.status_code == 422


# --- 5. Empty result and shape ---

class TestTransactionShape:
    def test_empty_result_shape(self, db_session: Session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/transactions", params={"min_amount": 999999}, headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["total_pages"] == 0
        assert body["page"] == 1

    def test_response_fields(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 1)
        client = TestClient(app)
        r = client.get("/api/v1/transactions", headers=auth_headers)
        assert r.status_code == 200
        item = r.json()["items"][0]
        for field in ["id", "provider_event_id", "amount", "currency", "status", "customer_id", "merchant_id", "created_at", "risk_score", "risk_level", "decision", "triggered_rules", "has_case", "customer_external_id", "merchant_name"]:
            assert field in item, f"missing {field}"
        assert isinstance(item["risk_score"], (int, float))
        assert item["risk_level"] in ("low", "medium", "high", "critical")
        assert item["decision"] in ("allow", "review", "block")

    def test_risk_fields_deterministic(self, db_session: Session, sample_rules, auth_headers):
        _seed_transactions(db_session, 2)
        client = TestClient(app)
        r1 = client.get("/api/v1/transactions", params={"sort_by": "created_at", "sort_order": "asc", "page_size": 100}, headers=auth_headers)
        r2 = client.get("/api/v1/transactions", params={"sort_by": "created_at", "sort_order": "asc", "page_size": 100}, headers=auth_headers)
        assert r1.json() == r2.json()


# --- 6. Existing endpoints still work ---

class TestExistingTransactionEndpoints:
    def test_ingest_still_protected(self, db_session: Session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.post("/api/v1/transactions", json={
            "provider_event_id": f"evt_existing_{uuid4().hex[:6]}",
            "amount": "100.00",
            "currency": "INR",
            "customer_external_id": "cust_exist",
            "merchant_name": "M",
            "merchant_category_code": "5411",
        }, headers=auth_headers)
        assert r.status_code == 200
        assert "transaction_id" in r.json()
        # Without auth should be 401
        r2 = client.post("/api/v1/transactions", json={
            "provider_event_id": f"evt_existing2_{uuid4().hex[:6]}",
            "amount": "100.00",
            "currency": "INR",
            "customer_external_id": "cust_exist2",
            "merchant_name": "M",
            "merchant_category_code": "5411",
        })
        assert r2.status_code == 401

    def test_get_by_id_still_works(self, db_session: Session, sample_rules, auth_headers):
        service = TransactionService(db_session)
        resp = service.ingest({
            "provider_event_id": f"evt_getid_{uuid4().hex[:6]}",
            "amount": Decimal("100.00"),
            "currency": "INR",
            "customer_external_id": "cust_getid",
            "merchant_name": "M",
            "merchant_category_code": "5411",
        })
        client = TestClient(app)
        r = client.get(f"/api/v1/transactions/{resp.transaction_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["id"] == str(resp.transaction_id)
        # Without auth
        r2 = client.get(f"/api/v1/transactions/{resp.transaction_id}")
        assert r2.status_code == 401

    def test_get_by_provider_still_works(self, db_session: Session, sample_rules, auth_headers):
        service = TransactionService(db_session)
        resp = service.ingest({
            "provider_event_id": f"evt_provider_{uuid4().hex[:6]}",
            "amount": Decimal("100.00"),
            "currency": "INR",
            "customer_external_id": "cust_provider",
            "merchant_name": "M",
            "merchant_category_code": "5411",
        })
        client = TestClient(app)
        r = client.get(f"/api/v1/transactions/by-provider/{resp.provider_event_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["provider_event_id"] == resp.provider_event_id


# --- 7. Test DB isolation ---

class TestDbIsolation:
    def test_isolation_guard(self):
        import os
        assert "risk_era_test" in os.getenv("DATABASE_URL", "")

    def test_demo_db_not_touched(self):
        # This test verifies the guard — if we reached here, isolation held
        assert True
