from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi import status as http_status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.auth.auth_deps import require_auth
from app.core.database import get_db
from app.schemas.alert import AlertResponse, AlertListResponse, AlertDetailResponse
from app.services.alert_service import AlertService

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts"])


class StatusUpdateRequest(BaseModel):
    status: str
    reason: Optional[str] = None


class AssignRequest(BaseModel):
    assigned_to: str


class ResolveRequest(BaseModel):
    reason: Optional[str] = None


@router.get("", response_model=AlertListResponse)
def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    priority: Optional[int] = Query(None, ge=1, le=100),
    alert_type: Optional[str] = Query(None),
    decision: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    sort_by: str = Query("created_at", description="created_at, priority, risk_score, severity"),
    sort_order: str = Query("desc", description="asc or desc"),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> AlertListResponse:
    service = AlertService(db)
    try:
        result = service.list_alerts(
            page=page,
            page_size=page_size,
            status=status,
            severity=severity,
            priority=priority,
            alert_type=alert_type,
            decision=decision,
            assigned_to=assigned_to,
            search=search,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return AlertListResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/{alert_id}", response_model=AlertDetailResponse)
def get_alert(
    alert_id: UUID,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> AlertDetailResponse:
    service = AlertService(db)
    result = service.get_alert(alert_id)
    if not result:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return AlertDetailResponse(**result)


@router.patch("/{alert_id}/status", response_model=AlertResponse)
def update_alert_status(
    alert_id: UUID,
    body: StatusUpdateRequest,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    service = AlertService(db)
    try:
        alert = service.update_status(alert_id, body.status, actor=user, reason=body.reason)
        if not alert:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Alert not found")
        # Return enriched
        result = service.get_alert(alert_id)
        return AlertResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/{alert_id}/assign", response_model=AlertResponse)
def assign_alert(
    alert_id: UUID,
    body: AssignRequest,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    service = AlertService(db)
    alert = service.assign(alert_id, body.assigned_to, actor=user)
    if not alert:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Alert not found")
    result = service.get_alert(alert_id)
    return AlertResponse(**result)


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(
    alert_id: UUID,
    body: ResolveRequest = Body(default=None),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    reason = body.reason if body else None
    service = AlertService(db)
    try:
        alert = service.resolve(alert_id, actor=user, reason=reason)
        if not alert:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Alert not found")
        result = service.get_alert(alert_id)
        return AlertResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/{alert_id}/dismiss", response_model=AlertResponse)
def dismiss_alert(
    alert_id: UUID,
    body: ResolveRequest = Body(default=None),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    reason = body.reason if body else None
    service = AlertService(db)
    try:
        alert = service.dismiss(alert_id, actor=user, reason=reason)
        if not alert:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Alert not found")
        result = service.get_alert(alert_id)
        return AlertResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/{alert_id}/case")
def create_case_from_alert(
    alert_id: UUID,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    service = AlertService(db)
    try:
        alert, case = service.create_case_from_alert(alert_id, actor=user)
        if not alert:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Alert not found")
        if not case:
            raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not create case, no transaction")
        return {"alert_id": str(alert.id), "case_id": str(case.id), "transaction_id": str(case.transaction_id)}
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
