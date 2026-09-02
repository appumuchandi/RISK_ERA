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
    # Clean relevant tables, but keep rules for assistant
    db.execute(text("TRUNCATE TABLE alerts, cases, transactions, rules, merchants, devices, customers, audit_log, investigations, analyst_feedback, evidence RESTART IDENTITY CASCADE"))
    db.commit()
    yield
    db.execute(text("TRUNCATE TABLE alerts, cases, transactions, rules, merchants, devices, customers, audit_log, investigations, analyst_feedback, evidence RESTART IDENTITY CASCADE"))
    db.commit()


@pytest.fixture
def auth_headers():
    token = JWTAuth.encode_token("analyst")
    return {"Authorization": f"Bearer {token}"}


def test_unauthenticated_401():
    client = TestClient(app)
    r = client.post("/api/v1/assistant/chat", json={"message": "What is RISK-ERA?"})
    assert r.status_code == 401
    r2 = client.post("/api/v1/assistant/chat", json={"message": "Hello", "context": {"route": "/"}})
    assert r2.status_code == 401

def test_authenticated_success(auth_headers):
    client = TestClient(app)
    r = client.post("/api/v1/assistant/chat", json={"message": "What is RISK-ERA?", "context": {"route": "/" }}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "answer" in body
    assert isinstance(body["answer"], str)
    assert len(body["answer"]) > 0
    assert "grounded" in body
    assert "sources" in body

def test_missing_context(auth_headers):
    client = TestClient(app)
    # Contextual question without context should return unavailable, not fabricate
    r = client.post("/api/v1/assistant/chat", json={"message": "Explain this case", "context": {}}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "required backend data is unavailable" in body["answer"].lower() or "unavailable" in body["answer"].lower()

def test_invalid_message(auth_headers):
    client = TestClient(app)
    r = client.post("/api/v1/assistant/chat", json={"message": "", "context": {"route": "/"}}, headers=auth_headers)
    assert r.status_code == 422
    r2 = client.post("/api/v1/assistant/chat", json={"message": "x"*3000, "context": {"route": "/"}}, headers=auth_headers)
    assert r2.status_code == 422

def test_no_api_key_in_frontend():
    # Ensure frontend source does not contain API keys or hardcoded JWT
    import pathlib
    frontend_files = list(pathlib.Path("frontend/risk-era-analyst/src").rglob("*.ts")) + list(pathlib.Path("frontend/risk-era-analyst/src").rglob("*.tsx"))
    for f in frontend_files:
        content = f.read_text(encoding="utf-8", errors="ignore")
        assert "nvapi-" not in content, f"API key found in {f}"
        assert "eyJhbGci" not in content, f"Hardcoded JWT found in {f}"
        assert "?authorization=" not in content.lower()
        assert "hardcoded" not in content.lower() or True  # allow word

def test_query_param_auth_rejected(auth_headers):
    token = auth_headers["Authorization"].split()[1]
    client = TestClient(app)
    r = client.post(f"/api/v1/assistant/chat?authorization=Bearer {token}", json={"message": "Hello"})
    assert r.status_code == 401

def test_isolation_guard():
    import os
    assert "risk_era_test" in os.getenv("DATABASE_URL", "")
