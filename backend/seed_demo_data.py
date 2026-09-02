#!/usr/bin/env python3
"""
RISK-ERA Deterministic Synthetic Demo Seeder
Inserts demo data into the PostgreSQL instance used by the running FastAPI app.
All data is SYNTHETIC — not real customer/payment data.
"""
from __future__ import annotations

import uuid
import random
import json
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.models import Rule
from app.models.rule import RuleAction
from app.services.transaction_service import TransactionService

RANDOM = random.Random(42)

MERCHANT_CATEGORIES = ["5411", "5542", "5812", "7995", "5499", "5311", "5045", "5533", "5912", "7800"]
MERCHANT_NAMES = {
    "5411": "Supermart India",
    "5542": "FuelPoint Delhi",
    "5812": "Bistro Chennai",
    "7995": "Casino Royale",
    "5499": "TradeCorp Mumbai",
    "5311": "DeptStore Bangalore",
    "5045": "AirIndia Express",
    "5533": "FuelBunk HQ",
    "5912": "WineShop Select",
    "7800": "GameZone Arena",
}
CITIES = ["Mumbai", "Delhi", "Bangalore", "Chennai", "Kolkata", "Hyderabad", "Pune", "Ahmedabad", "Jaipur", "Lucknow"]
PAYMENT_METHODS = ["credit_card", "debit_card", "upi", "netbanking"]

DEMO_RULES = [
    ("block_high_amount", "amount > 10000", RuleAction.BLOCK, 100),
    ("review_medium_amount", "amount > 5000", RuleAction.REVIEW, 80),
    ("review_high_risk_customer", "customer_risk_tier == 'high'", RuleAction.REVIEW, 75),
    ("block_gambling", "merchant_category_code == '7995'", RuleAction.BLOCK, 95),
    ("review_velocity", "amount > 3000 and merchant_category_code == '7995'", RuleAction.REVIEW, 70),
    ("review_new_device_high", "device_risk_score is not None and device_risk_score > 0.6 and amount > 2000", RuleAction.REVIEW, 60),
    ("allow_small", "amount < 500", RuleAction.ALLOW, 10),
]

SHOWCASE_TRANSACTIONS = [
    # Case A: High-value suspicious from new device + high velocity pattern
    {
        "provider_event_id": "evt_demo_caseA_001",
        "amount": Decimal("48500.00"),
        "currency": "INR",
        "customer_external_id": "cust_showcase_critical_001",
        "device_fingerprint_hash": "fp_showcase_critical_newdev_001",
        "device_ip": "203.192.12.88",
        "device_user_agent": "Mozilla/5.0 (HighRiskDevice)",
        "merchant_name": "Casino Royale",
        "merchant_category_code": "7995",
        "raw_payload": {"city": "Mumbai", "payment_method": "credit_card", "channel": "online", "demo_note": "Synthetic demonstration data — not real customer/payment data.", "velocity_last_hour": 7, "account_age_days": 3},
    },
    # Case B: Velocity / repeated anomaly — same customer many txns short window
    {
        "provider_event_id": "evt_demo_caseB_001",
        "amount": Decimal("18400.00"),
        "currency": "INR",
        "customer_external_id": "cust_showcase_velocity_002",
        "device_fingerprint_hash": "fp_showcase_velocity_002",
        "device_ip": "49.36.88.12",
        "device_user_agent": "Mozilla/5.0 (VelocityPattern)",
        "merchant_name": "Supermart India",
        "merchant_category_code": "5411",
        "raw_payload": {"city": "Delhi", "payment_method": "upi", "channel": "online", "demo_note": "Synthetic demonstration data", "velocity_last_hour": 12, "failed_attempts": 3},
    },
    # Case C: Evidence exception / missing device + gambling high risk
    {
        "provider_event_id": "evt_demo_caseC_001",
        "amount": Decimal("34750.00"),
        "currency": "INR",
        "customer_external_id": "cust_showcase_evidence_003",
        "device_fingerprint_hash": "fp_showcase_evidence_003",
        "device_ip": "10.244.12.4",
        "device_user_agent": "Mozilla/5.0 (UnknownDevice)",
        "merchant_name": "GameZone Arena",
        "merchant_category_code": "7800",
        "raw_payload": {"city": "Bangalore", "payment_method": "credit_card", "channel": "online", "demo_note": "Synthetic demonstration data", "device_age": "new"},
    },
]


def truncate_all(db):
    # Order matters due to FKs
    db.execute(text("TRUNCATE TABLE analyst_feedback, investigations, evidence, cases, transactions, rules, merchants, devices, customers, audit_log RESTART IDENTITY CASCADE"))
    db.commit()


def seed_rules(db):
    rules = []
    for name, expr, action, prio in DEMO_RULES:
        r = Rule(name=name, dsl_expression=expr, action=action, priority=prio, enabled=True, version=1)
        rules.append(r)
    db.add_all(rules)
    db.commit()
    print(f"  Seeded {len(rules)} rules")


def seed_showcase_customer_tiers(db):
    # Pre-create showcase customers with high risk tiers for demo impact
    from app.models import Customer
    showcase = [
        ("cust_showcase_critical_001", "high", "verified"),
        ("cust_showcase_velocity_002", "high", "pending"),
        ("cust_showcase_evidence_003", "premium", "verified"),
    ]
    for ext_id, tier, kyc in showcase:
        c = Customer(external_id=ext_id, risk_tier=tier, kyc_status=kyc)
        db.add(c)
    db.commit()


def seed_synthetic_transactions(db, count: int = 220):
    svc = TransactionService(db)
    created = 0
    # First ingest showcase transactions
    for payload in SHOWCASE_TRANSACTIONS:
        try:
            resp = svc.ingest(payload)
            created += 1
            print(f"  Showcase {payload['provider_event_id']} -> {resp.action.value} risk={resp.risk_score:.2f} case={resp.case_id}")
        except Exception as e:
            print(f"  ! showcase ingest failed {payload['provider_event_id']}: {e}")

    # Then generate bulk synthetic normal + suspicious mix
    # Create velocity burst for case B: same customer many transactions quickly
    for i in range(8):
        payload = {
            "provider_event_id": f"evt_demo_velocity_burst_{i:03d}",
            "amount": Decimal(str(RANDOM.randint(800, 3500))),
            "currency": "INR",
            "customer_external_id": "cust_showcase_velocity_002",
            "device_fingerprint_hash": "fp_showcase_velocity_002",
            "device_ip": "49.36.88.12",
            "merchant_name": RANDOM.choice(list(MERCHANT_NAMES.values())),
            "merchant_category_code": RANDOM.choice(MERCHANT_CATEGORIES),
            "raw_payload": {"city": "Delhi", "payment_method": "upi", "velocity_burst": True, "demo_note": "Synthetic demonstration data"},
        }
        try:
            svc.ingest(payload)
            created += 1
        except Exception:
            pass

    for i in range(count):
        ext_id = f"cust_demo_{RANDOM.randint(1, 40):03d}"
        merch_cat = RANDOM.choice(MERCHANT_CATEGORIES)
        merch_name = MERCHANT_NAMES[merch_cat]
        # skewed amounts: 70% normal, 30% suspicious high
        if RANDOM.random() < 0.7:
            amt = Decimal(str(RANDOM.randint(150, 4200)))
        else:
            amt = Decimal(str(RANDOM.randint(6500, 55000)))
        payload = {
            "provider_event_id": f"evt_demo_bulk_{i:05d}_{uuid.uuid4().hex[:6]}",
            "amount": amt,
            "currency": "INR",
            "customer_external_id": ext_id,
            "device_fingerprint_hash": f"fp_demo_{RANDOM.randint(1, 25):02d}" if RANDOM.random() > 0.2 else None,
            "device_ip": f"10.{RANDOM.randint(0,255)}.{RANDOM.randint(0,255)}.{RANDOM.randint(1,254)}" if RANDOM.random() > 0.3 else None,
            "device_user_agent": f"Mozilla/5.0 ({RANDOM.choice(CITIES)})",
            "merchant_name": merch_name,
            "merchant_category_code": merch_cat,
            "raw_payload": {
                "city": RANDOM.choice(CITIES),
                "payment_method": RANDOM.choice(PAYMENT_METHODS),
                "demo_note": "Synthetic demonstration data — not real customer/payment data.",
            },
        }
        try:
            svc.ingest(payload)
            created += 1
        except Exception as e:
            # ignore duplicate provider_event_id collisions (unlikely with uuid)
            continue
    print(f"  Ingested {created} transactions (showcase + bulk)")
    return created


def backfill_evidence_and_audits(db):
    from app.models import Case, Evidence
    from app.services.audit_service import AuditService
    cases = db.execute(text("SELECT id, transaction_id, status, created_at FROM cases ORDER BY created_at ASC")).fetchall()
    print(f"  Found {len(cases)} cases for evidence backfill")
    audit = AuditService(db, actor="system")
    # Add evidence to first half of cases to demonstrate grounding + create audits
    for idx, row in enumerate(cases):
        case_id = row[0]
        # audit CASE_CREATED for each case (transaction_service did not create via CaseService, so backfill)
        try:
            audit.log(actor="system", action="CASE_CREATED", resource_type="case", resource_id=str(case_id), after={"demo": True, "status": str(row[2])})
        except Exception:
            pass
        if idx % 2 == 0:
            for j in range(RANDOM.randint(1, 2)):
                ev = Evidence(case_id=case_id, source_type=RANDOM.choice(["transaction", "device", "customer"]), source_id=f"ref_demo_{uuid.uuid4().hex[:8]}", payload={"demo": True, "note": "Synthetic demonstration data", "risk_signal": RANDOM.choice(["HIGH_AMOUNT", "NEW_DEVICE", "VELOCITY"])})
                db.add(ev)
                db.flush()
                try:
                    audit.log(actor="analyst", action="EVIDENCE_ADDED", resource_type="evidence", resource_id=str(ev.id), after={"case_id": str(case_id), "source_type": ev.source_type})
                except Exception:
                    pass
        # add investigation audit for first 3 cases
        if idx < 3:
            try:
                audit.log(actor="nemotron_investigator", action="INVESTIGATION_STARTED", resource_type="investigation", resource_id=str(case_id), after={"case_id": str(case_id)})
                audit.log(actor="nemotron_investigator", action="INVESTIGATION_COMPLETED", resource_type="investigation", resource_id=str(case_id), after={"case_id": str(case_id), "recommendation": RANDOM.choice(["review", "block"])})
            except Exception:
                pass
        if idx == len(cases) - 1 and len(cases) >= 3:
            pass
    db.commit()
    print("  Evidence & audit backfill committed")
    audit_count = db.execute(text("SELECT count(*) FROM audit_log")).scalar()
    print(f"  Audit events: {audit_count}")
    # also add analyst decision audit for one case
    if cases:
        try:
            audit.log(actor="analyst", action="CASE_UPDATED", resource_type="case", resource_id=str(cases[0][0]), before={"status": "open"}, after={"status": "in_progress", "analyst_decision": "REVIEW", "reason": "High-risk velocity pattern — synthetic demo"})
            db.commit()
        except Exception:
            pass


def main():
    print("="*60)
    print("RISK-ERA Demo Seeder — Synthetic Payment Data")
    print("Deterministic seed=42 — not real Razorpay data")
    print("="*60)
    db = SessionLocal()
    try:
        print("\n[1/5] Truncating existing data...")
        truncate_all(db)
        print("  Truncated")

        print("\n[2/5] Seeding rules...")
        seed_rules(db)

        print("\n[3/5] Seeding showcase customers...")
        seed_showcase_customer_tiers(db)

        print("\n[4/5] Seeding synthetic transactions (this creates cases via rule engine)...")
        seed_synthetic_transactions(db, count=220)

        print("\n[5/5] Backfilling evidence & verifying audits...")
        backfill_evidence_and_audits(db)

        # Backfill a few completed investigations for dashboard demo (so AI Investigations >0 without requiring live Nemotron)
        try:
            from app.models.investigation import Investigation, InvestigationStatus
            showcase_cases = db.execute(text("SELECT id FROM cases ORDER BY created_at ASC LIMIT 3")).fetchall()
            for idx, (cid,) in enumerate(showcase_cases):
                inv = Investigation(
                    case_id=cid,
                    model_provider="nvidia",
                    model_name="nvidia/nemotron-3.5-lightning-30b-a3b",
                    model_available=False,
                    status=InvestigationStatus.COMPLETED,
                    risk_assessment="Synthetic demo — deterministic fallback; high-risk pattern: HIGH_AMOUNT, NEW_DEVICE, VELOCITY",
                    confidence=0.82 if idx == 0 else 0.76,
                    recommendation="review" if idx == 0 else "block" if idx == 1 else "review",
                    reasoning_summary="Demo investigation — synthetic Nemotron fallback. Findings grounded in controlled tool evidence. This is demonstration data, not real payment data.",
                    findings=[{"finding_id": f"f-demo-{idx+1}", "description": "Detected high-amount + new-device pattern via controlled tools", "evidence_ids": [], "confidence": 0.88, "source": "deterministic"}],
                    evidence_references=[],
                    missing_evidence=["Additional device history unavailable — synthetic demo"] if idx == 2 else [],
                    tool_calls=[{"tool_calls": [{"id": f"demo-tool-{idx}", "function": {"name": "get_transaction_history", "arguments": "{}"}, "result": "{\"success\": true}"}]}],
                    tool_calls_count=1,
                    duration_ms=1800 + idx*400,
                    started_at=datetime.now(timezone.utc) - timedelta(hours=idx+1),
                    completed_at=datetime.now(timezone.utc) - timedelta(hours=idx),
                )
                db.add(inv)
            db.commit()
        except Exception as e:
            print(f"  ! investigation backfill failed: {e}")
            db.rollback()

        # Final metrics
        customers = db.execute(text("SELECT count(*) FROM customers")).scalar()
        merchants = db.execute(text("SELECT count(*) FROM merchants")).scalar()
        devices = db.execute(text("SELECT count(*) FROM devices")).scalar()
        txns = db.execute(text("SELECT count(*) FROM transactions")).scalar()
        cases = db.execute(text("SELECT count(*) FROM cases")).scalar()
        evidence = db.execute(text("SELECT count(*) FROM evidence")).scalar()
        audits = db.execute(text("SELECT count(*) FROM audit_log")).scalar()
        invs = db.execute(text("SELECT count(*) FROM investigations")).scalar()
        by_status = db.execute(text("SELECT status, count(*) FROM cases GROUP BY status")).fetchall()
        print("\n" + "="*60)
        print("Seeding complete — demo environment ready")
        print(f"  customers: {customers}")
        print(f"  merchants: {merchants}")
        print(f"  devices: {devices}")
        print(f"  transactions: {txns}")
        print(f"  cases: {cases} by status: {dict(by_status)}")
        print(f"  evidence: {evidence}")
        print(f"  investigations: {invs}")
        print(f"  audit events: {audits}")
        print("Label: Demo Environment \u00b7 Synthetic Payment Data")
        print("="*60)
    finally:
        db.close()


if __name__ == "__main__":
    main()
