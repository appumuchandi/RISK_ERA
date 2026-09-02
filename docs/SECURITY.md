# RISK-ERA Security

## Security Architecture

RISK-ERA implements defense-in-depth across multiple layers:

### Authentication
- **JWT Bearer tokens** via `Authorization: Bearer <token>` header
- Secret key from `JWT_SECRET_KEY` environment variable (optional; defaults for backward compatibility)
- Token expiry: 60 minutes configurable via `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`
- Login endpoint: `POST /api/v1/auth/login`
- Protected routes require valid JWT; role enforcement via RBAC

### Authorization
- **Two roles**: ANALYST, ADMIN
- **30+ granular permissions** covering:
  - Case CRUD (create, read, update, delete)
  - Investigation management (start, complete, feedback)
  - Evidence view and validation
  - Audit log access
  - User management (ADMIN only)
- Denied attempts logged via `AUTHZ_DENIED` audit event

### Security Headers (FastAPI Middleware)
- **Content-Security-Policy**: Restricts script/src origins
- **Strict-Transport-Security**: HSTS, 31536000s, includeSubDomains, preload
- **X-Frame-Options**: DENY (prevents clickjacking)
- **X-Content-Type-Options**: nosniff (prevents MIME sniffing)
- **Referrer-Policy**: strict-origin-when-cross-origin

### Request Hardening
- **Rate limiting**: 100 requests/60s per IP via in-memory limiter
  - HTTP 429 response when limit exceeded
  - Skip /health and /ready endpoints
- **Input validation**:
  - UUID format validation for case IDs and evidence IDs
  - Pagination: `skip` (default 0), `limit` (max 100)
  - Date range validation for transaction filters
  - JSON payload max size: 1MB
- **Sanitized tool outputs**: Investigator tool results are validated against a Pydantic schema before being included in the Nemotin prompt; raw database rows are never exposed to the LLM
- **Correlation IDs**: `X-Request-ID` header propagated through logs and responses

### Audit & Integrity
- **8 event types**: AUTH_SUCCESS, AUTH_FAILED, AUTHZ_SUCCESS, AUTHZ_DENIED, INVESTIGATION_STARTED, INVESTIGATION_COMPLETED, EVIDENCE_ADDED, RATE_LIMITED
- **SHA-256 hash chain**: each event stores `previous_hash` and computed `hash`
- `audit_service.verify_chain()` validates entire chain integrity
- Tamper-evident: modifying any event invalidates the chain
- Audit events stored in PostgreSQL with: timestamp, event_type, actor, case_id, details, hash, previous_hash

### Secret Management
- **No hardcoded secrets** in source code
- All credentials from environment variables:
  - `DATABASE_URL` (postgresql+psycopg://user:pass@host:port/db)
  - `NVIDIA_API_KEY` (for Nemotron API access)
  - `JWT_SECRET_KEY` (optional, defaults provided)
  - `CORS_ORIGINS` (empty for production)
- `.env` file git-ignored (`.gitignore`: `.env`, `.env.*`)
- `.env.example` contains placeholder values only
- NVIDIA API key never committed to repository

### Frontend Security
- No API keys or secrets in JavaScript bundles
- No localStorage persistence of sensitive data beyond JWT session token
- All API communication through backend endpoints only
- CORS configured per environment (dev: localhost, prod: empty)
- Role-aware UI: ADMIN features hidden from ANALYST role
- Error states: user-friendly messages; no stack traces exposed

### Data Protection
- No PII stored in application state beyond what's needed for investigation
- Transaction data sanitized before display
- Evidence grounding validates against schema; no raw unvalidated data persisted
- Correlation IDs track requests without exposing sensitive data

### Deployment Security
- Production: `APP_ENV=production` via environment variable
- CORS origins empty by default; configure for actual deployment domain
- No debug mode by default; controllable via `APP_ENV`
- Docker images: minimal slim/alpine bases, production-oriented
- Health checks: `/health` and `/ready` for orchestration