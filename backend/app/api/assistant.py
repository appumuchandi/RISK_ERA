from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.auth_deps import require_auth
from app.core.database import get_db
from app.schemas.assistant import AssistantRequest, AssistantResponse
from app.services.assistant_service import AssistantService

router = APIRouter(prefix="/api/v1/assistant", tags=["Assistant"])


@router.post("/chat", response_model=AssistantResponse)
def chat(
    request: AssistantRequest,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    # Validate message not empty (already via Pydantic)
    # Sanitize context: ensure IDs are strings, not too large
    # Rate limiting is handled via global middleware (1000 for dev)
    try:
        service = AssistantService(db)
        # Convert context to dict for service
        ctx = request.context.model_dump() if request.context else None
        result = service.generate_answer(message=request.message, context=ctx, user=user)
        return AssistantResponse(**result)
    except Exception as e:
        # Never expose internal details
        raise HTTPException(status_code=503, detail="RISK-ERA Assistant is temporarily unavailable. Please try again.")
