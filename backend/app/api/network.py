from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.auth.auth_deps import require_auth
from app.core.database import get_db
from app.schemas.network import NetworkGraphResponse
from app.services.network_service import NetworkService

router = APIRouter(prefix="/api/v1/network", tags=["Network"])


@router.get("/graph", response_model=NetworkGraphResponse)
def get_network_graph(
    entity_type: Literal["customer", "merchant", "device", "transaction", "case"] = Query(..., description="Entity type"),
    entity_id: UUID = Query(..., description="Entity UUID"),
    hops: int = Query(2, ge=1, le=3, description="Hop depth 1-3"),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> NetworkGraphResponse:
    service = NetworkService(db)
    result = service.get_graph(entity_type=entity_type, entity_id=entity_id, hops=hops)
    if result is None:
        # Distinguish 404 vs 422: if entity not found, result None due to missing entity
        # But service returns None for both invalid type/hops and not found; we validated hops/type via Query, so None means not found
        # Check existence explicitly for clearer 404
        # If service returned None due to not found, we return 404
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"{entity_type} not found")
    return NetworkGraphResponse(**result)
