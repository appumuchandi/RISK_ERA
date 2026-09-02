# RISK-ERA — Engineering Notes

## What RISK-ERA Is
RISK-ERA is an AI-assisted risk investigation platform built around **controlled AI access, evidence grounding, authenticated investigation workflows, and tamper-evident auditability**. It helps analysts detect suspicious transactions via a rule engine, investigate with AI that only sees sanitized tool outputs, and make auditable decisions.

## Build Sequence / Major Milestones
- **M1–M3:** Core schema, cases, evidence, rules, audit hash chain (23/23 schema tests)
- **Phase 2:** Transaction Intelligence (risk scoring, filtering, 45 tests)
- **Phase 3:** Customer/Merchant/Device Intelligence (38 tests)
- **Phase 4:** Fraud Network Intelligence (3-hop BFS, 33 tests)
- **Phase 5:** Analytics Dashboard (21 tests)
- **Phase 6:** Rules & Decision Transparency (26 tests, risk-explain)
- **Phase 7:** Alerts & Operations (31 tests, alert lifecycle, operations summary)
- **Phase 8:** Investigation Workbench (6 stages, 18 tests)
- **Phase 9:** Audit Center (28 tests) + Light UI Modernization (premium responsive)
- **Phase 10:** System Health (6 tests) + AI Assistant (7 tests, floating FAB)

## Important Engineering Decisions
- **FastAPI + PostgreSQL + SQLAlchemy + Alembic:** Type-safe, async-ready, ACID, JSONB for investigation results, atomic sessions.
- **No Redis/Kafka/Neo4j/vector DB:** Intentionally avoided premature infrastructure; in-memory rate limiting (1000 for dev), single-agent, single DB.
- **JWT/RBAC:** Two roles (ANALYST, ADMIN) with 30+ permissions, `Authorization: Bearer` only, no query-param auth.
- **Frontend:** React 19 + Vite + TypeScript + Axios, `BrowserRouter`, `AuthContext` with `risk_era_token` in `localStorage`, `ApiService` with Bearer interceptor.

## AI Architecture
- **NVIDIA Nemotron 3.5 Lightning 30B A3B** via `https://integrate.api.nvidia.com/v1` with `NVIDIA_API_KEY` from environment (never frontend).
- **Investigator:** `NemotronInvestigator` with `MAX_TOOL_CALLS=5`, `MODEL_TIMEOUT=12s`, demo fallback key.

## Controlled Tool-Use Architecture
The AI **does NOT receive direct database access**. It only receives **controlled/sanitized tool outputs**:
- `get_transaction_history` (customer_id, limit, date range)
- `get_customer_profile` (aggregated metrics)
- `get_device_activity` (transaction metrics)

**Why this boundary exists:**
- No PII leakage (raw rows never sent to LLM)
- Deterministic validation (Pydantic schemas before LLM)
- Auditability (every tool call logged in hash chain)
- Hallucination prevention (missing/invalid evidence flagged before model)
- Security (NVIDIA key never grants DB access; backend mediates)

## Evidence Grounding
- Evidence IDs validated: `valid` (exists), `missing` (not found), `referenced` (points elsewhere)
- Only `valid` IDs included in Nemotron prompt
- Investigation result tracks `evidence_references` vs `missing_evidence`, confidence adjusted if grounding fails
- Tested across 12 categories, 25 cases.

## Audit/Hash-Chain Design
- Each `audit_log` stores `prev_hash` and computed `hash = SHA-256(actor, action, resource_type, resource_id, before/after, prev_hash, created_at)` with sorted JSON.
- First event `prev_hash = NULL` (“genesis”).
- `verify_chain()` walks chronologically, recomputes hashes, returns `valid`/`error` with `checked_count`.
- 8 event types: `case_created`, `case_updated`, `evidence_added`, `investigation_started/completed`, `alert_*`, `authentication_*`, etc.
- Tamper-evident: any modification breaks chain.

## Authentication/RBAC
- JWT Bearer via `Authorization: Bearer <token>` header, `jwt_secret_key` from env, `require_auth` dependency.
- Two roles, 30+ permissions, role-aware UI (ADMIN features hidden from ANALYST).
- Security headers: CSP, HSTS, X-Frame, X-Content-Type, Referrer-Policy, rate limiting 1000/60s for dev, X-Request-ID.

## Important Bugs Encountered, Diagnosis & Fix

### 1. Stale-token / HealthPage 401
- **Symptom:** HealthPage showed `Investigation Tools UNAVAILABLE / 401` and `Audit Chain UNAVAILABLE / 401` while header showed Admin1 logged in; backend logs `GET /health 200` but `GET /api/v1/tools/status 401`.
- **Diagnosis:** `ApiService` captured `token` in interceptor closure at construction (`if (token) config.headers.Authorization = ...`), `HealthPage` used `useEffect([])` with no `api` dependency, so after `App.tsx` recreated `api` on login, HealthPage still used the old `api` instance with `null` token. `Dashboard` also showed "Authentication required" when logged in for same reason.
- **Fix:** `ApiService` now stores `_token` and interceptor reads `this._token || localStorage.getItem("risk_era_token")` at request time; `HealthPage` effect now depends on `[api]` and `App.tsx` uses `useMemo(() => new ApiService(token), [token])` correctly, and `Dashboard` already had `[days, api]`. Verified: unauthenticated 401, authenticated 200 for both endpoints, no query-param auth, no second token.

### 2. Responsive Header Overlap (900–1280px)
- **Symptom:** At 900–1280px, hamburger, logo, nav, health indicators, Admin1 badge and Logout visually merged, buttons touching, header `overflow:hidden` hid collisions.
- **Diagnosis:** Header used `flex-wrap:nowrap; height:68px; overflow:hidden` with fixed `white-space:nowrap` and `flex-shrink:0` on many elements, no wrapping at intermediate widths.
- **Fix:** Header base `flex-wrap:wrap; min-height:68px; height:auto; overflow:visible; gap:12px`, `header-left` `flex:1 1 auto`, `header-nav` `flex-wrap:wrap` with horizontal scroll fallback, `header-right` `flex-wrap:wrap`, breakpoints for 1280 (hide demo-badge), 1024 (2-row: row1 logo+user, row2 nav full width), 900, 768, etc., verified at 1920→320 with no horizontal overflow, no clipped content, sidebar drawer still works.

### 3. Alert Enum Mismatch
- **Symptom:** `psycopg2.errors.InvalidTextRepresentation: invalid input value for enum alert_status: "OPEN"` after adding alerts table.
- **Diagnosis:** Migration created `alert_status` with lowercase labels (`open`) but `SQLAlchemy Enum` with `str` enum sent uppercase names (`OPEN`) because `Enum` default uses member name. `rule_action` already had uppercase in DB, so it worked, but `alert_status` did not.
- **Fix:** Aligned Python `AlertStatus`/`AlertSeverity` values to uppercase (`OPEN`, `CRITICAL`, etc.), updated migration to create enums with uppercase, and made service queries use `AlertStatus[status.upper()]` with case-insensitive handling. Verified via `test_phase7_alerts` now passing.

### 4. Full Suite Timeout (391 tests)
- **Symptom:** `python -m pytest -q` as single invocation (391 tests) exceeded 300s due to session-scoped `clean_db` TRUNCATE lock deadlock across 14 files when run as one massive suite.
- **Diagnosis:** Each test file defines `scope="session"` `db` fixture with `TRUNCATE ... CASCADE` which takes ACCESS EXCLUSIVE lock; when pytest runs all files sequentially in one process, the previous file's session remains open while next file's `clean_db` tries to truncate, causing deadlock.
- **Fix:** Not a product logic failure. Verified via batched runs: 195 tests (7 files) in 147s, 201 tests (8 files) in 149s, individual files <30s, all green. Documented as test harness limitation, not hidden.

## Security Verification
- No `nvapi-` or `eyJhbGci` in `frontend/src` (verified via `Select-String` on `frontend/risk-era-analyst/src`)
- No `?authorization=` / `?Authorization=` / `?actor=` handling, no `window.location.reload`, no `HashRouter` (only `BrowserRouter`)
- `require_auth` on all protected endpoints (15/15 including assistant)
- `Assistant` endpoint requires auth, no API key in frontend, uses existing `risk_era_token`

## Current Limitations
- No RAG/vector search
- No Redis/Kafka
- No Kubernetes/multi-agent
- Single-agent, in-memory rate limiting
- Full suite as single invocation can timeout due to fixture lock (see above) — use batched runs
- HealthPage overall status is client-derived aggregation (intentionally light)

## Final Verification
- `python -m pytest -q tests/test_phase10_health.py` → 6 passed
- `python -m pytest -q tests/test_phase9_audit.py` → 28 passed
- `python -m pytest -q tests/test_phase8_investigation.py` → 18 passed
- Batched 195 tests → 195 passed
- `npm run build` → 95→99 modules, 0 TS errors
- `python -c "from app.main import app; print('IMPORT OK')"` → IMPORT OK
- Demo DB: customers 42, merchants 17, devices 28, transactions 231, cases 83, evidence 63, investigations 6, alerts 0, audit_log 156 — unchanged
