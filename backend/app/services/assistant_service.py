from __future__ import annotations

import time
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings

# System prompt for RISK-ERA Assistant — domain-specific, not generic
SYSTEM_PROMPT = """You are the RISK-ERA Assistant, a domain-specific AI assistant for the RISK-ERA fraud/risk operations platform.

RISK-ERA is a transaction investigation system that combines rule-based anomaly detection with NVIDIA Nemotron AI-powered investigation orchestration, delivering explainable risk decisions with full auditability.

Key concepts you must explain accurately:

1. PLATFORM OVERVIEW:
- RISK-ERA detects suspicious transactions via a DSL-driven RuleEngine (BLOCK/REVIEW/ALLOW actions, priority-based, BLOCK > REVIEW > ALLOW precedence).
- Risk levels: 0-25 low (green), 25-60 medium (amber), 60-85 high (red), 85+ critical (deep red).
- Risk scores are deterministic, calculated from transaction amount, customer risk tier, device risk, merchant risk.

2. WORKFLOW: Detect → Investigate → Ground Evidence → Decide → Audit
- RuleEngine flags transaction → Case created (OPEN)
- Analyst reviews case → triggers AI investigation (POST /api/v1/investigation/{case_id}/run)
- Nemotron Investigator executes controlled tools (get_transaction_history, get_customer_profile, get_device_activity) → retrieves sanitized evidence
- Nemotron generates grounded investigation result with recommendation (approve/review/block), confidence, findings, evidence IDs
- Analyst reviews result → ACCEPT/MODIFY/REJECT with reason → Audit event recorded with SHA-256 hash chain
- Audit chain verified via GET /api/v1/audit/verify-chain

3. ENTITIES:
- Transaction: provider_event_id, amount, currency, status, customer/merchant/device, risk_score, decision, triggered_rules
- Case: transaction_id, status (open/in_progress/escalated/closed_approved/closed_denied), assignee, evidence
- Customer: external_id, risk_tier, kyc_status, transactions, risk
- Merchant: name, category_code (MCC), risk_level, transactions
- Device: fingerprint_hash, ip, user_agent, risk_score, transactions
- Fraud Network: Customer↔Device↔Merchant↔Transaction↔Case graph, up to 3 hops, BFS
- Rule: name, dsl_expression, action, priority, enabled
- Alert: transaction_id, case_id, rule_id, severity, priority, status (open/acknowledged/in_progress/resolved/dismissed)
- Investigation: case_id, status, model_provider, risk_assessment, recommendation, tool_calls, evidence_references
- Analytics: Dashboard with KPIs, risk/decision distributions, trends, top rules, risk concentration
- Audit: actor, action, resource_type, resource_id, prev_hash, SHA-256 chain
- Health: Backend API, PostgreSQL, Authentication (JWT), Investigation Tools, Audit Chain

4. ROLES:
- ANALYST and ADMIN via JWT Bearer tokens, 30+ permissions, role-aware UI.

5. GROUNDING RULES:
- Distinguish between general RISK-ERA documentation and live backend data.
- Never invent transaction values, risk scores, case IDs, customer info, alert counts, investigation results, audit events, or health states.
- If live data is unavailable or not provided in context, explicitly say "The required backend data is unavailable" or "No live data for that entity in current context".
- When context includes live data (e.g., case details), use it.
- When answering general questions, use documentation knowledge.

6. STYLE:
- Professional, concise, helpful, fraud-operations tone.
- Use clear hierarchy, avoid excessive formatting.
- Never expose secrets, JWTs, or API keys.

You will be given:
- User question
- Current application context (route, selected IDs, and optionally pre-loaded entity data)
- Relevant live data already fetched from PostgreSQL (when context requires it)

Answer based on the above. If evidence is insufficient, state that explicitly.
"""

# Suggested questions for frontend
SUGGESTED_QUESTIONS = [
    "What is RISK-ERA?",
    "Explain the analyst workflow.",
    "How does risk investigation work?",
    "What does the audit chain verify?",
    "Explain this case.",
]


class AssistantService:
    def __init__(self, db: Session):
        self.db = db
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                # Validate key exists
                api_key = (settings.nvidia_api_key or "").strip()
                if not api_key or not api_key.startswith("nvapi-") or len(api_key) < 40:
                    return None
                self._client = OpenAI(
                    api_key=api_key,
                    base_url=settings.nvidia_base_url,
                )
            except Exception:
                return None
        return self._client

    def _fetch_context_data(self, context: Optional[Dict[str, Any]]) -> tuple[Dict[str, Any], List[str]]:
        """Fetch authoritative data for context-aware questions. Returns (data, sources)."""
        if not context:
            return {}, []

        data: Dict[str, Any] = {}
        sources: List[str] = []

        # Helper to safely fetch
        def try_fetch_case(case_id: str):
            try:
                from app.models import Case
                from sqlalchemy import select
                case_uuid = UUID(case_id)
                case = self.db.execute(select(Case).where(Case.id == case_uuid)).scalar_one_or_none()
                if case:
                    data["case"] = {
                        "id": str(case.id),
                        "status": case.status.value if hasattr(case.status, "value") else str(case.status),
                        "assignee": case.assignee,
                        "created_at": case.created_at.isoformat() if case.created_at else None,
                        "transaction_id": str(case.transaction_id),
                    }
                    sources.append("case")
                    # Also fetch transaction for case
                    try_fetch_transaction(str(case.transaction_id))
            except Exception:
                pass

        def try_fetch_transaction(txn_id: str):
            try:
                from app.models import Transaction
                txn_uuid = UUID(txn_id)
                txn = self.db.execute(select(Transaction).where(Transaction.id == txn_uuid).options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device))).scalar_one_or_none() if hasattr(Transaction, 'customer') else self.db.execute(select(Transaction).where(Transaction.id == txn_uuid)).scalar_one_or_none()
                if txn:
                    # Use risk_explain to get risk if available
                    try:
                        from app.services.risk_explain_service import explain_transaction
                        exp = explain_transaction(self.db, txn.id)
                        if exp:
                            data["transaction_risk"] = {
                                "risk_score": exp["risk_score"],
                                "risk_level": exp["risk_level"],
                                "decision": exp["decision"],
                                "triggered_rules": [r["rule_name"] for r in exp["triggered_rules"]],
                            }
                            sources.append("transaction_risk")
                    except Exception:
                        pass
                    data["transaction"] = {
                        "id": str(txn.id),
                        "provider_event_id": txn.provider_event_id,
                        "amount": str(txn.amount),
                        "currency": txn.currency,
                        "status": txn.status.value if hasattr(txn.status, "value") else str(txn.status),
                    }
                    if "transaction" not in sources:
                        sources.append("transaction")
            except Exception:
                pass

        def try_fetch_customer(cust_id: str):
            try:
                from app.models import Customer
                cust_uuid = UUID(cust_id)
                cust = self.db.execute(select(Customer).where(Customer.id == cust_uuid)).scalar_one_or_none()
                if cust:
                    data["customer"] = {
                        "id": str(cust.id),
                        "external_id": cust.external_id,
                        "risk_tier": cust.risk_tier,
                        "kyc_status": cust.kyc_status,
                    }
                    sources.append("customer")
            except Exception:
                pass

        def try_fetch_merchant(merch_id: str):
            try:
                from app.models import Merchant
                merch_uuid = UUID(merch_id)
                merch = self.db.execute(select(Merchant).where(Merchant.id == merch_uuid)).scalar_one_or_none()
                if merch:
                    data["merchant"] = {
                        "id": str(merch.id),
                        "name": merch.name,
                        "category_code": merch.category_code,
                        "risk_level": merch.risk_level,
                    }
                    sources.append("merchant")
            except Exception:
                pass

        def try_fetch_device(dev_id: str):
            try:
                from app.models import Device
                dev_uuid = UUID(dev_id)
                dev = self.db.execute(select(Device).where(Device.id == dev_uuid)).scalar_one_or_none()
                if dev:
                    data["device"] = {
                        "id": str(dev.id),
                        "fingerprint_hash": dev.fingerprint_hash[:16] + "…" if dev.fingerprint_hash else None,
                        "ip": dev.ip,
                    }
                    sources.append("device")
            except Exception:
                pass

        # Extract IDs from context
        route = context.get("route") or context.get("Route")
        case_id = context.get("caseId") or context.get("case_id")
        txn_id = context.get("transactionId") or context.get("transaction_id")
        cust_id = context.get("customerId") or context.get("customer_id")
        merch_id = context.get("merchantId") or context.get("merchant_id")
        dev_id = context.get("deviceId") or context.get("device_id")

        # Also handle extra pre-loaded data
        extra = context.get("extra") or {}
        if extra:
            data["extra_context"] = extra
            sources.append("extra_context")

        if case_id:
            try_fetch_case(str(case_id))
        if txn_id:
            try_fetch_transaction(str(txn_id))
        if cust_id:
            try_fetch_customer(str(cust_id))
        if merch_id:
            try_fetch_merchant(str(merch_id))
        if dev_id:
            try_fetch_device(str(dev_id))

        # If route is provided but no IDs, add route as source for general context
        if route and not sources:
            data["current_route"] = route
            sources.append("route")

        return data, list(set(sources))

    def _is_contextual_question(self, message: str) -> bool:
        low = message.lower()
        keywords = ["this case", "this transaction", "this customer", "this merchant", "this device", "explain this", "current case", "selected case"]
        return any(k in low for k in keywords)

    def generate_answer(self, message: str, context: Optional[Dict[str, Any]], user: str) -> Dict[str, Any]:
        # Sanitize message
        msg = message.strip()
        if not msg:
            return {
                "answer": "Please provide a question about RISK-ERA.",
                "grounded": False,
                "sources": ["documentation"],
                "context_used": context or {},
            }

        # Check if contextual question but no context data
        is_contextual = self._is_contextual_question(msg)
        context_data, sources = self._fetch_context_data(context)

        # If contextual but no data fetched and no IDs, inform unavailable
        has_ids = any(context and context.get(k) for k in ["caseId", "case_id", "transactionId", "transaction_id", "customerId", "customer_id", "merchantId", "merchant_id", "deviceId", "device_id"]) if context else False
        if is_contextual and not context_data:
            return {
                "answer": "The required backend data is unavailable for that question. Please select a case, transaction, customer, merchant, or device first, or ensure the relevant page has loaded the entity. Then ask again (e.g., 'Explain this case').",
                "grounded": False,
                "sources": ["documentation"],
                "context_used": context or {},
            }

        # Try AI provider
        client = self._get_client()
        if client is None:
            # Fallback to rule-based answers for general questions when AI unavailable
            return self._fallback_answer(msg, context_data, sources, context)

        try:
            # Build messages
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
            ]
            # Add context data as system context if available
            if context_data:
                messages.append({"role": "system", "content": f"Live backend-derived context for current question (grounded, do not invent beyond this): {context_data}"})
            if context:
                messages.append({"role": "system", "content": f"Application context: {context}"})
            messages.append({"role": "user", "content": msg})

            # Call Nemotron via OpenAI client
            resp = client.chat.completions.create(
                model=settings.nemotron_model,
                messages=messages,
                temperature=0.3,
                max_tokens=800,
                timeout=15,
            )
            content = resp.choices[0].message.content or ""
            # Basic grounding check: ensure we don't hallucinate IDs not in context
            # If content contains a UUID-like string not in context_data, we could flag but for now trust
            grounded = bool(context_data) or "RISK-ERA" in content
            # Determine sources
            if not sources:
                sources = ["documentation"]
                grounded = False
            else:
                grounded = True

            # Ensure we distinguish
            # If the answer is about live data but we had no live data, mark not grounded
            if is_contextual and not context_data:
                grounded = False
                sources = ["documentation"]

            return {
                "answer": content.strip() or "RISK-ERA Assistant is temporarily unavailable. Please try again.",
                "grounded": grounded,
                "sources": sources,
                "context_used": context or {},
            }
        except Exception as e:
            # Log and return fallback
            # Check if it's an auth error, we should not expose
            return {
                "answer": "RISK-ERA Assistant is temporarily unavailable. Please try again.",
                "grounded": False,
                "sources": ["documentation"],
                "context_used": context or {},
            }

    def _fallback_answer(self, message: str, context_data: Dict[str, Any], sources: List[str], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        low = message.lower()
        # Simple rule-based fallback for when AI unavailable
        if "what is risk-era" in low or "what is risk era" in low:
            ans = "RISK-ERA is a transaction investigation system that combines rule-based anomaly detection (RuleEngine with BLOCK/REVIEW/ALLOW, risk levels low/medium/high/critical) with NVIDIA Nemotron AI-powered investigation orchestration, delivering explainable risk decisions with full SHA-256 auditability. Workflow: Detect → Investigate → Ground Evidence → Decide → Audit."
            src = ["documentation"]
            grounded = False
        elif "analyst workflow" in low or "explain the analyst" in low:
            ans = "Analyst workflow: 1) Login (JWT) → 2) Executive Overview (Dashboard analytics) → 3) Cases list → 4) Open Case → 5) Review transaction/risk (DecisionExplanation) → 6) Check evidence → 7) Run Investigation (POST /api/v1/investigation/{case_id}/run, 6 stages) → 8) Review tool trace and findings → 9) Make decision (ACCEPT/MODIFY/REJECT) → 10) Audit trail verified via SHA-256 chain."
            src = ["documentation"]
            grounded = False
        elif "risk investigation" in low or "how does risk" in low:
            ans = "Risk investigation: RuleEngine evaluates transaction factors (amount, customer_risk_tier, device_risk_score, merchant_category_code, etc.) against DSL rules, calculates risk_score 0-100 and decision via BLOCK>REVIEW>ALLOW precedence, then Nemotron Investigator executes controlled tools (get_transaction_history, get_customer_profile, get_device_activity) to gather sanitized evidence, grounds findings, and produces a recommendation with confidence. If Nemotron is unavailable, deterministic fallback is used and clearly labeled."
            src = ["documentation"]
            grounded = False
        elif "audit chain" in low or "what does the audit" in low:
            ans = "The audit chain is an immutable SHA-256 hash chain (actor, action, resource_type, resource_id, before/after, prev_hash, created_at). Each event's prev_hash links to the previous event's hash. GET /api/v1/audit/verify-chain checks the chain and returns valid true/false with checked counts. It is used to verify that no audit event has been tampered with."
            src = ["documentation"]
            grounded = False
        elif "explain this case" in low:
            if "case" in context_data:
                case = context_data["case"]
                txn = context_data.get("transaction", {})
                ans = f"Current case {case['id'][:8]} is {case['status']} (created {case['created_at']}). Transaction {txn.get('provider_event_id', '—')} amount {txn.get('amount', '—')} {txn.get('currency', '')} with risk from RuleEngine. Use the Investigation Workbench to see the six stages, evidence, tool trace, and timeline. The required backend data for this case is available and grounded."
                src = sources
                grounded = True
            else:
                ans = "The required backend data is unavailable for that question. Please open a case first (e.g., from Cases list) so the assistant can use the current case context."
                src = ["documentation"]
                grounded = False
        else:
            # Generic fallback
            ans = "RISK-ERA is a fraud/risk operations platform. Ask about: risk operations, transactions, cases, customers, merchants, devices, fraud network (3-hop BFS), rules (DSL, priority), alerts (severity/priority), investigations (6 stages), analytics (KPIs, trends), audit chain (SHA-256), or system health. For context-specific questions like 'Explain this case', please select an entity first."
            src = ["documentation"]
            grounded = bool(context_data)
            if grounded:
                src = sources
        return {
            "answer": ans,
            "grounded": grounded,
            "sources": src,
            "context_used": context or {},
        }
