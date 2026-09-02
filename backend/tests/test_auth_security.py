from __future__ import annotations

import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import JWTAuth
from app.core.database import SessionLocal
from app.main import app
from app.models.user import User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture(scope="session")
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_db(db: Session):
    db.execute(text("TRUNCATE TABLE users, alerts, cases, transactions, rules, merchants, devices, customers, audit_log, investigations, analyst_feedback, evidence RESTART IDENTITY CASCADE"))
    db.commit()
    yield
    db.execute(text("TRUNCATE TABLE users, alerts, cases, transactions, rules, merchants, devices, customers, audit_log, investigations, analyst_feedback, evidence RESTART IDENTITY CASCADE"))
    db.commit()


@pytest.fixture(autouse=True)
def clear_rate_limiters():
    # Clear rate limiters before each test to avoid cross-test pollution
    from app.middleware.rate_limit import get_rate_limiter
    from app.api.auth import _auth_login_limiter, _auth_register_limiter
    get_rate_limiter()._clients.clear()
    _auth_login_limiter._clients.clear()
    _auth_register_limiter._clients.clear()
    yield
    get_rate_limiter()._clients.clear()
    _auth_login_limiter._clients.clear()
    _auth_register_limiter._clients.clear()


@pytest.fixture
def db_session(db: Session) -> Session:
    yield db
    db.rollback()


def _create_user(db_session: Session, username: str = "testuser", email: str = "test@example.com", password: str = "TestPass123!", role: str = "analyst"):
    hashed = pwd_context.hash(password)
    user = User(username=username, email=email, hashed_password=hashed, role=role)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestAuthSecurity:
    def test_unknown_username_demo_401(self, db_session):
        client = TestClient(app)
        r = client.post("/api/v1/auth/login", json={"username": "unknown_user_xyz", "password": "demo"})
        assert r.status_code == 401

    def test_existing_username_demo_401(self, db_session):
        _create_user(db_session, username="existing1", email="existing1@example.com", password="CorrectPass123!")
        client = TestClient(app)
        r = client.post("/api/v1/auth/login", json={"username": "existing1", "password": "demo"})
        assert r.status_code == 401

    def test_unknown_random_401(self, db_session):
        client = TestClient(app)
        r = client.post("/api/v1/auth/login", json={"username": "nonexistent", "password": "randompass123"})
        assert r.status_code == 401

    def test_existing_wrong_password_401(self, db_session):
        _create_user(db_session, username="user2", email="user2@example.com", password="CorrectPass123!")
        client = TestClient(app)
        r = client.post("/api/v1/auth/login", json={"username": "user2", "password": "WrongPass123!"})
        assert r.status_code == 401

    def test_existing_correct_200(self, db_session):
        _create_user(db_session, username="user3", email="user3@example.com", password="CorrectPass123!")
        client = TestClient(app)
        r = client.post("/api/v1/auth/login", json={"username": "user3", "password": "CorrectPass123!"})
        assert r.status_code == 200
        assert "access_token" in r.json()
        assert r.json()["username"] == "user3"

    def test_login_contains_jwt_only_after_success(self, db_session):
        client = TestClient(app)
        r = client.post("/api/v1/auth/login", json={"username": "bad", "password": "bad"})
        assert r.status_code == 401
        assert "access_token" not in r.json()

    def test_client_cannot_choose_role(self, db_session):
        client = TestClient(app)
        # Try to register with role admin should be ignored, always analyst
        username = f"role_test_{uuid4().hex[:6]}"
        email = f"{username}@example.com"
        r = client.post("/api/v1/auth/register", json={"username": username, "email": email, "password": "TestPass123!", "confirm_password": "TestPass123!", "name": "Test"})
        assert r.status_code == 201
        assert r.json()["role"] == "analyst"
        # Try to register with explicit role in payload (should be ignored, no field)
        username2 = f"role_test2_{uuid4().hex[:6]}"
        email2 = f"{username2}@example.com"
        r2 = client.post("/api/v1/auth/register", json={"username": username2, "email": email2, "password": "TestPass123!", "confirm_password": "TestPass123!", "role": "admin"})
        # Should either ignore or 422, but not create admin
        if r2.status_code == 201:
            assert r2.json()["role"] == "analyst"
        else:
            assert r2.status_code in (422, 400)

    def test_query_param_auth_rejected(self, db_session):
        _create_user(db_session, username="user4", email="user4@example.com", password="CorrectPass123!")
        client = TestClient(app)
        token = JWTAuth.encode_token("user4")
        r = client.get(f"/api/v1/auth/me?authorization=Bearer {token}")
        # Should still be 401 because auth is via header, not query, but endpoint will try header and fail, so it should be 401
        # However our /auth/me requires header, query should not auth, so it will be 401 if no header
        assert r.status_code == 401
        r2 = client.get(f"/api/v1/auth/me?Authorization=Bearer {token}")
        assert r2.status_code == 401
        r3 = client.get(f"/api/v1/auth/me?actor=admin")
        assert r3.status_code == 401

    def test_passwords_hashed(self, db_session):
        user = _create_user(db_session, username="hash_test", email="hash_test@example.com", password="TestPass123!")
        # Check DB directly
        row = db_session.execute(text("SELECT hashed_password FROM users WHERE username=:u"), {"u": "hash_test"}).fetchone()
        assert row is not None
        hashed = row[0]
        assert hashed != "TestPass123!"
        assert pwd_context.verify("TestPass123!", hashed)

    def test_password_not_returned(self, db_session):
        client = TestClient(app)
        username = f"nopass_{uuid4().hex[:6]}"
        email = f"{username}@example.com"
        r = client.post("/api/v1/auth/register", json={"username": username, "email": email, "password": "TestPass123!", "confirm_password": "TestPass123!"})
        assert r.status_code == 201
        body = r.json()
        assert "hashed_password" not in body
        assert "password" not in body

    def test_duplicate_username_409(self, db_session):
        _create_user(db_session, username="dupuser", email="dup1@example.com", password="TestPass123!")
        client = TestClient(app)
        r = client.post("/api/v1/auth/register", json={"username": "dupuser", "email": "dup2@example.com", "password": "TestPass123!", "confirm_password": "TestPass123!"})
        assert r.status_code == 409

    def test_duplicate_email_409(self, db_session):
        _create_user(db_session, username="dupuser2", email="dup@example.com", password="TestPass123!")
        client = TestClient(app)
        r = client.post("/api/v1/auth/register", json={"username": "dupuser3", "email": "dup@example.com", "password": "TestPass123!", "confirm_password": "TestPass123!"})
        assert r.status_code == 409

    def test_invalid_registration_422(self, db_session):
        client = TestClient(app)
        # Short password
        r = client.post("/api/v1/auth/register", json={"username": "ab", "email": "invalid", "password": "short", "confirm_password": "short"})
        assert r.status_code == 422
        # Mismatched passwords
        r2 = client.post("/api/v1/auth/register", json={"username": "validuser", "email": "valid@example.com", "password": "TestPass123!", "confirm_password": "Different123!"})
        assert r2.status_code == 422

    def test_registration_default_analyst(self, db_session):
        client = TestClient(app)
        username = f"analyst_test_{uuid4().hex[:6]}"
        email = f"{username}@example.com"
        r = client.post("/api/v1/auth/register", json={"username": username, "email": email, "password": "TestPass123!", "confirm_password": "TestPass123!"})
        assert r.status_code == 201
        assert r.json()["role"] == "analyst"

    def test_client_cannot_register_admin(self, db_session):
        client = TestClient(app)
        username = f"admin_test_{uuid4().hex[:6]}"
        email = f"{username}@example.com"
        # Try to inject role
        r = client.post("/api/v1/auth/register", json={"username": username, "email": email, "password": "TestPass123!", "confirm_password": "TestPass123!", "role": "admin"})
        # Should be analyst regardless
        if r.status_code == 201:
            assert r.json()["role"] != "admin"
            assert r.json()["role"] == "analyst"
        else:
            assert r.status_code in (422, 400)

    def test_rate_limiting_login(self, db_session):
        client = TestClient(app)
        # Try 11 logins quickly (limit 10 per minute)
        for i in range(11):
            r = client.post("/api/v1/auth/login", json={"username": f"rate_test_{i}", "password": "wrong"})
            # First 10 should be 401, 11th should be 429
            if i >= 10:
                assert r.status_code == 429
                break

    def test_rate_limiting_register(self, db_session):
        client = TestClient(app)
        # Try 6 registers quickly (limit 5 per minute)
        for i in range(6):
            username = f"rate_reg_{uuid4().hex[:4]}_{i}"
            email = f"{username}@example.com"
            r = client.post("/api/v1/auth/register", json={"username": username, "email": email, "password": "TestPass123!", "confirm_password": "TestPass123!"})
            if i >= 5:
                assert r.status_code == 429
                break

    def test_no_plaintext_demo_users(self):
        # Ensure auth.py no longer contains DEMO_USERS
        import pathlib
        # When running from backend directory, path is app/api/auth.py; when from root, it's backend/app/api/auth.py
        p1 = pathlib.Path("app/api/auth.py")
        p2 = pathlib.Path("backend/app/api/auth.py")
        path = p1 if p1.exists() else p2
        content = path.read_text()
        assert "DEMO_USERS" not in content
        assert 'password == "demo"' not in content
        assert "password == 'demo'" not in content
