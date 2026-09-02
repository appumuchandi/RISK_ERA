from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AssistantContext(BaseModel):
    route: Optional[str] = Field(None, description="Current frontend route")
    caseId: Optional[str] = Field(None, description="Selected case ID")
    transactionId: Optional[str] = Field(None, description="Selected transaction ID")
    customerId: Optional[str] = Field(None, description="Selected customer ID")
    merchantId: Optional[str] = Field(None, description="Selected merchant ID")
    deviceId: Optional[str] = Field(None, description="Selected device ID")
    extra: Optional[Dict[str, Any]] = Field(None, description="Additional context already loaded by page")


class AssistantRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User question")
    context: Optional[AssistantContext] = Field(None, description="Application context")


class AssistantResponse(BaseModel):
    answer: str
    grounded: bool = Field(description="Whether answer is grounded in live backend data")
    sources: List[str] = Field(default_factory=list, description="Sources used: documentation, case, transaction, etc.")
    context_used: Optional[Dict[str, Any]] = None
