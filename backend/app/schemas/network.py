from __future__ import annotations

from typing import Optional, List, Dict
from uuid import UUID

from pydantic import BaseModel, Field


class NetworkNode(BaseModel):
    id: str
    type: str  # customer, merchant, device, transaction, case
    label: str
    risk_score: Optional[float] = None
    risk_level: str = "low"
    hop: int = 0
    # optional extra metadata for frontend
    external_id: Optional[str] = None
    provider_event_id: Optional[str] = None


class NetworkEdge(BaseModel):
    source: str
    target: str
    relationship: str
    label: str
    supporting_transaction_ids: List[str] = Field(default_factory=list)
    supporting_case_ids: List[str] = Field(default_factory=list)


class NetworkStats(BaseModel):
    node_count: int = 0
    edge_count: int = 0
    customer_count: int = 0
    merchant_count: int = 0
    device_count: int = 0
    transaction_count: int = 0
    case_count: int = 0
    max_hop: int = 0


class NetworkGraphResponse(BaseModel):
    root: NetworkNode
    nodes: List[NetworkNode]
    edges: List[NetworkEdge]
    stats: NetworkStats
