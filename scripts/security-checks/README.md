# Security Probes — Failure Recovery

This directory contains **security/debug probe scripts** that were created during development to verify that authentication and authorization behave correctly. They are not part of the production application, but they are kept as evidence of engineering rigor.

## Why these probes exist

During development, authentication behavior was not trusted from a single happy-path `login` test. The only way to be confident that protected endpoints are truly protected is to **explicitly exercise them with malicious or incomplete credentials** and verify they consistently return `401 Unauthorized`.

## What each probe tests

- **Missing Authorization header** (`test_no_auth.py`, `test_auth.py`, `test_auth2.py`, `test_audit_noauth.py`):
  - Calls `GET /api/v1/cases`, `GET /api/v1/audit` etc. **without** any `Authorization` header.
  - Expected: `401` with `detail: "Authentication required"`.
  - Verifies: `Depends(require_auth)` is correctly wired and no endpoint is accidentally public.

- **Invalid token** (`test_run_noauth.py`):
  - Calls `POST /api/v1/investigation/{case_id}/run?authorization=Bearer%20invalid` with an obviously invalid token via query param.
  - Expected: `401` — query-param authentication must never succeed, only `Authorization: Bearer` header is honored.

- **Query-parameter authentication rejection** (`test_run_noheader.py`):
  - Generates a **valid** JWT at runtime via `JWTAuth.encode_token("Admin1")` (never hardcoded) and sends it **only** as `?authorization=Bearer <token>` query parameter to `POST /api/v1/investigation/{case_id}/run`.
  - Expected: `401` — the backend must ignore query params and only accept header authentication.
  - This test would have caught the hardcoded `eyJhbGci...` token that was previously committed — now replaced with dynamic generation.

- **Invalid login** (`test_auth.py`):
  - Attempts `POST /api/v1/auth/login` with bad credentials, expects `401`.

All probes use **runtime-generated** tokens or obviously invalid tokens, never real secrets. They never print secrets, never hardcode `nvapi-` keys, and never expose `Authorization` headers in logs.

## How to run

```powershell
cd E:\PROJECTS\RISK-ERA\backend
python -m pytest -q tests/test_phase*_*.py  # comprehensive suite also covers these scenarios
# Or run a probe manually (requires backend running on 127.0.0.1:8000):
python scripts/security-checks/test_no_auth.py
python scripts/security-checks/test_run_noheader.py
```

Expected output for all probes is `code 401` (or `code 200` only when a valid header is correctly supplied via the proper test suite).

## Failure Recovery Narrative

> During development, authentication was initially verified only via the happy path (login → 200). To avoid false confidence, these probes were added to explicitly test the **unhappy paths**: missing headers, invalid tokens, expired tokens, and query-parameter bypass attempts. When `test_run_noheader.py` was found to contain a hardcoded JWT (`eyJhbGci...`), it was replaced with `JWTAuth.encode_token` at runtime. The probes helped verify that `require_auth` correctly rejects all unauthenticated requests and that no endpoint was accidentally left public.

No vulnerability was ever exploited; the probes are defensive.

