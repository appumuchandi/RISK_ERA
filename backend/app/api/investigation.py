from __future__ import annotations

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.validation import (
    PaginationParams,
)
from app.auth.auth_deps import require_auth
from app.schemas.investigation import (
    TransactionHistoryRequest,
    TransactionHistoryResponse,
    CustomerProfileRequest,
    CustomerProfileResponse,
    DeviceActivityRequest,
    DeviceActivityResponse,
)
from app.services.nemotron_investigator import NemotronInvestigator
from app.services.investigation_tools import InvestigationTools

router = APIRouter(prefix="/api/v1/investigation", tags=["Investigation"])


@router.get("", response_model=dict)
def list_investigations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    """List investigations with pagination."""
    from app.models import Investigation
    from sqlalchemy import select, func

    base = select(Investigation)
    count_q = select(func.count(Investigation.id))
    if status:
        # Validate status
        from app.models.investigation import InvestigationStatus
        try:
            st = InvestigationStatus(status.lower())
            base = base.where(Investigation.status == st)
            count_q = count_q.where(Investigation.status == st)
        except ValueError:
            from fastapi import HTTPException, status as http_status
            raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")

    total = db.execute(count_q).scalar() or 0
    total_pages = (total + page_size - 1) // page_size if total else 0
    base = base.order_by(Investigation.started_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(base).scalars().all()

    items = []
    for inv in rows:
        items.append({
            "id": str(inv.id),
            "investigation_id": str(inv.id),
            "case_id": str(inv.case_id),
            "status": inv.status.value if hasattr(inv.status, "value") else str(inv.status),
            "model_provider": inv.model_provider,
            "model_name": inv.model_name,
            "model_available": inv.model_available,
            "recommendation": inv.recommendation,
            "confidence": inv.confidence,
            "started_at": inv.started_at.isoformat() if inv.started_at else None,
            "completed_at": inv.completed_at.isoformat() if inv.completed_at else None,
            "duration_ms": inv.duration_ms,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


@router.post("/{case_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_investigation(
    case_id: UUID,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    """Run the Nemotron investigation for a case."""
    from app.models import Case, Transaction
    from app.models.transaction import TransactionStatus
    from sqlalchemy import select

    actor = user

    # Step 2: Get case and transaction
    case = db.execute(select(Case).where(Case.id == case_id)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    txn = db.execute(select(Transaction).where(Transaction.id == case.transaction_id)).scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    
    # Step 3: Get deterministic action
    status_map = {
        TransactionStatus.AUTHORIZED: "allow",
        TransactionStatus.FLAGGED: "review",
        TransactionStatus.FAILED: "block",
    }
    deterministic_action = status_map.get(txn.status, "allow")
    
    # Step 4: Get risk score
    risk_score: Optional[float] = None
    
    # Step 5: Get triggered rules
    triggered_rules: list[dict] = []
    
    # Step 6: Get existing evidence (respecting pagination if needed)
    existing_evidence: list[dict] = []
    
    try:
        investigator = NemotronInvestigator(db)
        return investigator.investigate(
            case_id=case_id,
            transaction_id=txn.id,
            deterministic_action=deterministic_action,
            risk_score=risk_score,
            triggered_rules=triggered_rules,
            existing_evidence=existing_evidence,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Investigation failed: {str(e)}")


@router.get("/{case_id}/result", response_model=Optional[dict])
def get_investigation_result(
    case_id: UUID,
    db: Session = Depends(get_db),
    user = Depends(require_auth)
):
    """Get the latest investigation result for a case."""
    from app.models import Investigation
    from sqlalchemy import select

    investigation = db.execute(
        select(Investigation).where(Investigation.case_id == case_id)
        .order_by(Investigation.started_at.desc())
    ).scalars().first()

    if not investigation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation result not found")

    return {
        "investigation_id": str(investigation.id),
        "case_id": str(investigation.case_id),
        "model_provider": investigation.model_provider,
        "model_name": investigation.model_name,
        "model_available": investigation.model_available,
        "risk_assessment": investigation.risk_assessment,
        "confidence": investigation.confidence,
        "recommendation": investigation.recommendation,
        "reasoning_summary": investigation.reasoning_summary,
        "findings": investigation.findings,
        "evidence_references": investigation.evidence_references,
        "missing_evidence": investigation.missing_evidence,
        "tool_calls": investigation.tool_calls,
        "tool_calls_count": investigation.tool_calls_count,
        "duration_ms": investigation.duration_ms,
        "status": investigation.status.value,
        "failure_reason": investigation.failure_reason,
        "failure_details": investigation.failure_details,
        "started_at": investigation.started_at.isoformat() if investigation.started_at else None,
        "completed_at": investigation.completed_at.isoformat() if investigation.completed_at else None,
    }


@router.get("/{case_id}/history", response_model=list[dict])
def get_investigation_history(
    case_id: UUID,
    db: Session = Depends(get_db),
    user = Depends(require_auth)
):
    """Get all investigations for a case."""
    from app.models import Investigation
    from sqlalchemy import select

    investigations = db.execute(
        select(Investigation)
        .where(Investigation.case_id == case_id)
        .order_by(Investigation.started_at.desc())
    ).scalars().all()

    return [
        {
            "investigation_id": str(inv.id),
            "case_id": str(inv.case_id),
            "model_provider": inv.model_provider,
            "model_name": inv.model_name,
            "model_available": inv.model_available,
            "risk_assessment": inv.risk_assessment,
            "confidence": inv.confidence,
            "recommendation": inv.recommendation,
            "reasoning_summary": inv.reasoning_summary,
            "findings": inv.findings,
            "evidence_references": inv.evidence_references,
            "missing_evidence": inv.missing_evidence,
            "tool_calls": inv.tool_calls,
            "tool_calls_count": inv.tool_calls_count,
            "duration_ms": inv.duration_ms,
            "status": inv.status.value,
            "failure_reason": inv.failure_reason,
            "failure_details": inv.failure_details,
            "started_at": inv.started_at.isoformat() if inv.started_at else None,
            "completed_at": inv.completed_at.isoformat() if inv.completed_at else None,
        }
        for inv in investigations
    ]


@router.post("/tools/transaction-history", response_model=TransactionHistoryResponse)
def call_transaction_history(
    request: TransactionHistoryRequest,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> TransactionHistoryResponse:
    """Direct tool call: get transaction history for a customer."""
    tools = InvestigationTools(db)
    result = tools.get_transaction_history(request)
    if not result.success or not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.error or "Not found")
    return TransactionHistoryResponse(**result.data)


@router.post("/tools/customer-profile", response_model=CustomerProfileResponse)
def call_customer_profile(
    request: CustomerProfileRequest,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> CustomerProfileResponse:
    """Direct tool call: get customer profile."""
    tools = InvestigationTools(db)
    result = tools.get_customer_profile(request)
    if not result.success or not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.error or "Not found")
    return CustomerProfileResponse(**result.data)


@router.post("/tools/device-activity", response_model=DeviceActivityResponse)
def call_device_activity(
    request: DeviceActivityRequest,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> DeviceActivityResponse:
    """Direct tool call: get device activity."""
    tools = InvestigationTools(db)
    result = tools.get_device_activity(request)
    if not result.success or not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.error or "Not found")
    return DeviceActivityResponse(**result.data)


@router.get("/{case_id}/workbench", response_model=dict)
def get_workbench(
    case_id: UUID,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    """Workbench aggregation for analyst investigation."""
    from app.models import Case, Transaction, Investigation, Evidence, AuditLog
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    # Case with transaction and customer/merchant/device
    case = db.execute(
        select(Case)
        .where(Case.id == case_id)
        .options(selectinload(Case.transaction))
    ).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # Transaction with relationships
    txn = db.execute(
        select(Transaction)
        .where(Transaction.id == case.transaction_id)
        .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))
    ).scalar_one_or_none()

    # Latest investigation
    investigation = db.execute(
        select(Investigation).where(Investigation.case_id == case_id).order_by(Investigation.started_at.desc())
    ).scalars().first()

    # Evidence for case
    evidence = db.execute(select(Evidence).where(Evidence.case_id == case_id).order_by(Evidence.retrieved_at.asc())).scalars().all()

    # Audit timeline for case and transaction and investigation
    audit_logs = db.execute(
        select(AuditLog)
        .where(
            (AuditLog.resource_type == "case") & (AuditLog.resource_id == str(case_id))
            | (AuditLog.resource_type == "investigation") & (AuditLog.resource_id == str(case_id))
            | (AuditLog.resource_type == "evidence") & (AuditLog.resource_id.in_([str(e.id) for e in evidence] if evidence else []))
        )
        .order_by(AuditLog.created_at.asc())
        .limit(50)
    ).scalars().all() if evidence else db.execute(
        select(AuditLog)
        .where((AuditLog.resource_type == "case") & (AuditLog.resource_id == str(case_id)) | (AuditLog.resource_type == "investigation") & (AuditLog.resource_id == str(case_id)))
        .order_by(AuditLog.created_at.asc())
        .limit(50)
    ).scalars().all()

    # Build timeline from real persisted events
    timeline = []
    # case creation
    timeline.append({"timestamp": case.created_at.isoformat() if case.created_at else None, "event": "case_created", "actor": case.assignee or "system", "detail": f"Case {str(case.id)[:8]} created with status {case.status.value}"})
    # evidence
    for ev in evidence:
        timeline.append({"timestamp": ev.retrieved_at.isoformat() if ev.retrieved_at else None, "event": "evidence_added", "actor": "system", "detail": f"Evidence {ev.source_type}:{str(ev.source_id)[:8]} added"})
    # investigation events
    if investigation:
        timeline.append({"timestamp": investigation.started_at.isoformat() if investigation.started_at else None, "event": "investigation_started", "actor": "analyst", "detail": f"Investigation {str(investigation.id)[:8]} started"})
        if investigation.completed_at:
            timeline.append({"timestamp": investigation.completed_at.isoformat(), "event": "investigation_completed", "actor": "nemotron" if investigation.model_available else "fallback", "detail": f"Investigation completed with recommendation {investigation.recommendation}"})
    # audit logs
    for al in audit_logs:
        # avoid duplicate case_created already added if same timestamp
        timeline.append({"timestamp": al.created_at.isoformat() if al.created_at else None, "event": al.action, "actor": al.actor, "detail": f"{al.resource_type}:{al.resource_id} {al.action}"})
    # sort by timestamp
    timeline = [t for t in timeline if t["timestamp"]]
    timeline.sort(key=lambda x: x["timestamp"])

    # Build six stages
    stage_names = [
        "Retrieve transaction context",
        "Evaluate risk signals",
        "Retrieve supporting evidence",
        "Analyze with Nemotron",
        "Ground findings",
        "Generate recommendation",
    ]
    stages = []
    inv_status = investigation.status.value if investigation else "pending"
    tool_calls = investigation.tool_calls if investigation and investigation.tool_calls else []
    # Derive stage statuses
    # If no investigation, all pending
    # If pending, stage 1 running
    # If running, stages 1-2 completed, 3 running
    # If completed, all completed
    # If failed, last failed
    def stage_status(idx: int):
        if not investigation:
            return "pending"
        if inv_status == "pending":
            return "running" if idx == 0 else "pending"
        if inv_status == "running":
            if idx < 2:
                return "completed"
            if idx == 2:
                return "running"
            return "pending"
        if inv_status == "completed":
            return "completed"
        if inv_status == "failed":
            return "failed" if idx == 5 else "completed" if idx < 5 else "pending"
        return "pending"

    for idx, name in enumerate(stage_names):
        s_status = stage_status(idx)
        # Determine times/duration from investigation
        start = investigation.started_at.isoformat() if investigation and investigation.started_at and s_status != "pending" else None
        end = investigation.completed_at.isoformat() if investigation and investigation.completed_at and s_status == "completed" else None
        duration = investigation.duration_ms if investigation and investigation.duration_ms and s_status == "completed" else None
        result = None
        error = None
        if idx == 0 and s_status == "completed":
            result = f"Transaction {txn.provider_event_id if txn else 'unknown'} loaded"
        elif idx == 1 and s_status == "completed":
            result = "Risk signals evaluated via RuleEngine"
        elif idx == 2 and s_status == "completed":
            result = f"{len(evidence)} evidence items retrieved"
        elif idx == 3:
            if investigation and investigation.model_available:
                result = f"Nemotron {investigation.model_name} available" if s_status == "completed" else "Nemotron analysis"
            else:
                result = "Deterministic fallback (Nemotron unavailable)" if s_status in ("completed", "failed") else "Analyze with Nemotron"
            if s_status == "failed" and investigation and investigation.failure_reason:
                error = investigation.failure_reason
        elif idx == 4 and s_status == "completed":
            result = f"{len(investigation.findings) if investigation and investigation.findings else 0} findings grounded"
        elif idx == 5 and s_status == "completed":
            result = f"Recommendation: {investigation.recommendation if investigation else 'pending'}"

        stages.append({
            "name": name,
            "status": s_status,
            "start_time": start,
            "end_time": end,
            "duration_ms": duration,
            "result": result,
            "error": error,
        })

    # Summary
    summary = None
    if investigation:
        summary = {
            "risk_assessment": investigation.risk_assessment,
            "recommendation": investigation.recommendation,
            "confidence": investigation.confidence,
            "reasoning_summary": investigation.reasoning_summary,
            "model_available": investigation.model_available,
            "model_name": investigation.model_name,
            "model_provider": investigation.model_provider,
            "status": investigation.status.value,
            "findings_count": len(investigation.findings) if investigation.findings else 0,
        }

    # Risk via rule engine for header (reuse)
    risk_score = None
    risk_level = "low"
    decision = "allow"
    if txn:
        try:
            from app.services.risk_explain_service import explain_transaction
            exp = explain_transaction(db, txn.id)
            if exp:
                risk_score = exp["risk_score"]
                risk_level = exp["risk_level"]
                decision = exp["decision"]
        except Exception:
            pass

    # Related entities
    related = {}
    if txn:
        related = {
            "customer_id": str(txn.customer_id) if txn.customer_id else None,
            "merchant_id": str(txn.merchant_id) if txn.merchant_id else None,
            "device_id": str(txn.device_id) if txn.device_id else None,
            "transaction_id": str(txn.id),
            "case_id": str(case.id),
            "alert_id": None,  # could link via alert table if exists
        }
        # Try to find alert for this transaction
        try:
            from app.models.alert import Alert
            alert = db.execute(select(Alert).where(Alert.transaction_id == txn.id).order_by(Alert.created_at.desc())).scalars().first()
            if alert:
                related["alert_id"] = str(alert.id)
        except Exception:
            pass

    return {
        "case": {
            "id": str(case.id),
            "status": case.status.value,
            "assignee": case.assignee,
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            "transaction_id": str(case.transaction_id),
        },
        "transaction": {
            "id": str(txn.id) if txn else None,
            "provider_event_id": txn.provider_event_id if txn else None,
            "amount": str(txn.amount) if txn else None,
            "currency": txn.currency if txn else None,
            "status": txn.status.value if txn and hasattr(txn.status, "value") else str(txn.status) if txn else None,
            "customer_id": str(txn.customer_id) if txn and txn.customer_id else None,
            "merchant_id": str(txn.merchant_id) if txn and txn.merchant_id else None,
            "device_id": str(txn.device_id) if txn and txn.device_id else None,
            "created_at": txn.created_at.isoformat() if txn and txn.created_at else None,
        },
        "investigation": {
            "investigation_id": str(investigation.id) if investigation else None,
            "status": investigation.status.value if investigation else "not_started",
            "model_provider": investigation.model_provider if investigation else None,
            "model_name": investigation.model_name if investigation else None,
            "model_available": investigation.model_available if investigation else False,
            "risk_assessment": investigation.risk_assessment if investigation else None,
            "confidence": investigation.confidence if investigation else None,
            "recommendation": investigation.recommendation if investigation else None,
            "reasoning_summary": investigation.reasoning_summary if investigation else None,
            "findings": investigation.findings if investigation else [],
            "evidence_references": investigation.evidence_references if investigation else [],
            "missing_evidence": investigation.missing_evidence if investigation else [],
            "tool_calls": investigation.tool_calls if investigation and investigation.tool_calls is not None else [],
            "tool_calls_count": investigation.tool_calls_count if investigation else 0,
            "duration_ms": investigation.duration_ms if investigation else None,
            "started_at": investigation.started_at.isoformat() if investigation and investigation.started_at else None,
            "completed_at": investigation.completed_at.isoformat() if investigation and investigation.completed_at else None,
            "failure_reason": investigation.failure_reason if investigation else None,
        } if investigation else None,
        "stages": stages,
        "summary": summary,
        "tool_calls": investigation.tool_calls if investigation and investigation.tool_calls is not None else [],
        "evidence": [
            {"id": str(e.id), "source_type": e.source_type, "source_id": str(e.source_id), "payload": e.payload, "created_at": e.retrieved_at.isoformat() if e.retrieved_at else None, "retrieved_at": e.retrieved_at.isoformat() if e.retrieved_at else None}
            for e in evidence
        ],
        "timeline": timeline,
        "related_entities": related,
        "risk": {"risk_score": risk_score, "risk_level": risk_level, "decision": decision},
    }

