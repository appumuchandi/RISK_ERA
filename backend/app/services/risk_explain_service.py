from __future__ import annotations

from decimal import Decimal
from typing import Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Transaction, Rule
from app.models.transaction import TransactionStatus
from app.schemas.transaction import TransactionAction
from app.services.rule_engine import RuleEngine, Rule as RuleEngineRule, evaluate_expression, parse_expression


def _get_enabled_rules(db: Session) -> List[RuleEngineRule]:
    rows = db.execute(select(Rule).where(Rule.enabled).order_by(Rule.priority)).scalars().all()
    return [
        RuleEngineRule(
            id=r.id,
            name=r.name,
            dsl_expression=r.dsl_expression,
            action=TransactionAction(r.action.value),
            priority=r.priority,
            enabled=r.enabled,
            version=r.version,
        )
        for r in rows
    ]


def _get_all_rules(db: Session) -> List[RuleEngineRule]:
    # For evaluated_rules we want all enabled rules? Or all rules? Spec says evaluated_rules should be all configured rules evaluated.
    # Use enabled only, as disabled should not affect decision.
    return _get_enabled_rules(db)


def _risk_level_from_score(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def explain_transaction(db: Session, transaction_id: UUID) -> dict | None:
    txn = db.execute(
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))
    ).scalar_one_or_none()
    if not txn:
        return None

    # Build factors exactly as RuleEngine uses
    customer = txn.customer
    merchant = txn.merchant
    device = txn.device

    factors = {
        "amount": txn.amount,
        "currency": txn.currency,
        "customer_risk_tier": customer.risk_tier if customer else "standard",
        "customer_kyc_status": customer.kyc_status if customer else "pending",
        "device_risk_score": float(device.risk_score) if device and device.risk_score is not None else None,
        "merchant_category_code": merchant.category_code if merchant else "",
        "merchant_risk_level": merchant.risk_level if merchant else "standard",
    }

    # Evaluate with RuleEngine
    rules = _get_all_rules(db)
    engine = RuleEngine(rules)

    # Prepare evaluated list
    evaluated: List[dict] = []
    triggered: List[dict] = []

    # We need to evaluate each rule individually to know matched
    for rule in rules:
        # Use engine's safe evaluation
        try:
            matched = engine._evaluate_dsl(rule.dsl_expression, factors)  # type: ignore[attr-defined]
        except Exception:
            matched = False

        # Build explanation string
        # Show factor values that are relevant to this rule's expression
        # Simple: if matched, explain which condition satisfied
        # We can parse which variables appear in expression
        # For now, provide generic explanation with actual factor values
        # To make it transparent, include factor snapshot
        exp_parts = []
        # Determine which factors appear in dsl
        dsl_lower = rule.dsl_expression.lower()
        for key in ["amount", "customer_risk_tier", "customer_kyc_status", "device_risk_score", "merchant_category_code", "merchant_risk_level", "currency"]:
            if key in dsl_lower:
                exp_parts.append(f"{key}={factors.get(key)!r}")

        if matched:
            explanation = f"Matched: {rule.dsl_expression} — " + (", ".join(exp_parts) if exp_parts else "condition satisfied")
        else:
            explanation = f"Not matched: {rule.dsl_expression} — " + (", ".join(exp_parts) if exp_parts else "condition not satisfied")

        item = {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "action": rule.action.value,
            "priority": rule.priority,
            "matched": matched,
            "explanation": explanation,
            "dsl_expression": rule.dsl_expression,
            "condition": rule.dsl_expression,
        }
        evaluated.append(item)
        if matched:
            triggered.append(item)

    # Sort evaluated by priority asc for determinism (same as engine)
    evaluated.sort(key=lambda x: x["priority"])
    triggered.sort(key=lambda x: x["priority"])

    # Get final decision and risk score via engine
    data_for_engine = {
        "amount": factors["amount"],
        "currency": factors["currency"],
        "customer_risk_tier": factors["customer_risk_tier"],
        "customer_kyc_status": factors["customer_kyc_status"],
        "device_risk_score": factors["device_risk_score"],
        "merchant_category_code": factors["merchant_category_code"],
        "merchant_risk_level": factors["merchant_risk_level"],
    }
    result = engine.evaluate(data_for_engine)
    risk_score = float(result.risk_score) if result.risk_score is not None else 0.0
    risk_level = _risk_level_from_score(risk_score)
    decision = result.final_action.value

    # Decision reason with precedence
    if not triggered:
        decision_reason = "No configured rule triggered for this transaction. Default decision is ALLOW with risk score 0."
    else:
        # Find highest precedence triggered
        # BLOCK > REVIEW > ALLOW
        max_prec = max({"block": 3, "review": 2, "allow": 1}.get(t["action"], 0) for t in triggered)
        top_action = next(a for a, p in [("block", 3), ("review", 2), ("allow", 1)] if p == max_prec)
        top_rules = [t for t in triggered if t["action"] == top_action]
        top_names = ", ".join([t["rule_name"] for t in top_rules])
        if top_action == "block":
            decision_reason = f"Rule(s) {top_names} triggered BLOCK. BLOCK takes precedence over REVIEW and ALLOW, therefore the final decision is BLOCK."
        elif top_action == "review":
            # Check if any block existed? No, because max is review
            if any(t["action"] == "block" for t in triggered):
                decision_reason = f"Rule(s) triggered BLOCK but none, final is REVIEW."
            else:
                decision_reason = f"Rule(s) {top_names} triggered REVIEW. No BLOCK rule triggered, so final decision is REVIEW (takes precedence over ALLOW)."
        else:
            decision_reason = f"Rule(s) {top_names} triggered ALLOW. No BLOCK or REVIEW triggered, final decision is ALLOW."

        # More precise: if triggered contains multiple actions, explain precedence
        if len(set(t["action"] for t in triggered)) > 1:
            decision_reason += f" Triggered actions were {', '.join(sorted(set(t['action'] for t in triggered)))}."

    # Score breakdown as per RuleEngine._calculate_risk_score
    # Recompute factors for transparency
    amount = factors["amount"]
    amount_f = float(amount) if isinstance(amount, Decimal) else float(amount)
    amount_factor = min(amount_f / 50000.0, 0.3)
    customer_factor = {"low": -0.1, "standard": 0.0, "high": 0.15, "critical": 0.25}.get(factors["customer_risk_tier"], 0.0)
    device_factor = float(factors["device_risk_score"]) * 0.2 if factors["device_risk_score"] is not None else 0.0
    merchant_factor = {"low": -0.05, "standard": 0.0, "high": 0.1, "critical": 0.2}.get(factors["merchant_risk_level"], 0.0)
    max_prec = max({"block": 3, "review": 2, "allow": 1}.get(t["action"], 0) for t in triggered) if triggered else 0
    base_score = (max_prec / 3.0) * 40.0 if triggered else 0.0

    score_breakdown = {
        "base_score": round(base_score, 2),
        "amount": str(amount),
        "amount_factor": round(amount_factor * 100, 2),
        "customer_risk_tier": factors["customer_risk_tier"],
        "customer_factor": round(customer_factor * 100, 2),
        "device_risk_score": factors["device_risk_score"],
        "device_factor": round(device_factor * 100, 2),
        "merchant_risk_level": factors["merchant_risk_level"],
        "merchant_factor": round(merchant_factor * 100, 2),
        "final_score": round(risk_score, 2),
        "formula": "base + amount_factor*100 + customer_factor*100 + device_factor*100 + merchant_factor*100 capped 0-100",
    }

    # Factors to expose, with unavailable handling
    # Ensure Decimal and None are JSON serializable via string conversion where needed
    serializable_factors = {}
    for k, v in factors.items():
        if isinstance(v, Decimal):
            serializable_factors[k] = str(v)
        else:
            serializable_factors[k] = v
    # Add transaction meta
    serializable_factors["transaction_id"] = str(txn.id)
    serializable_factors["provider_event_id"] = txn.provider_event_id
    serializable_factors["status"] = txn.status.value if hasattr(txn.status, "value") else str(txn.status)
    serializable_factors["customer_id"] = str(txn.customer_id)
    serializable_factors["merchant_id"] = str(txn.merchant_id)
    serializable_factors["device_id"] = str(txn.device_id) if txn.device_id else None
    serializable_factors["created_at"] = txn.created_at.isoformat() if txn.created_at else None

    return {
        "transaction_id": txn.id,
        "provider_event_id": txn.provider_event_id,
        "amount": str(txn.amount),
        "currency": txn.currency,
        "risk_score": round(risk_score, 2),
        "risk_level": risk_level,
        "decision": decision,
        "triggered_rules": triggered,
        "evaluated_rules": evaluated,
        "decision_reason": decision_reason,
        "score_breakdown": score_breakdown,
        "factors": serializable_factors,
    }
