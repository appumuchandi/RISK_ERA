from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.auth_deps import require_auth
from app.schemas.feedback import (
    FeedbackCreate,
    FeedbackResponse,
    FeedbackListResponse,
)
from app.models import AnalystFeedback, Investigation
from sqlalchemy import select, func

router = APIRouter(prefix="/api/v1/feedback", tags=["Feedback"])


@router.post(
    "/investigation/{investigation_id}",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_feedback(
    investigation_id: UUID,
    request: FeedbackCreate,
    user = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Submit feedback for an investigation."""

    investigation = db.execute(
        select(Investigation).where(Investigation.id == investigation_id)
    ).scalar_one_or_none()

    if not investigation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")

    feedback = AnalystFeedback(
        investigation_id=investigation_id,
        case_id=investigation.case_id,
        decision=request.decision.value,
        corrected_recommendation=request.corrected_recommendation,
        reason=request.reason,
        actor=user,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return FeedbackResponse.model_validate(feedback)


@router.get("/investigation/{investigation_id}", response_model=FeedbackListResponse)
def list_feedback_for_investigation(
    investigation_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """List all feedback for an investigation."""
    from app.models import AnalystFeedback
    from sqlalchemy import select

    stmt = select(AnalystFeedback).where(AnalystFeedback.investigation_id == investigation_id)
    count_stmt = select(func.count(AnalystFeedback.id)).where(AnalystFeedback.investigation_id == investigation_id)

    total = db.execute(count_stmt).scalar() or 0

    stmt = stmt.order_by(AnalystFeedback.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = db.execute(stmt).scalars().all()

    return FeedbackListResponse(
        items=[FeedbackResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/case/{case_id}", response_model=FeedbackListResponse)
def list_feedback_for_case(
    case_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """List all feedback for a case."""
    from app.models import AnalystFeedback
    from sqlalchemy import select

    stmt = select(AnalystFeedback).where(AnalystFeedback.case_id == case_id)
    count_stmt = select(func.count(AnalystFeedback.id)).where(AnalystFeedback.case_id == case_id)

    total = db.execute(count_stmt).scalar() or 0

    stmt = stmt.order_by(AnalystFeedback.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = db.execute(stmt).scalars().all()

    return FeedbackListResponse(
        items=[FeedbackResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{feedback_id}", response_model=FeedbackResponse)
def get_feedback(
    feedback_id: UUID,
    user = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Get a specific feedback entry."""
    from app.models import AnalystFeedback
    from sqlalchemy import select

    stmt = select(AnalystFeedback).where(AnalystFeedback.id == feedback_id)
    feedback = db.execute(stmt).scalar_one_or_none()

    if not feedback:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")

    return FeedbackResponse.model_validate(feedback)