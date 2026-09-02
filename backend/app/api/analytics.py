from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.auth.auth_deps import require_auth
from app.core.database import get_db
from app.schemas.analytics import DashboardAnalytics
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/dashboard", response_model=DashboardAnalytics)
def get_dashboard(
    days: int = Query(30, ge=1, le=365, description="Days range 1-365"),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> DashboardAnalytics:
    try:
        service = AnalyticsService(db)
        result = service.get_dashboard(days=days)
        return DashboardAnalytics(**result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
