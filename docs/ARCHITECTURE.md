# RISK-ERA Architecture

## Overview

RISK-ERA is a transaction investigation system that combines rule-based detection with AI-powered investigation orchestration using NVIDIA Nemotron large language models.

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 19, Vite, TypeScript, Axios |
| **Backend** | FastAPI, Python 3.11 |
| **Database** | PostgreSQL 17 |
| **AI/ML** | NVIDIA Nemotron 3.5 Lightning 30B A3B |
| **API** | RESTful JSON over HTTP/1.1 |
| **Container** | Docker (multi-stage where applicable) |

## System Workflow

1. **Rule Engine**: Transaction rules detect anomalies → create Case records
2. **Analyst Interface**: Analyst opens case → reviews transaction details
3. **Investigation**: Analyst triggers Nemotron investigation → tools execute → evidence gathered
4. **AI Reasoning**: Nemotron generates investigation result with findings, recommendation, confidence
5. **Evidence Grounding**: Evidence IDs validated against schema; missing/referenced status tracked
6. **Analyst Feedback**: ACCEPT/MODIFY/REJECT with optional reason → audit trail
7. **Audit**: Hash-chain integrity verification of all events

## Data Flow

```
Frontend (React + Vite)
    ↓ HTTPS/HTTP
Backend (FastAPI + Python)
    ↓ SQL
PostgreSQL (risk_era database)
    ↓ NVIDIA API
NVIDIA Nemotron API (https://integrate.api.nvidia.com/v1)
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| GET | /ready | Readiness check (DB + Nemotron) |
| POST | /api/v1/auth/login | JWT authentication |
| GET | /api/v1/cases/ | List cases |
| GET | /api/v1/cases/{id} | Case details |
| POST | /api/v1/investigation/{case_id}/run | Run investigation |
| POST | /api/v1/feedback/ | Submit analyst feedback |
| GET | /api/v1/audit/ | Audit events |

## Deployment Architecture

```
[Browser] ↔ [Frontend Container: Nginx + Static Assets]
      |
      API Calls (VITE_API_BASE_URL)
      |
[Backend Container: FastAPI + Uvicorn]
      |
[PostgreSQL Container: risk_era database]
      |
[NVIDIA Nemotron API (external, environment-provided)]
```

## Security Architecture

- **Authentication**: JWT Bearer tokens via `Authorization: Bearer <header>`
- **Authorization**: Role-based (ANALYST, ADMIN) with 30+ granular permissions
- **Security Headers**: CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy
- **Rate Limiting**: 100 requests per 60 seconds per IP (429 response), skip /health/ and /ready/
- **Input Validation**: UUID validation, pagination limits (max 100), date range validation, JSON payload max 1MB
- **Correlation IDs**: X-Request-ID middleware preserves and propagates request IDs
- **Structured Logging**: JSON formatted; request_id, endpoint, case_id, duration_ms; never logs secrets
- **Audit Hash Chain**: SHA-256 linked event chain; `verify_chain()` validates integrity
- **No Hardcoded Secrets**: All credentials from environment variables; `.env` git-ignored; `.env.example` has placeholders
- **CORS**: Development allows localhost; production origins empty (configure for deployment)
- **No Secrets in Frontend**: No NVIDIA API key, database credentials, or JWT secrets in browser bundles

## Nemotron Integration

- **Endpoint**: `https://integrate.api.nvidia.com/v1`
- **Model**: `nvidia/nemotron-3.5-lightning-30b-a3b`
- **Authentication**: NVIDIA API key via `NVIDIA_API_KEY` environment variable
- **Workflow**: Investigator → controlled tool calls → evidence grounding → investigation result → persistence → audit
- **Why Controlled Tools**: The investigator does not have direct database access. Instead, it executes a predefined set of sanitized tools (evidence retrieval, schema validation) that return read-only data. This design ensures:
  - **No PII leakage**: The LLM never sees raw database rows; only sanitized evidence summaries
  - **Deterministic behavior**: Tool outputs are validated against a schema before reaching the LLM
  - **Auditability**: Every tool call is logged with arguments and results in the audit hash chain
  - **Security**: The NVIDIA API key never grants direct database access; the backend mediates all data exposure
  - **Hallucination prevention**: Missing or invalid evidence IDs are flagged before the model generates a recommendation
- **Result Schema**: InvestigationResult with recommendation, confidence score, findings, evidence IDs

## Investigation Workflow

1. Rule engine flags suspicious transaction → Case created (status: OPEN)
2. Analyst opens case → reviews transaction, risk score, findings
3. Analyst triggers investigation → `POST /api/v1/investigation/{case_id}/run`
4. System executes: tool retrieval → evidence validation → Nemotron API call
5. Nemotron generates result → InvestigationResult stored in PostgreSQL
6. Analyst reviews result → ACCEPT/MODIFY/REJECT with optional reason
7. Audit event recorded with hash chain → integrity verifiable via `verify_chain()`

## Evidence Grounding

- Evidence IDs reference validated data sources
- Status tracking: valid, missing, referenced
- Schema validation ensures evidence consistency
- Audit log tracks evidence addition and modifications

## Persistence

- SQLAlchemy ORM with PostgreSQL
- Alembic migrations for schema evolution
- Atomic investigation sessions: commit on success, rollback on failure
- Pool recycle configuration for connection management
- Investigation records persist with: case_id, status, model, recommendation, confidence, duration_ms, tool_calls, evidence_ids

## Audit Mechanism

- 8 event types: AUTH_SUCCESS, AUTH_FAILED, AUTHZ_SUCCESS, AUTHZ_DENIED, INVESTIGATION_STARTED, INVESTIGATION_COMPLETED, EVIDENCE_ADDED, RATE_LIMITED
- SHA-256 hash chain: each event stores `previous_hash`, computed `hash`
- `audit_service.verify_chain()` validates entire chain integrity
- Events include: timestamp, event_type, actor, case_id, details, hash, previous_hash
- Tamper-evident: changing any event invalidates the entire chain

## Engineering Challenges & Recovery

Real issues encountered during Phases 1–10 and how they were fixed:

1. **JWT stale-token / HealthPage 401**
   - HealthPage was created with `new ApiService(token)` where `token` was captured in an Axios interceptor closure at construction time. `HealthPage` used `useEffect([])` with no `api` dependency, so after `App.tsx` recreated `api` on login (new JWT), the HealthPage still used the old `api` instance with `null` token. Protected calls `GET /api/v1/tools/status` and `GET /api/v1/audit/verify-chain` therefore sent no `Authorization` and returned 401, while `GET /health` (public) stayed 200 and the UI still showed Admin1 logged in.
   - Root cause was a stale closure, not a backend auth bypass.
   - Fix: `ApiService` now stores `_token` and the interceptor reads `this._token || localStorage.getItem("risk_era_token")` at request time; `HealthPage` effect now depends on `[api]` and `App.tsx` uses `useMemo(() => new ApiService(token), [token])` correctly, and all protected requests use `Authorization: Bearer <current JWT>` via the single `risk_era_token` session. Verified with `TestClient` (401 without JWT, 200 with) and browser Network tab showing `Authorization` header on health checks.

2. **Responsive header overlap at 900–1280px**
   - Original header used `flex-wrap:nowrap; height:68px; overflow:hidden` with fixed `white-space:nowrap` and `flex-shrink:0` on many elements. At 1280/1024/900 the hamburger, logo, nav, health indicators, Admin1 badge and Logout visually merged and buttons touched, with horizontal overflow hidden rather than wrapped.
   - Fixed with proper flexbox: header base `flex-wrap:wrap; min-height:68px; height:auto; overflow:visible; gap:12px`, `header-left` `flex:1 1 auto`, `header-nav` `flex-wrap:wrap` with horizontal scroll fallback, `header-right` `flex-wrap:wrap`, responsive breakpoints for 1280 (hide demo-badge), 1024 (2-row: row1 logo+user, row2 nav full width), 900 (gap reduction), plus 768/600/480/390/360/320. No `position:absolute` hacks, no hidden important functionality.

3. **Network Error after dashboard switching (request explosion / pool exhaustion)**
   - Rapid switching `Overview → Cases → Customers → Merchants → Devices → Network → Rules → Alerts → Audit → Health` for 5–10 cycles generated ~180 requests in <60s, exceeding the in-memory rate limiter (100/60s) and exhausting the SQLAlchemy `QueuePool` (5 + 10 = 15 max) with `pool_timeout=30`, plus `Dashboard` KPI `onNavigate` used `window.location.assign` causing full reloads. Backend logs showed `GET /api/v1/tools/status → 429/401` and `QueuePool` timeouts, frontend showed "Network Error" (not just 401).
   - Fixed with minimal production changes: rate limiter limit raised to 1000 for `APP_ENV=development` (testing already bypassed), DB pool increased to `pool_size 10 / max_overflow 20 / pool_timeout 10`, fixed `Dashboard` to use `navigate(p)` instead of `window.location.assign`, fixed `Response`→`JSONResponse` bug in rate-limit middleware that caused 500 on 429, and ensured `get_db` correctly yields/closes. Verified via repeated 10-cycle switching with DevTools Network showing all `Authorization` headers present and no 429/500.

4. **Alert enum mismatch (alert_status / alert_severity)**
   - Migration created `alert_status` with lowercase labels (`open`) but `SQLAlchemy Enum` with `str` enum sent uppercase names (`OPEN`), causing `psycopg2.errors.InvalidTextRepresentation: invalid input value for enum alert_status: "OPEN"`.
   - Fixed by aligning Python enum values to uppercase (`OPEN`, `CRITICAL`, etc.) and recreating the enum types via `alembic downgrade`/`upgrade` with `ALTER TYPE ... RENAME VALUE` handling, and making service queries use `AlertStatus[status.upper()]` with case-insensitive handling. Verified via `test_phase7_alerts` now passing.

## Known Limitations

- No RAG/vector search capability
- No Redis caching or Kafka streaming
- No Kubernetes or multi-agent orchestration
- Deployment requires PostgreSQL, Docker (optional), and NVIDIA API key
- Frontend requires `VITE_API_BASE_URL` configuration for production use