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
        Rule(name="review_high_risk_customer", dsl_expression="customer_risk_tier == 'high'", action=ModelRuleAction.REVIEW, priority=75, enabled=True),
        Rule(name="block_gambling", dsl_expression="merchant_category_code == '7995'", action=ModelRuleAction.BLOCK, priority=95, enabled=True),
        Rule(name="allow_small", dsl_expression="amount < 500", action=ModelRuleAction.ALLOW, priority=10, enabled=True),
        Rule(name="disabled_rule", dsl_expression="amount > 1", action=ModelRuleAction.BLOCK, priority=5, enabled=False),
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


def _seed_txns(db_session: Session, n=3):
    svc = TransactionService(db_session)
    out = []
    for i in range(n):
        amt = Decimal(str([100, 6000, 15000][i % 3]))
        cat = "7995" if i == 2 else "5411"
        cust = "high" if i == 1 else "standard"
        # Need to set customer risk tier via direct DB after creation? Simpler to ingest then update customer
        res = svc.ingest({
            "provider_event_id": f"evt_r6_{uuid4().hex[:8]}_{i}",
            "amount": amt,
            "currency": "INR",
            "customer_external_id": f"cust_r6_{i}",
            "merchant_name": "TestM",
            "merchant_category_code": cat,
        })
        # Update customer risk tier if needed
        if cust == "high":
            db_session.execute(text("UPDATE customers SET risk_tier='high' WHERE external_id=:e"), {"e": f"cust_r6_{i}"})
            db_session.commit()
        out.append(res)
    return out


# RULE API AUTH

class TestRulesAuth:
    def test_missing_jwt_401(self, db_session, sample_rules):
        client = TestClient(app)
        r = client.get("/api/v1/rules")
        assert r.status_code == 401
        r2 = client.get("/api/v1/rules/00000000-0000-0000-0000-000000000000")
        assert r2.status_code == 401

    def test_invalid_jwt_401(self, db_session, sample_rules):
        client = TestClient(app)
        r = client.get("/api/v1/rules", headers={"Authorization": "Bearer invalid"})
        assert r.status_code == 401
        r2 = client.get(f"/api/v1/rules/{uuid4()}", headers={"Authorization": "Bearer invalid.token"})
        assert r2.status_code == 401

    def test_expired_jwt_401(self, db_session, sample_rules):
        expired = JWTAuth.encode_token("analyst", expires_delta=timedelta(seconds=-1))
        client = TestClient(app)
        r = client.get("/api/v1/rules", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_query_param_auth_rejected(self, db_session, sample_rules, auth_headers):
        token = auth_headers["Authorization"].split()[1]
        client = TestClient(app)
        r = client.get(f"/api/v1/rules?authorization=Bearer {token}")
        assert r.status_code == 401
        r2 = client.get(f"/api/v1/rules?Authorization=Bearer {token}")
        assert r2.status_code == 401

    def test_valid_jwt_200(self, db_session, sample_rules, auth_headers, admin_headers):
        client = TestClient(app)
        r = client.get("/api/v1/rules", headers=auth_headers)
        assert r.status_code == 200
        r2 = client.get("/api/v1/rules", headers=admin_headers)
        assert r2.status_code == 200
        # detail
        rule_id = db_session.execute(text("SELECT id FROM rules LIMIT 1")).scalar()
        r3 = client.get(f"/api/v1/rules/{rule_id}", headers=auth_headers)
        assert r3.status_code == 200


# RULES LIST BEHAVIOR

class TestRulesList:
    def test_pagination(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/rules?page=1&page_size=2", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == 1
        assert body["page_size"] == 2
        assert len(body["items"]) == 2
        assert body["total"] >= 5
        assert body["total_pages"] >= 3
        # page 2
        r2 = client.get("/api/v1/rules?page=2&page_size=2", headers=auth_headers)
        ids1 = {x["id"] for x in body["items"]}
        ids2 = {x["id"] for x in r2.json()["items"]}
        assert ids1.isdisjoint(ids2)

    def test_invalid_pagination(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/rules?page=0", headers=auth_headers)
        assert r.status_code == 422
        r2 = client.get("/api/v1/rules?page_size=0", headers=auth_headers)
        assert r2.status_code == 422
        r3 = client.get("/api/v1/rules?page_size=101", headers=auth_headers)
        assert r3.status_code == 422

    def test_action_filter(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/rules?action=BLOCK", headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["action"].lower() == "block"
        r2 = client.get("/api/v1/rules?action=REVIEW", headers=auth_headers)
        for item in r2.json()["items"]:
            assert item["action"].lower() == "review"

    def test_enabled_filter(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/rules?enabled=true", headers=auth_headers)
        for item in r.json()["items"]:
            assert item["enabled"] is True
        r2 = client.get("/api/v1/rules?enabled=false", headers=auth_headers)
        for item in r2.json()["items"]:
            assert item["enabled"] is False
        assert r2.json()["total"] == 1  # disabled_rule

    def test_search(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get("/api/v1/rules?search=high_amount", headers=auth_headers)
        assert r.status_code == 200
        assert any("high_amount" in x["name"] for x in r.json()["items"])

    def test_deterministic_ordering(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r1 = client.get("/api/v1/rules?page=1&page_size=10", headers=auth_headers).json()
        r2 = client.get("/api/v1/rules?page=1&page_size=10", headers=auth_headers).json()
        assert r1 == r2
        # Check ordering by priority asc then id
        priorities = [x["priority"] for x in r1["items"]]
        assert priorities == sorted(priorities)

    def test_rule_detail_404(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get(f"/api/v1/rules/{uuid4()}", headers=auth_headers)
        assert r.status_code == 404


# RISK EXPLANATION

class TestRiskExplain:
    def test_missing_jwt_401(self, db_session, sample_rules):
        _seed_txns(db_session, 1)
        txn_id = db_session.execute(text("SELECT id FROM transactions LIMIT 1")).scalar()
        client = TestClient(app)
        r = client.get(f"/api/v1/transactions/{txn_id}/risk-explain")
        assert r.status_code == 401

    def test_invalid_jwt_401(self, db_session, sample_rules):
        _seed_txns(db_session, 1)
        txn_id = db_session.execute(text("SELECT id FROM transactions LIMIT 1")).scalar()
        client = TestClient(app)
        r = client.get(f"/api/v1/transactions/{txn_id}/risk-explain", headers={"Authorization": "Bearer invalid"})
        assert r.status_code == 401

    def test_expired_jwt_401(self, db_session, sample_rules):
        _seed_txns(db_session, 1)
        txn_id = db_session.execute(text("SELECT id FROM transactions LIMIT 1")).scalar()
        expired = JWTAuth.encode_token("analyst", expires_delta=timedelta(seconds=-1))
        client = TestClient(app)
        r = client.get(f"/api/v1/transactions/{txn_id}/risk-explain", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_query_param_auth_rejected(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 1)
        txn_id = db_session.execute(text("SELECT id FROM transactions LIMIT 1")).scalar()
        token = auth_headers["Authorization"].split()[1]
        client = TestClient(app)
        r = client.get(f"/api/v1/transactions/{txn_id}/risk-explain?authorization=Bearer {token}")
        assert r.status_code == 401

    def test_actor_impersonation_rejected(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 1)
        txn_id = db_session.execute(text("SELECT id FROM transactions LIMIT 1")).scalar()
        client = TestClient(app)
        r = client.get(f"/api/v1/transactions/{txn_id}/risk-explain?actor=admin", headers=auth_headers)
        assert r.status_code == 200
        # without JWT, actor should not auth
        r2 = client.get(f"/api/v1/transactions/{txn_id}/risk-explain?actor=admin")
        assert r2.status_code == 401

    def test_unknown_transaction_404(self, db_session, sample_rules, auth_headers):
        client = TestClient(app)
        r = client.get(f"/api/v1/transactions/{uuid4()}/risk-explain", headers=auth_headers)
        assert r.status_code == 404

    def test_valid_explanation(self, db_session, sample_rules, auth_headers):
        res = _seed_txns(db_session, 3)
        txn_id = str(res[2].transaction_id)  # high amount + gambling -> block
        client = TestClient(app)
        r = client.get(f"/api/v1/transactions/{txn_id}/risk-explain", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["transaction_id"] == txn_id
        assert "risk_score" in body
        assert "risk_level" in body
        assert body["risk_level"] in ["low", "medium", "high", "critical"]
        assert "decision" in body
        assert body["decision"] in ["allow", "review", "block"]
        assert "triggered_rules" in body
        assert "evaluated_rules" in body
        assert "decision_reason" in body
        assert "score_breakdown" in body
        assert "factors" in body
        # factors should contain amount, customer_risk_tier etc
        for f in ["amount", "customer_risk_tier", "merchant_category_code"]:
            assert f in body["factors"]

    def test_triggered_rules_real(self, db_session, sample_rules, auth_headers):
        res = _seed_txns(db_session, 3)
        # Small amount should trigger allow_small, high should trigger block
        txn_small = str(res[0].transaction_id)  # 100 -> allow_small
        client = TestClient(app)
        r = client.get(f"/api/v1/transactions/{txn_small}/risk-explain", headers=auth_headers).json()
        # allow_small should be in evaluated, maybe triggered
        names = [x["rule_name"] for x in r["evaluated_rules"]]
        assert "allow_small" in names
        # Check triggered are subset of evaluated and matched true
        for tr in r["triggered_rules"]:
            assert tr["matched"] is True
            assert tr["rule_name"] in names

    def test_decision_matches_engine(self, db_session, sample_rules, auth_headers):
        res = _seed_txns(db_session, 3)
        txn_block = str(res[2].transaction_id)
        client = TestClient(app)
        body = client.get(f"/api/v1/transactions/{txn_block}/risk-explain", headers=auth_headers).json()
        # Block gambling + high amount should result in block
        assert body["decision"] == "block"
        # Check decision_reason mentions BLOCK precedence
        assert "BLOCK" in body["decision_reason"]

    def test_risk_score_matches(self, db_session, sample_rules, auth_headers):
        res = _seed_txns(db_session, 2)
        txn_id = str(res[1].transaction_id)  # 6000 -> review
        client = TestClient(app)
        explain = client.get(f"/api/v1/transactions/{txn_id}/risk-explain", headers=auth_headers).json()
        # Fetch same via transactions list
        list_resp = client.get("/api/v1/transactions", headers=auth_headers, params={"page_size": 100}).json()
        # Find same txn
        item = next((x for x in list_resp["items"] if x["id"] == txn_id), None)
        assert item is not None
        assert abs(item["risk_score"] - explain["risk_score"]) < 0.01
        assert item["risk_level"] == explain["risk_level"]
        assert item["decision"] == explain["decision"]


# CONSISTENCY ACROSS ENDPOINTS

class TestConsistency:
    def test_transaction_list_vs_explain(self, db_session, sample_rules, auth_headers):
        res = _seed_txns(db_session, 5)
        client = TestClient(app)
        list_body = client.get("/api/v1/transactions?page_size=100", headers=auth_headers).json()
        for item in list_body["items"]:
            expl = client.get(f"/api/v1/transactions/{item['id']}/risk-explain", headers=auth_headers).json()
            assert item["risk_score"] == expl["risk_score"]
            assert item["risk_level"] == expl["risk_level"]
            assert item["decision"] == expl["decision"]
            # triggered rules should match count
            assert len(item["triggered_rules"]) == len(expl["triggered_rules"])

    def test_analytics_vs_explain(self, db_session, sample_rules, auth_headers):
        _seed_txns(db_session, 5)
        client = TestClient(app)
        analytics = client.get("/api/v1/analytics/dashboard?days=30", headers=auth_headers).json()
        # analytics risk distribution should be consistent with per-transaction risks
        # Sum of risk distribution counts should equal total transactions
        total = analytics["overview"]["total_transactions"]
        assert sum(x["count"] for x in analytics["risk_distribution"]) == total


# DB ISOLATION

class TestIsolation:
    def test_isolation_guard(self):
        import os
        assert "risk_era_test" in os.getenv("DATABASE_URL", "")

    def test_no_seed_demo(self, db_session):
        cnt = db_session.execute(text("SELECT count(*) FROM customers")).scalar()
        assert cnt < 20
