import os
import sys

# Ensure tests never use the demo database
TEST_DB_URL = "postgresql+psycopg2://risk_era:risk_era_dev@localhost:5432/risk_era_test"

# Override environment before app imports
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("NVIDIA_API_KEY", "test-nvidia-key-for-tests")

# Regression guard: prevent accidental use of demo DB
db_url = os.environ.get("DATABASE_URL", "")
if "risk_era_test" not in db_url:
    raise RuntimeError(
        f"TEST DATABASE GUARD: pytest is configured to use demo database: {db_url}. "
        f"Tests MUST use {TEST_DB_URL}. Aborting to protect demo data."
    )

# Optional: ensure Settings loads after env is set
# The app imports settings lazily, this guard runs early enough.

# Provide a pytest fixture for a clean DB per test session if needed
import pytest
from sqlalchemy import create_engine, text
from app.core.database import Base

@pytest.fixture(scope="session", autouse=True)
def ensure_test_db():
    # Verify connection works
    engine = create_engine(TEST_DB_URL)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    # Optionally drop/create schema for isolation – tests use clean_db helpers
    yield
