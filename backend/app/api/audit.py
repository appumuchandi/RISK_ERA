from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.audit import AuditLogResponse, AuditLogListResponse
from app.services.audit_service import AuditService
from app.auth.auth_deps import require_auth

router = APIRouter(prefix="/api/v1/audit", tags=["Audit"])


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, description="Alias for date_from"),
    to_date: Optional[str] = Query(None, description="Alias for to_date"),
    search: Optional[str] = Query(None, description="Search actor/action/resource"),
    sort_by: str = Query("created_at", description="created_at, actor, action, resource_type"),
    sort_order: str = Query("desc", description="asc or desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user = Depends(require_auth)
) -> AuditLogListResponse:
    eff_from = from_date or date_from
    eff_to = to_date or date_to
    if sort_by not in ("created_at", "actor", "action", "resource_type"):
        raise HTTPException(status_code=422, detail="Invalid sort_by")
    if sort_order not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail="Invalid sort_order")
    service = AuditService(db)
    try:
        items, total = service.get_audit_logs(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            date_from=eff_from,
            date_to=eff_to,
            page=page,
            page_size=page_size,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/summary")
def get_audit_summary(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user = Depends(require_auth),
):
    eff_from = from_date or date_from
    eff_to = to_date or date_to
    service = AuditService(db)
    summary = service.get_summary(from_date=eff_from, to_date=eff_to)
    return summary


@router.get("/verify-chain")
def verify_audit_chain(
    limit: int = Query(1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    user = Depends(require_auth)
):
    service = AuditService(db)
    is_valid, error = service.verify_chain(limit=limit)
    # Enrich with counts and timestamps for UI
    from sqlalchemy import select, func
    from app.models.audit_log import AuditLog
    total = db.execute(select(func.count(AuditLog.id))).scalar() or 0
    # Get first and last timestamps
    first = db.execute(select(AuditLog).order_by(AuditLog.created_at.asc()).limit(1)).scalars().first()
    last = db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(1)).scalars().first()
    return {
        "valid": is_valid,
        "error": error,
        "checked_count": min(limit, total),
        "total": total,
        "first_checked_at": first.created_at.isoformat() if first and first.created_at else None,
        "last_checked_at": last.created_at.isoformat() if last and last.created_at else None,
    }
