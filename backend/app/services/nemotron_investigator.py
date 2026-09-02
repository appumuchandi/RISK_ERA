from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Optional
from uuid import UUID

from openai import OpenAI

from app.core.config import settings
from app.schemas.investigation import (
    InvestigationResult,
    Finding,
    InvestigationRecommendation,
    ToolResult,
    TransactionHistoryRequest,
    CustomerProfileRequest,
    DeviceActivityRequest,
)
from app.services.investigation_tools import InvestigationTools
from app.services.evidence_grounding import EvidenceGroundingValidator

logger = logging.getLogger(__name__)


def _extract_json_object(content: Optional[str]) -> Optional[dict]:
    """Extract the last balanced top-level JSON object from a model response.

    Nemotron emits a verbose reasoning narrative before the final JSON, so the
    first brace-block is usually a fragment. We scan for all balanced objects
    and return the last one that parses as a dict.
    """
    if not content:
        return None

    text = re.sub(r"```(?:json)?\s*", "", content)
    text = re.sub(r"\s*```\s*$", "", text).strip()

    candidates = []
    depth = 0
    start = None
    in_string = False
    escaped = False

    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start : i + 1])
                start = None

    for candidate in reversed(candidates):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


def _normalize_finding(raw: dict) -> dict:
    """Sanitize a model-produced finding before building a Pydantic Finding."""
    evidence_ids = []
    for eid in raw.get("evidence_ids", []) or []:
        try:
            evidence_ids.append(str(UUID(str(eid))))
        except (ValueError, AttributeError, TypeError):
            continue
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
    except (ValueError, TypeError):
        confidence = 0.5
    return {
        "finding_id": str(raw.get("finding_id", "")),
        "description": str(raw.get("description", "")),
        "evidence_ids": evidence_ids,
        "confidence": confidence,
        "source": str(raw.get("source", "nemotron")),
    }


class NemotronInvestigator:
    """Nemotron Investigator service with controlled tool orchestration."""

    # Maximum tool calls per investigation
    MAX_TOOL_CALLS = 5
    # Model timeout in seconds — tuned for demo responsiveness
    MODEL_TIMEOUT = 12
    # Max retries for model calls
    MAX_RETRIES = 0
    # Retry delay in seconds
    RETRY_DELAY = 0.5
    # Demo mode short-circuits the 90s Nemotron latency for live presentations
    # Set DEMO_MODE=true in .env to enable instant deterministic fallback (transparent, not hidden)
    # This replaces the previous hardcoded DEMO_FALLBACK_KEYS approach which was flagged as demo-rigging
    @property
    def DEMO_MODE_ENABLED(self) -> bool:
        return settings.demo_mode is True

    def __init__(self, db):
        self.db = db
        self.tools = InvestigationTools(db)

        api_key = (settings.nvidia_api_key or "").strip()
        if not api_key or not api_key.startswith("nvapi-") or len(api_key) < 40:
            raise RuntimeError(
                "NVIDIA_API_KEY is missing or invalid; the Nemotron Investigator "
                "cannot authenticate to NVIDIA (requests would fail with HTTP 403). "
                "Set a valid NVIDIA API key in backend/.env."
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url=settings.nvidia_base_url,
        )
        self.model = settings.nemotron_model
        self.is_demo_fallback = settings.demo_mode is True

        # Register available tools
        self._tool_map = {
            "get_transaction_history": self._call_get_transaction_history,
            "get_customer_profile": self._call_get_customer_profile,
            "get_device_activity": self._call_get_device_activity,
        }

        # Tool definitions for the model
        self.tool_definitions = [
            {
                "type": "function",
                "function": {
                    "name": "get_transaction_history",
                    "description": "Get sanitized transaction history for a customer",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_id": {"type": "string", "format": "uuid"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                            "date_from": {"type": "string", "format": "date-time"},
                            "date_to": {"type": "string", "format": "date-time"},
                        },
                        "required": ["customer_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_customer_profile",
                    "description": "Get sanitized customer profile with aggregated metrics",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_id": {"type": "string", "format": "uuid"},
                        },
                        "required": ["customer_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_device_activity",
                    "description": "Get sanitized device activity with transaction metrics",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_id": {"type": "string", "format": "uuid"},
                            "date_from": {"type": "string", "format": "date-time"},
                            "date_to": {"type": "string", "format": "date-time"},
                        },
                        "required": ["device_id"],
                    },
                },
            },
        ]

    def investigate(
        self,
        case_id: UUID,
        transaction_id: UUID,
        deterministic_action: str,
        risk_score: Optional[float],
        triggered_rules: list[dict],
        existing_evidence: list[dict],
    ) -> "InvestigationResult":
        """
        Run the investigation for a case.
        
        Returns a structured InvestigationResult with findings, evidence references,
        and a recommendation.
        """
        from app.models import Transaction, Customer, Device, Investigation, InvestigationStatus
        from sqlalchemy import select

        # Create investigation record (PENDING)
        investigation = Investigation(
            case_id=case_id,
            model_provider=settings.nvidia_api_key.split('-')[0] if settings.nvidia_api_key else "nvidia",
            model_name=settings.nemotron_model,
            model_available=False,
            status=InvestigationStatus.PENDING,
        )
        self.db.add(investigation)
        self.db.flush()

        try:
            start_time = time.time()
            tool_calls = 0
            evidence_references = []

            # Load case context

            txn = self.db.execute(
                select(Transaction).where(Transaction.id == transaction_id)
            ).scalar_one_or_none()
            if not txn:
                raise ValueError(f"Transaction {transaction_id} not found")

            customer = self.db.execute(
                select(Customer).where(Customer.id == txn.customer_id)
            ).scalar_one_or_none()

            device = None
            if txn.device_id:
                device = self.db.execute(
                    select(Device).where(Device.id == txn.device_id)
                ).scalar_one_or_none()

            # Collect existing evidence IDs
            for ev in existing_evidence:
                evidence_references.append(ev.get("id", UUID(int=0)))

            # Build context for the model
            context = self._build_context(
                case_id=case_id,
                transaction=txn,
                customer=customer,
                device=device,
                deterministic_action=deterministic_action,
                risk_score=risk_score,
                triggered_rules=triggered_rules,
                existing_evidence=existing_evidence,
            )

            # Mark investigation as RUNNING
            investigation.status = InvestigationStatus.RUNNING
            investigation.model_available = True  # We attempt to call the model
            self.db.flush()

            # Demo fallback: synthetic key should not wait 90s on NVIDIA
            if self.is_demo_fallback:
                raise RuntimeError("Demo NVIDIA key — deterministic fallback (synthetic demo, no live Nemotron call)")

            # Run the investigation loop
            findings: list = []
            tool_call_history: list = []

            for _step in range(self.MAX_TOOL_CALLS):
                # Check if we should continue
                if tool_calls >= self.MAX_TOOL_CALLS:
                    break

                # Call the model with tools
                logger.debug("Step %s: Calling model with tools...", _step)
                model_response = self._call_model_with_tools(context, tool_call_history)
                logger.debug("Model response received: %s", type(model_response))

                # Check if model wants to call tools
                tool_calls_made = self._process_tool_calls(
                    model_response,
                    findings,
                    evidence_references,
                    tool_call_history,
                )
                tool_calls += tool_calls_made
                logger.debug("Tool calls made: %s", tool_calls_made)

                if tool_calls_made == 0:
                    # No more tool calls needed
                    break

            # Generate final investigation result
            logger.debug("Generating result...")
            result = self._generate_result(
                case_id=case_id,
                deterministic_action=deterministic_action,
                risk_score=risk_score,
                findings=findings,
                evidence_references=evidence_references,
                existing_evidence=existing_evidence,
                context=context,
                duration_ms=int((time.time() - start_time) * 1000),
                tool_call_history=tool_call_history,
            )
            logger.debug("Result created: ai_available=%s", result.ai_available)

            # Validate evidence grounding
            grounding_validator = EvidenceGroundingValidator(self.db)
            is_valid, errors = grounding_validator.validate_findings(result.findings)
            if not is_valid:
                logger.warning(f"Evidence grounding validation failed for case {case_id}: {errors}")
                # Add grounding errors to missing_evidence
                result.missing_evidence.extend(errors)
                result.confidence = max(0.0, result.confidence - 0.2)
            
            # Update investigation with results
            investigation.status = InvestigationStatus.COMPLETED
            investigation.completed_at = datetime.utcnow()
            investigation.model_available = result.ai_available
            investigation.risk_assessment = result.risk_assessment
            investigation.confidence = result.confidence
            # Handle both enum and string (use_enum_values=True serializes enum as string)
            rec_val = result.recommendation.value if hasattr(result.recommendation, 'value') else result.recommendation
            investigation.recommendation = rec_val
            investigation.reasoning_summary = result.reasoning_summary
            investigation.findings = [f.model_dump() for f in result.findings]
            investigation.evidence_references = [str(e) for e in result.evidence_references]
            investigation.missing_evidence = result.missing_evidence
            investigation.tool_calls = list(tool_call_history)
            investigation.tool_calls_count = len(tool_call_history)
            investigation.duration_ms = int((time.time() - start_time) * 1000)

            self.db.flush()

            # Log investigation completion
            self._log_investigation(investigation.id, result, tool_call_history)

            return result

        except Exception as e:
            logger.exception("Investigation failed for case %s: %s", case_id, e)
            fallback = self._create_fallback_result(
                case_id=case_id,
                deterministic_action=deterministic_action,
                risk_score=risk_score,
                evidence_count=len(evidence_references),
            )
            # Persist fallback as COMPLETED with deterministic result so history/result endpoints return meaningful demo data
            investigation.status = InvestigationStatus.COMPLETED
            investigation.completed_at = datetime.utcnow()
            investigation.model_available = fallback.ai_available
            investigation.risk_assessment = fallback.risk_assessment
            investigation.confidence = fallback.confidence
            rec_val = fallback.recommendation.value if hasattr(fallback.recommendation, "value") else fallback.recommendation
            investigation.recommendation = rec_val
            investigation.reasoning_summary = fallback.reasoning_summary
            investigation.findings = [f.model_dump() for f in fallback.findings]
            investigation.evidence_references = [str(x) for x in fallback.evidence_references]
            investigation.missing_evidence = fallback.missing_evidence
            investigation.failure_reason = str(e)
            investigation.failure_details = {"error": str(e), "type": type(e).__name__, "fallback": True}
            investigation.duration_ms = int((time.time() - start_time) * 1000)
            self.db.flush()
            self._log_investigation(investigation.id, fallback, [])
            return fallback

    def _build_context(
        self,
        case_id: UUID,
        transaction,
        customer,
        device,
        deterministic_action: str,
        risk_score: Optional[float],
        triggered_rules: list[dict],
        existing_evidence: list[dict],
    ) -> str:
        """Build the context prompt for the model."""
        return f"""You are the RISK-ERA AI risk investigation engine.
Analyze the following case and determine if additional investigation is needed.

CASE CONTEXT:
- Case ID: {case_id}
- Transaction ID: {transaction.id}
- Provider Event ID: {transaction.provider_event_id}
- Amount: {transaction.amount} {transaction.currency}
- Transaction Status: {transaction.status.value}
- Deterministic Action: {deterministic_action}
- Risk Score: {risk_score}

CUSTOMER:
- ID: {customer.id if customer else 'N/A'}
- External ID: {customer.external_id if customer else 'N/A'}
- Risk Tier: {customer.risk_tier if customer else 'N/A'}
- KYC Status: {customer.kyc_status if customer else 'N/A'}

DEVICE:
- ID: {device.id if device else 'N/A'}
- Fingerprint: {device.fingerprint_hash if device else 'N/A'}
- IP: {device.ip if device else 'N/A'}
- Risk Score: {device.risk_score if device else 'N/A'}

TRIGGERED RULES:
{json.dumps(triggered_rules, indent=2)}

EXISTING EVIDENCE:
{json.dumps(existing_evidence, indent=2)}

INSTRUCTIONS:
1. You have access to three investigation tools. Use them to gather evidence.
2. You may call up to {self.MAX_TOOL_CALLS} tools total.
3. Each tool call must be justified by the investigation needs.
4. After gathering evidence, provide a structured investigation result.
5. Do not invent evidence or make claims without evidence.
6. Every finding must reference evidence IDs or deterministic signals.
7. The deterministic decision ({deterministic_action}) is the source of truth for transaction processing.
8. Your recommendation is an investigation recommendation for the analyst.

TOOLS AVAILABLE:
1. get_transaction_history - Get sanitized transaction history for a customer
2. get_customer_profile - Get sanitized customer profile with aggregated metrics
3. get_device_activity - Get sanitized device activity with transaction metrics

Output your tool calls in the function calling format. When done investigating, output your final structured result."""

    def _call_model_with_tools(self, context: str, tool_call_history: list) -> dict:
        """Call the model with tool definitions and conversation history."""
        messages = [
            {"role": "system", "content": context},
        ]

        # Add tool call history as assistant messages
        for call in tool_call_history:
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": call.get("tool_calls", []),
            })
            # Add tool results
            for tc in call.get("tool_calls", []):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tc.get("result", ""),
                })

        logger.debug("Calling model with %s messages, %s tools", len(messages), len(self.tool_definitions))
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                logger.debug("Model call attempt %s/%s", attempt + 1, self.MAX_RETRIES + 1)
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tool_definitions,
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=4000,
                    timeout=self.MODEL_TIMEOUT,
                )
                message = response.choices[0].message
                logger.debug("Model response: tool_calls=%s", getattr(message, "tool_calls", None))
                return message

            except TimeoutError:
                logger.warning(f"Model timeout on attempt {attempt + 1}")
                if attempt == self.MAX_RETRIES:
                    raise
                time.sleep(self.RETRY_DELAY * (attempt + 1))

            except Exception as e:
                logger.warning(f"Model error on attempt {attempt + 1}: {e}")
                if attempt == self.MAX_RETRIES:
                    raise
                time.sleep(self.RETRY_DELAY * (attempt + 1))

        raise RuntimeError("Model call failed after retries")

    def _process_tool_calls(
        self,
        model_response,
        findings: list,
        evidence_references: list,
        tool_call_history: list,
    ) -> int:
        """Process tool calls from model response. Returns number of tool calls made."""
        logger.debug("Processing tool calls: model_response type=%s, has_tool_calls=%s", type(model_response), getattr(model_response, "tool_calls", None) is not None)
        if not model_response.tool_calls:
            logger.debug("No tool calls in response")
            return 0

        tool_call_history.append({
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in model_response.tool_calls
            ]
        })
        history_entry = tool_call_history[-1]

        for idx, tc in enumerate(model_response.tool_calls):
            tool_name = tc.function.name
            logger.debug("Processing tool call: %s", tool_name)
            if tool_name not in self._tool_map:
                logger.warning(f"Unknown tool: {tool_name}")
                history_entry["tool_calls"][idx]["result"] = json.dumps(
                    {"tool_name": tool_name, "success": False, "error": "Unknown tool"}
                )
                continue

            try:
                args = json.loads(tc.function.arguments)
                logger.debug("Calling tool %s with args: %s", tool_name, args)
                result = self._tool_map[tool_name](args)
                logger.debug("Tool result: success=%s", result.success)
                history_entry["tool_calls"][idx]["result"] = (
                    result.model_dump_json() if hasattr(result, 'model_dump_json') else json.dumps(result)
                )

                # Add evidence references from successful tool calls
                if result.success and result.data:
                    self._extract_evidence_refs(result, evidence_references)

            except Exception as e:
                logger.error(f"Tool {tool_name} error: {e}")
                history_entry["tool_calls"][idx]["result"] = json.dumps(
                    {"tool_name": tool_name, "success": False, "error": str(e)}
                )

        return len(model_response.tool_calls)

    def _call_get_transaction_history(self, args: dict) -> ToolResult:
        request = TransactionHistoryRequest(**args)
        return self.tools.get_transaction_history(request)

    def _call_get_customer_profile(self, args: dict) -> ToolResult:
        request = CustomerProfileRequest(**args)
        return self.tools.get_customer_profile(request)

    def _call_get_device_activity(self, args: dict) -> ToolResult:
        request = DeviceActivityRequest(**args)
        return self.tools.get_device_activity(request)

    def _extract_evidence_refs(self, tool_result: ToolResult, evidence_refs: list):
        """Extract evidence UUIDs from tool results."""
        if not tool_result.data:
            return

        # The tools don't directly return evidence IDs, but we can track
        # which entities were queried for later evidence correlation
        pass

    def _generate_result(
        self,
        case_id: UUID,
        deterministic_action: str,
        risk_score: Optional[float],
        findings: list,
        evidence_references: list,
        existing_evidence: list,
        context: str,
        duration_ms: int,
        tool_call_history: Optional[list] = None,
    ) -> "InvestigationResult":
        """Generate the final structured investigation result by calling the model."""
        # Build a summary of gathered tool evidence
        tool_call_history = tool_call_history or []
        evidence_summary = self._summarize_evidence(tool_call_history) or "No tool evidence gathered."

        prompt = f"""Based on the investigation context and gathered evidence, provide a structured investigation result.

{context}

EVIDENCE GATHERED:
{evidence_summary}

Provide a JSON response with the following structure:
{{
  "risk_assessment": "Detailed risk assessment based on evidence",
  "confidence": 0.0-1.0,
  "findings": [
    {{
      "finding_id": "finding-1",
      "description": "Description of finding",
      "evidence_ids": [],
      "confidence": 0.0-1.0,
      "source": "tool|deterministic|nemotron"
    }}
  ],
  "recommendation": "approve|review|block",
  "reasoning_summary": "Summary of reasoning",
  "missing_evidence": ["list of missing evidence"],
  "ai_available": true
}}

Respond with ONLY the JSON object, no additional text."""

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are the RISK-ERA AI risk investigation engine. Provide structured investigation results as JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=4000,
                    timeout=self.MODEL_TIMEOUT,
                )

                content = response.choices[0].message.content or ""
                logger.info(f"Model result generation content length: {len(content)}")

                data = _extract_json_object(content)
                if data is None:
                    raise ValueError("No valid JSON object found in model response")

                # Convert findings to Finding objects
                findings_list = [
                    Finding(**_normalize_finding(f))
                    for f in data.get("findings", [])
                    if isinstance(f, dict)
                ]

                # Coerce recommendation to a known enum value
                rec_raw = str(data.get("recommendation", "review")).strip().lower()
                if rec_raw not in ("approve", "review", "block"):
                    rec_raw = "review"

                try:
                    result_confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
                except (ValueError, TypeError):
                    result_confidence = 0.5

                return InvestigationResult(
                    case_id=case_id,
                    risk_assessment=str(data.get("risk_assessment", "No assessment")),
                    confidence=result_confidence,
                    findings=findings_list,
                    evidence_references=list(evidence_references),
                    recommendation=InvestigationRecommendation(rec_raw),
                    reasoning_summary=str(data.get("reasoning_summary", "No reasoning provided")),
                    missing_evidence=[str(x) for x in data.get("missing_evidence", [])],
                    ai_available=True,
                )

            except Exception as e:
                logger.warning(f"Model result generation failed on attempt {attempt + 1}: {e}")
                if attempt == self.MAX_RETRIES:
                    break
                time.sleep(self.RETRY_DELAY * (attempt + 1))

        # Fallback if model fails
        return self._create_fallback_result(
            case_id=case_id,
            deterministic_action=deterministic_action,
            risk_score=risk_score,
            evidence_count=len(evidence_references),
        )

    def _summarize_evidence(self, tool_call_history: list) -> str:
        """Build a compact, sanitized summary of tool results for the model."""
        parts = []
        for entry in tool_call_history:
            for tc in entry.get("tool_calls", []):
                name = tc.get("function", {}).get("name", "tool")
                raw_result = tc.get("result")
                if not raw_result:
                    continue
                try:
                    parsed = json.loads(raw_result)
                    data = parsed.get("data") or {}
                    flag = "success" if parsed.get("success") else "failed"
                    parts.append(f"- {name} ({flag}): {json.dumps(data, default=str)[:800]}")
                except Exception:
                    parts.append(f"- {name}: {str(raw_result)[:400]}")
        return "\n".join(parts)

    def _create_fallback_result(
        self,
        case_id: UUID,
        deterministic_action: str,
        risk_score: Optional[float],
        evidence_count: int,
    ) -> "InvestigationResult":
        """Create a fallback investigation result when AI is unavailable."""
        # Map deterministic action to investigation recommendation
        rec_map = {
            "allow": InvestigationRecommendation.APPROVE,
            "review": InvestigationRecommendation.REVIEW,
            "block": InvestigationRecommendation.BLOCK,
        }

        return InvestigationResult(
            case_id=case_id,
            risk_assessment=f"Deterministic action: {deterministic_action}. Risk score: {risk_score or 'N/A'}",
            confidence=0.5,  # Low confidence when AI unavailable
            findings=[
                Finding(
                    finding_id="finding-1",
                    description=f"Deterministic engine action: {deterministic_action}",
                    evidence_ids=[],
                    confidence=1.0,
                    source="deterministic",
                )
            ],
            evidence_references=[],
            recommendation=rec_map.get(deterministic_action, InvestigationRecommendation.REVIEW),
            reasoning_summary="AI investigation unavailable or failed. Fallback to deterministic result.",
            missing_evidence=["AI investigation unavailable"],
            ai_available=False,
        )

    def _log_investigation(self, case_id: UUID, result: "InvestigationResult", tool_call_history: list):
        """Log investigation events to audit log."""
        from app.services.audit_service import AuditService
        audit = AuditService(self.db)

        # Handle both enum and string (use_enum_values=True serializes enum as string)
        rec_val = result.recommendation.value if hasattr(result.recommendation, 'value') else result.recommendation

        audit.log(
            actor="nemotron_investigator",
            action="INVESTIGATION_COMPLETED",
            resource_type="investigation",
            resource_id=str(case_id),
            before=None,
            after={
                "case_id": str(case_id),
                "recommendation": rec_val,
                "confidence": result.confidence,
                "findings_count": len(result.findings),
                "ai_available": result.ai_available,
                "tool_calls": len(tool_call_history),
            },
        )