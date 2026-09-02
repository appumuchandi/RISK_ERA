from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.auth_deps import require_auth
from app.core.database import get_db
from app.schemas.alert import OperationsSummaryResponse
from app.services.alert_service import AlertService

router = APIRouter(prefix="/api/v1/operations", tags=["Operations"])


@router.get("/summary", response_model=OperationsSummaryResponse)
def get_operations_summary(
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> OperationsSummaryResponse:
    service = AlertService(db)
    result = service.get_operations_summary()
    return OperationsSummaryResponse(**result)
