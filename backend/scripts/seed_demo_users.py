"""
Seed demo users for local/demo presentation.

This script ONLY creates demo users when explicitly executed.
It NEVER runs automatically during application startup, migrations, or login.

Requirements:
- DEMO_MODE=true must be set in environment, otherwise the script refuses to run.
- Passwords are bcrypt hashed before insertion.
- Duplicate username/email are skipped (existing users not overwritten).
- Roles preserved: Admin1/admin -> admin, analyst/demo -> analyst

Usage:
    DEMO_MODE=true python backend/scripts/seed_demo_users.py
    # or
    DEMO_MODE=true python -m scripts.seed_demo_users

Never commit real passwords to source. This script uses demo-only passwords
that are also present in the seeded database as hashes, not plaintext.
If you change these passwords, update your local .env and re-run with DEMO_MODE=true.
"""

from __future__ import annotations

import os
import sys

# Ensure backend is on path when run as `python backend/scripts/seed_demo_users.py`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from passlib.context import CryptContext

from app.core.database import SessionLocal
from app.models.user import User
from app.auth.roles import Role

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Demo users to seed — synthetic, not production.
# These are the same usernames that were previously hardcoded in auth.py DEMO_USERS.
# Passwords are hashed before insertion, never stored plaintext.
DEMO_USERS_TO_SEED = [
    {"username": "analyst", "email": "analyst@risk-era.local", "password": "analyst123", "role": Role.ANALYST},
    {"username": "admin", "email": "admin@risk-era.local", "password": "admin123", "role": Role.ADMIN},
    {"username": "Admin1", "email": "admin1@risk-era.local", "password": "Admin@1234", "role": Role.ADMIN},
]

def main():
    if os.getenv("DEMO_MODE", "").lower() != "true":
        print("Refusing to seed demo users: DEMO_MODE != 'true'")
        print("Set DEMO_MODE=true in environment to intentionally seed local demo users.")
        sys.exit(1)

    db = SessionLocal()
    try:
        created = 0
        skipped = 0
        for u in DEMO_USERS_TO_SEED:
            existing_user = db.execute(select(User).where(User.username == u["username"])).scalar_one_or_none()
            if existing_user:
                print(f"Skipping existing username: {u['username']}")
                skipped += 1
                continue
            existing_email = db.execute(select(User).where(User.email == u["email"])).scalar_one_or_none()
            if existing_email:
                print(f"Skipping existing email: {u['email']}")
                skipped += 1
                continue

            hashed = pwd_context.hash(u["password"])
            user = User(
                username=u["username"],
                email=u["email"],
                hashed_password=hashed,
                role=u["role"],
            )
            db.add(user)
            print(f"Creating demo user: {u['username']} ({u['role']})")

        db.commit()
        print(f"Done. Created: {created if 'created' in locals() else 'see above'}, Skipped: {skipped}")
        # Count total users
        total = db.execute(select(User)).scalars().all()
        print(f"Total users in DB: {len(total)}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
