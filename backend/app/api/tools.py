from fastapi import APIRouter, Depends
from app.auth.auth_deps import require_auth

router = APIRouter(prefix="/api/v1/tools", tags=["Tools"])

@router.get("/status")
def tools_status(user = Depends(require_auth)):
    """Check if investigation tools are available."""
    return {
        "tools": [
            "get_transaction_history",
            "get_customer_profile",
            "get_device_activity",
        ],
        "available": True,
    }
