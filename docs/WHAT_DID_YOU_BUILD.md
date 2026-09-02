# What Did You Build?

## RISK-ERA: Transaction Investigation System

RISK-ERA is a full-stack investigation platform that combines rule-based anomaly detection with NVIDIA Nemotron AI-powered orchestration. The system processes suspicious transactions through a deterministic workflow: rule engine → case creation → analyst review → controlled AI investigation → evidence-grounded recommendation → analyst feedback → audit trail.

## Key Engineering Contributions

### Investigation Workflow Orchestration
Designed the end-to-end investigation pipeline from rule-based anomaly detection to AI-generated recommendations. The workflow is: rule engine flags suspicious transactions → Case records created (status: OPEN) → Analyst reviews transaction details → triggers `POST /api/v1/investigation/{case_id}/run` → Nemotin investigator executes controlled tools → evidence validated against schema → Nemotin API call generates InvestigationResult (recommendation, confidence, findings, evidence IDs) → result persisted to PostgreSQL → Analyst submits ACCEPT/MODIFY/REJECT feedback → audit event recorded with hash chain. All 157 automated tests pass, verifying the full lifecycle.

### Controlled AI Tool Pattern
Core design decision: the investigator (Nemotin) does **not** have direct database access. Instead, it executes a predefined set of sanitized tools (evidence retrieval, schema validation) that return read-only summaries. This design ensures:
- **No PII leakage**: The LLM never sees raw database rows; only sanitized evidence summaries
- **Deterministic behavior**: Tool outputs validated against Pydantic schemas before reaching the model
- **Auditability**: Every tool call is logged with arguments and results in the SHA-256 audit hash chain
- **Security**: The NVIDIA API key never grants direct database access; the backend mediates all data exposure
- **Hallucination prevention**: Missing/invalid evidence IDs are flagged before the model generates a recommendation

### Evidence Grounding System
Built an evidence grounding pipeline that validates evidence IDs against a Pydantic schema before the model sees them. Three statuses: `valid` (exists and matches), `missing` (not found), `referenced` (pointing to another entity). Only `valid` evidence IDs are included in the Nemotin prompt. The investigation result explicitly surfaces grounding status, so the analyst knows which evidence is reliable and which requires attention. This design prevents the model from generating findings based on non-existent or ambiguous data.

### JWT Authentication & RBAC
Implemented JWT Bearer token authentication (`Authorization: Bearer <token>`) with two roles and ~30 granular permissions:
- **ANALYST**: case review, investigation triggering, feedback submission, evidence view
- **ADMIN**: all analyst capabilities + user management, system configuration
Permission checks enforced in route dependencies. Denied attempts logged via `AUTHZ_DENIED` audit event. Role-aware UI: ADMIN features hidden from ANALYST and vice versa.

### SHA-256 Audit Hash Chain
Replaced append-only logs with a tamper-evident hash chain: each event stores `previous_hash` and computed `hash` (SHA-256). `audit_service.verify_chain()` validates entire chain integrity in O(n). 8 event types: AUTH_SUCCESS, AUTH_FAILED, AUTHZ_SUCCESS, AUTHZ_DENIED, INVESTIGATION_STARTED, INVESTIGATION_COMPLETED, EVIDENCE_ADDED, RATE_LIMITED. Changing any event invalidates the entire chain. This provides cryptographic assurance that the audit trail has not been modified.

### Security-by-Default Configuration
- No hardcoded secrets: all credentials from environment variables (`DATABASE_URL`, `NVIDIA_API_KEY`, `JWT_SECRET_KEY`, `CORS_ORIGINS`)
- `.env` git-ignored; `.env.example` has placeholder values only
- Security headers: CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy
- Rate limiting: 100 requests/60s per IP; HTTP 429; skip /health/ and /ready/
- Input validation: UUID format, pagination (max 100), date range, JSON payload max 1MB
- Correlation IDs: X-Request-ID middleware propagated through requests, responses, and structured JSON logs
- Frontend: no API keys, no database credentials, no JWT secrets in browser bundles
- All communication through backend APIs only; no direct DB access from frontend; no direct NVIDIA API access from frontend

### Docker-Ready Deployment
Created production-oriented Dockerfiles:
- **Backend**: Python 3.11-slim, install dependencies from requirements.txt, run Alembic migrations, start Uvicorn
- **Frontend**: Multi-stage (build React/Vite assets, serve with Nginx)
- `docker-compose.yml` orchestrates postgres + backend + frontend with health checks
- No NVIDIA_API_KEY in frontend image; configured via environment at runtime

### Technology Stack Choices
- **React 19 + Vite + TypeScript**: Fast refresh, type safety, modern tooling
- **FastAPI + Python 3.11**: Automatic OpenAPI docs, Pydantic validation, async Nemotin API calls
- **PostgreSQL 17 + psycopg**: ACID guarantees, JSONB for investigation results, strong relational modeling
- **NVIDIA Nemotin 3.5 Lightning 30B A3B**: NVIDIA API endpoint; environment-provided key; controlled tool calling
- **Alembic**: Schema migrations; head at a4fc36b9ad5f; 23/23 schema tests passing

## What Problem It Solves

Financial fraud detection requires both rapid automated response and thorough investigative analysis. Traditional systems either auto-block transactions (risking false positives) or require manual review at scale. RISK-ERA combines the best of both: rule-based filtering reduces the volume of cases needing attention, while the Nemotin investigator provides evidence-grounded recommendations that analysts can ACCEPT, MODIFY, or REJECT — with full auditability and no data governance violations.

## What Makes It Different

Most AI+fraud systems either (a) grant the LLM direct database access (security risk, no auditability) or (b) use the LLM only for classification without investigation orchestration. RISK-ERA uniquely combines: (a) controlled tool pattern where the LLM never sees raw data, (b) evidence grounding with explicit valid/missing/referenced status, (c) SHA-256 hash-chain audit log with integrity verification, and (d) full JWT/RBAC security from the database layer to the frontend — all with 157 automated tests verifying correctness.