from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.auth.auth_deps import require_auth
from app.core.database import get_db
from app.schemas.rules import RuleResponse, RuleListResponse
from app.services.rule_service import list_rules, get_rule

router = APIRouter(prefix="/api/v1/rules", tags=["Rules"])


@router.get("", response_model=RuleListResponse)
def list_rules_endpoint(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search name or condition"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled"),
    action: Optional[str] = Query(None, description="Filter by action: allow, review, block"),
    sort_by: str = Query("priority", description="Sort field: priority, created_at, name, action"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> RuleListResponse:
    if action and action.lower() not in ("allow", "review", "block"):
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid action filter")
    if sort_by not in ("priority", "created_at", "name", "action"):
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid sort_by")
    if sort_order not in ("asc", "desc"):
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid sort_order")
    result = list_rules(db, page=page, page_size=page_size, search=search, enabled=enabled, action=action, sort_by=sort_by, sort_order=sort_order)
    return RuleListResponse(**result)


@router.get("/{rule_id}", response_model=RuleResponse)
def get_rule_endpoint(
    rule_id: UUID,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> RuleResponse:
    result = get_rule(db, rule_id)
    if not result:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return RuleResponse(**result)
