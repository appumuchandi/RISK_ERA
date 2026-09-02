import sys
sys.path.insert(0, 'E:/PROJECTS/RISK-ERA/backend')

from decimal import Decimal
from uuid import UUID
from datetime import datetime
from typing import List

from app.schemas.evaluation import (
    GoldenCase,
    GoldenCaseInput,
    GoldenCaseExpected,
    GoldenCaseCategory,
    GoldenCaseDifficulty,
)


def _make_input(
    *,
    provider_event_id: str,
    amount: Decimal,
    currency: str,
    customer_external_id: str,
    device_fingerprint_hash: str | None = None,
    device_ip: str | None = None,
    device_user_agent: str | None = None,
    merchant_name: str = "Test Merchant",
    merchant_category_code: str = "5000",
    raw_payload: dict | None = None,
) -> GoldenCaseInput:
    return GoldenCaseInput(
        provider_event_id=provider_event_id,
        amount=amount,
        currency=currency,
        customer_external_id=customer_external_id,
        device_fingerprint_hash=device_fingerprint_hash,
        device_ip=device_ip,
        device_user_agent=device_user_agent,
        merchant_name=merchant_name,
        merchant_category_code=merchant_category_code,
        raw_payload=raw_payload or {},
    )


def _make_expected(
    *,
    deterministic_action: str,
    key_evidence_types: List[str],
    investigation_recommendation: str,
    rationale: str,
    difficulty: GoldenCaseDifficulty,
    category: GoldenCaseCategory,
    tags: List[str] | None = None,
) -> GoldenCaseExpected:
    return GoldenCaseExpected(
        deterministic_action=deterministic_action,
        key_evidence_types=key_evidence_types,
        investigation_recommendation=investigation_recommendation,
        rationale=rationale,
        difficulty=difficulty,
        category=category,
        )


# 25 golden investigation cases across 12 categories
# These are deterministic evaluation fixtures — they define expected behavior
# based on transaction patterns and business rules, not fake production evidence.

GOLDEN_DATASET: list[GoldenCase] = []

cases_data = [
    # --- Category: legitimate_transaction (Easy) ---
    ("Small legitimate transaction", "Small under-threshold transaction with normal customer risk",
     "evtxn-001", "15.99", "USD", "CUST-001", "dh-abc123",
     "allow", "approve", "easy", "legitimate_transaction"),
    ("Routine authorized transaction", "Normal authorized transaction within customer's typical range",
     "evtxn-002", "200.00", "USD", "CUST-002", "dh-def456",
     "allow", "approve", "easy", "legitimate_transaction"),
    # --- Category: high_value_anomaly (Medium) ---
    ("Large unexpected transaction", "Large transaction above customer's typical spending pattern",
     "evtxn-003", "15000.00", "USD", "CUST-001", "dh-abc123",
     "block", "block", "medium", "high_value_anomaly"),
    # --- Category: new_device (Medium) ---
    ("New device fingerprint", "Transaction from a device not previously associated with the customer",
     "evtxn-004", "450.00", "USD", "CUST-003", "dh-new-device-789|192.168.1.50",
     "review", "review", "medium", "new_device"),
    # --- Category: velocity_anomaly (Medium) ---
    ("Multiple rapid transactions", "Multiple transactions in short time from same customer/device",
     "evtxn-005", "88.00", "USD", "CUST-004", "dh-vel-123",
     "review", "review", "medium", "velocity_anomaly"),
    # --- Category: risky_device (Medium) ---
    ("Device with prior fraud flag", "Device associated with prior fraudulent activity",
     "evtxn-006", "1200.00", "USD", "CUST-005", "dh-fraud-device|10.0.0.99",
     "block", "block", "medium", "risky_device"),
    # --- Category: customer_risk_anomaly (Medium) ---
    ("High-risk customer tier transaction", "Customer in high-risk tier making unusual transaction",
     "evtxn-007", "3200.00", "USD", "CUST-006", "dh-risk-456|192.168.1.100",
     "block", "block", "medium", "customer_risk_anomaly"),
    # --- Category: merchant_anomaly (Medium) ---
    ("High-risk merchant category", "Transaction with merchant known for fraudulent activity",
     "evtxn-008", "670.00", "USD", "CUST-007", "dh-avg123|MCC-6510",
     "review", "review", "medium", "merchant_anomaly"),
    # --- Category: multiple_simultaneous_signals (Hard) ---
    ("High-value + new device + velocity", "Combined anomalies: large amount, new device, rapid transactions",
     "evtxn-009", "8500.00", "USD", "CUST-001", "dh-combo-789|10.0.0.50",
     "block", "block", "hard", "multiple_simultaneous_signals"),
    # --- Category: conflicting_signals (Hard) ---
    ("Large legitimate amount with new but clean device", "Large amount but device is new and has clean history",
     "evtxn-010", "5000.00", "USD", "CUST-008", "dh-clean-new|192.168.1.200",
     "review", "review", "hard", "conflicting_signals"),
    # --- Category: ambiguous_case (Hard) ---
    ("Marginal transaction with mixed signals", "Transaction just above threshold with mixed risk indicators",
     "evtxn-011", "950.00", "USD", "CUST-009", "dh-ambiguous-01|192.168.1.150",
     "review", "review", "hard", "ambiguous_case"),
    # --- Category: false_positive_prone (Medium) ---
    ("Legitimate business transaction flagged", "Normal business transaction that resembles fraud patterns",
     "evtxn-012", "3800.00", "USD", "CUST-010", "dh-business-02|MCC-5814",
     "review", "review", "medium", "false_positive_prone"),
    # --- Category: insufficient_evidence (Easy) ---
    ("Transaction with limited history", "New customer with very limited transaction history",
     "evtxn-013", "45.00", "USD", "CUST-NEW-01", "dh-limited-history",
     "review", "review", "easy", "insufficient_evidence"),
    # --- Additional cases to reach 25 total ---
    ("Very small transaction under $1", "Micro-transaction well under any fraud threshold",
     "evtxn-014", "0.99", "USD", "CUST-011", "",
     "allow", "approve", "easy", "legitimate_transaction"),
    ("Very large amount structuring pattern", "Unusually large structuring pattern detection",
     "evtxn-015", "9850.00", "USD", "CUST-002", "dh-structuring",
     "block", "block", "medium", "high_value_anomaly"),
    ("Device from high-risk geographic region", "Device from geographic region associated with fraud",
     "evtxn-016", "280.00", "USD", "CUST-003", "dh-high-risk-region|203.0.113.50",
     "review", "review", "medium", "new_device"),
    ("After-hours rapid transactions", "Multiple transactions outside normal business hours",
     "evtxn-017", "55.00", "USD", "CUST-004", "dh-after-hours",
     "review", "review", "medium", "velocity_anomaly"),
    ("Device with mismatched IP location", "Device IP location doesn't match customer's typical location",
     "evtxn-018", "1100.00", "USD", "CUST-005", "dh-ip-mismatch|8.8.8.8",
     "block", "block", "medium", "risky_device"),
    ("Customer risk tier downgrade transaction", "Customer with recent risk tier change making transaction",
     "evtxn-019", "750.00", "USD", "CUST-012", "dh-risk-downgrade",
     "review", "review", "medium", "customer_risk_anomaly"),
    ("Round-number transaction from high-risk merchant", "Round-amount transaction from high-risk merchant category",
     "evtxn-020", "3000.00", "USD", "CUST-013", "dh-round-amt|MCC-6510",
     "review", "review", "medium", "merchant_anomaly"),
    ("Transaction at exact threshold boundary", "Transaction exactly at the fraud threshold",
     "evtxn-021", "1000.00", "USD", "CUST-014", "dh-threshold-boundary",
     "review", "review", "hard", "ambiguous_case"),
    ("Legitimate recurring transaction", "Legitimate recurring transaction resembling fraud",
     "evtxn-022", "475.00", "USD", "CUST-015", "dh-recurring",
     "review", "review", "medium", "false_positive_prone"),
    ("New customer first transaction", "First transaction for new customer with no history",
     "evtxn-023", "500.00", "USD", "CUST-FIRST-01", "",
     "review", "review", "easy", "insufficient_evidence"),
    ("Edge case: low amount but risky merchant", "Low amount but merchant is explicitly high-risk",
     "evtxn-024", "25.00", "USD", "CUST-016", "dh-low-amount-high-risk-merchant|MCC-9999",
     "review", "review", "medium", "false_positive_prone"),
    ("Final case: comprehensive anomaly review", "Comprehensive case for comprehensive evaluation",
     "evtxn-025", "6200.00", "USD", "CUST-017", "dh-comprehensive-01",
     "review", "review", "hard", "multiple_simultaneous_signals"),
]

for i, (name, desc, provider_event_id, amount, currency, customer_external_id, device_info,
        rec_action, rec_recommendation, rec_difficulty, rec_category) in enumerate(cases_data, 1):
    
    # Parse device info
    device_fingerprint = None
    device_ip = None
    if "|" in device_info:
        parts = device_info.split("|")
        device_fingerprint = parts[0]
        device_ip = parts[1] if len(parts) > 1 else None
    
    # Map category string to enum
    category_map = {
        "legitimate_transaction": GoldenCaseCategory.LEGITIMATE_TRANSACTION,
        "high_value_anomaly": GoldenCaseCategory.HIGH_VALUE_ANOMALY,
        "new_device": GoldenCaseCategory.NEW_DEVICE,
        "velocity_anomaly": GoldenCaseCategory.VELOCITY_ANOMALY,
        "risky_device": GoldenCaseCategory.RISKY_DEVICE,
        "customer_risk_anomaly": GoldenCaseCategory.CUSTOMER_RISK_ANOMALY,
        "merchant_anomaly": GoldenCaseCategory.MERCHANT_ANOMALY,
        "multiple_simultaneous_signals": GoldenCaseCategory.MULTIPLE_SIMULTANEOUS_SIGNALS,
        "conflicting_signals": GoldenCaseCategory.CONFLICTING_SIGNALS,
        "ambiguous_case": GoldenCaseCategory.AMBIGUOUS_CASE,
        "false_positive_prone": GoldenCaseCategory.FALSE_POSITIVE_PRONE,
        "insufficient_evidence": GoldenCaseCategory.INSUFFICIENT_EVIDENCE,
    }
    
    # Map difficulty string to enum
    difficulty_map = {
        "easy": GoldenCaseDifficulty.EASY,
        "medium": GoldenCaseDifficulty.MEDIUM,
        "hard": GoldenCaseDifficulty.HARD,
    }
    
    inp = _make_input(
        provider_event_id=provider_event_id,
        amount=Decimal(amount),
        currency=currency,
        customer_external_id=customer_external_id,
        device_fingerprint_hash=device_fingerprint,
        device_ip=device_ip,
    )
    
    exp = _make_expected(
        deterministic_action=rec_action,
        key_evidence_types=[],
        investigation_recommendation=rec_recommendation,
        rationale=f"{name} evaluation",
        difficulty=difficulty_map[rec_difficulty],
        category=category_map[rec_category],
    )
    
    gc = GoldenCase(
        name=name,
        description=desc,
        input=inp,
        expected=exp,
        category=category_map[rec_category],  # Top-level category
        difficulty=difficulty_map[rec_difficulty],  # Top-level difficulty
    )
    
    GOLDEN_DATASET.append(gc)
    
    print(f"  {i}. [{gc.category.value}] {gc.name} -> expected: {gc.expected.investigation_recommendation}")

print(f"\nGolden dataset loaded: {len(GOLDEN_DATASET)} cases")