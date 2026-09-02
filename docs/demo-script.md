# RISK-ERA — 60–90 Second Demo Script

Target: 00:00–01:25, no camera, focus on product, synthetic demo data.

| Timestamp | Screen / Action | What to Demonstrate | Narration |
|-----------|-----------------|---------------------|-----------|
| 00:00–00:10 | **Login** as `analyst` / `analyst123` (or `admin` / `admin123`) | Show login, JWT issued, role badge, no secrets exposed | "RISK-ERA is an AI-assisted risk investigation platform built around controlled AI access and auditability." |
| 00:10–00:25 | **Executive Overview** (Dashboard) — 7D/30D/90D, KPIs, Risk/Decision distributions | Real backend analytics: 231 transactions, risk levels, blocked rate, top rules | "The overview shows real PostgreSQL analytics — risk distribution and decision precedence BLOCK > REVIEW > ALLOW." |
| 00:25–00:45 | **Open a suspicious case/alert** — Cases list → Click high-risk case (`CRITICAL`/`BLOCK`) → Show transaction, risk explanation via RuleEngine | Transaction risk explanation: factors → triggered rules → risk score → final decision | "Every decision is explained via the single RuleEngine. Here a high-amount rule triggered BLOCK." |
| 00:45–01:00 | **Investigation Workbench** — Click *Run Investigation* → Show 6 stages (Retrieve context → Evaluate risk → Retrieve evidence → Analyze with Nemotron → Ground findings → Generate recommendation) | Real Nemotron tool calls, evidence grounding (valid/missing), deterministic fallback when unavailable, duration | "The investigator executes only sanitized tools — no direct DB access for the LLM. Evidence is validated before the model sees it." |
| 01:00–01:15 | **Evidence + AI/tool trace** — Evidence Workspace (3 items), Tool Execution Trace (tool name, status, input/output), Timeline (case created → investigation started/completed) | Evidence IDs, tool trace observability, no secrets | "Every tool call is logged and every finding is grounded in evidence." |
| 01:15–01:25 | **Decision + Audit + Health** — Make decision (ACCEPT/MODIFY/REJECT) → Open **Audit Center** → *Verify Chain* → Show **System Health** (all HEALTHY) | SHA-256 hash chain (`prev_hash` linkage, `verify_chain` valid), Health shows Backend, DB, Auth, Tools, Audit Chain HEALTHY | "Every action is hash-chained and verifiable. Health shows real subsystem checks. No Phase 11 — this is Phase 10 verified." |

**Notes:**
- Use existing demo accounts: `analyst` / `analyst123`, `admin` / `admin123` (synthetic, demo-only, no real PII).
- Keep to 60–90 seconds, no camera, no fabricated metrics.
- If Nemotron is unavailable, the UI clearly labels *Deterministic fallback* — do not claim AI output when `model_available: false`.
