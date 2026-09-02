from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import JWTAuth
from app.core.database import SessionLocal
from app.main import app


@pytest.fixture(scope="session")
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_db(db: Session):
    # Health does not create data, but ensure clean
    yield


@pytest.fixture
def auth_headers():
    token = JWTAuth.encode_token("analyst")
    return {"Authorization": f"Bearer {token}"}


class TestHealthPublic:
    def test_health_no_auth(self):
        client = TestClient(app)
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_ready_no_auth(self):
        client = TestClient(app)
        r = client.get("/ready")
        assert r.status_code == 200
        assert "database" in r.json()

    def test_tools_status_requires_auth(self):
        client = TestClient(app)
        r = client.get("/api/v1/tools/status")
        assert r.status_code == 401
        token = JWTAuth.encode_token("analyst")
        r2 = client.get("/api/v1/tools/status", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        assert "available" in r2.json()

    def test_audit_verify_requires_auth(self):
        client = TestClient(app)
        r = client.get("/api/v1/audit/verify-chain")
        assert r.status_code == 401


class TestHealthIsolation:
    def test_isolation_guard(self):
        import os
        assert "risk_era_test" in os.getenv("DATABASE_URL", "")

    def test_demo_db_untouched(self, db: Session):
        # Health should not modify DB
        before = db.execute(text("SELECT count(*) FROM customers")).scalar()
        client = TestClient(app)
        client.get("/health")
        client.get("/ready")
        after = db.execute(text("SELECT count(*) FROM customers")).scalar()
        assert before == after
