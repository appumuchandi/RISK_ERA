from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.nemotron_service import nemotron_service


router = APIRouter(prefix="/api/v1/ai", tags=["AI"])


class InvestigationRequest(BaseModel):
    prompt: str


@router.post("/test")
def test_nemotron(request: InvestigationRequest):
    try:
        result = nemotron_service.generate(request.prompt)

        return {
            "model": "nemotron",
            "response": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Nemotron request failed: {str(exc)}",
        )