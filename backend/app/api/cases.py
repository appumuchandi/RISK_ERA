from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.auth_deps import require_auth
from app.schemas.case import (
    CaseCreate,
    CaseUpdate,
    CaseResponse,
    CaseDetail,
    CaseListResponse,
    CaseFilter,
    CaseStatus as SchemaCaseStatus,
)
from app.schemas.evidence import (
    EvidenceCreate,
    EvidenceResponse,
    EvidenceListResponse,
    EvidenceFilter,
)
from app.services.case_service import CaseService

router = APIRouter(prefix="/api/v1/cases", tags=["Cases"])


@router.post(
    "",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_case(
    request: CaseCreate,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> CaseResponse:
    service = CaseService(db)
    try:
        case = service.create_case(
            transaction_id=request.transaction_id,
            status=SchemaCaseStatus.OPEN,
            assignee=request.assignee,
            actor=user,
        )
        return CaseResponse.model_validate(case)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=CaseListResponse)
def list_cases(
    status: Optional[SchemaCaseStatus] = Query(None),
    assignee: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user = Depends(require_auth)
) -> CaseListResponse:
    from datetime import datetime
    
    date_from_dt = None
    date_to_dt = None
    if date_from:
        date_from_dt = datetime.fromisoformat(date_from)
    if date_to:
        date_to_dt = datetime.fromisoformat(date_to)
    
    service = CaseService(db)
    filters = CaseFilter(
        status=status,
        assignee=assignee,
        date_from=date_from_dt,
        date_to=date_to_dt,
        page=page,
        page_size=page_size,
    )
    return service.list_cases(filters)


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    user = Depends(require_auth)
) -> CaseDetail:
    service = CaseService(db)
    case = service.get_case_detail(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


@router.patch("/{case_id}", response_model=CaseResponse)
def update_case(
    case_id: UUID,
    request: CaseUpdate,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> CaseResponse:
    service = CaseService(db)
    try:
        case = service.update_case(case_id, request, user)
        return CaseResponse.model_validate(case)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{case_id}/assign", response_model=CaseResponse)
def assign_case(
    case_id: UUID,
    assignee: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> CaseResponse:
    service = CaseService(db)
    try:
        case = service.assign_case(case_id, assignee, user)
        return CaseResponse.model_validate(case)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{case_id}/status", response_model=CaseResponse)
def change_case_status(
    case_id: UUID,
    new_status: SchemaCaseStatus = Query(...),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> CaseResponse:
    service = CaseService(db)
    try:
        case = service.change_status(case_id, new_status, user)
        return CaseResponse.model_validate(case)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{case_id}/evidence", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
def add_evidence(
    case_id: UUID,
    request: EvidenceCreate,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> EvidenceResponse:
    service = CaseService(db)
    try:
        evidence = service.add_evidence(case_id, request.source_type, request.source_id, request.payload, user)
        return EvidenceResponse.model_validate(evidence)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{case_id}/evidence", response_model=EvidenceListResponse)
def list_evidence(
    case_id: UUID,
    source_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user = Depends(require_auth)
) -> EvidenceListResponse:
    service = CaseService(db)
    filters = EvidenceFilter(source_type=source_type, page=page, page_size=page_size)
    return service.list_evidence(case_id, filters)