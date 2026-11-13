"""Admin Control Panel Router (Skeleton)."""

from typing import Any

from fastapi import APIRouter, Depends

from app.api.v1.deps import require_permission
from app.db.models import User

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/audit-log")
async def get_audit_log(
    current_user: User = Depends(require_permission("admin:access")),
) -> dict[str, Any]:
    """Retrieve system audit logs."""
    return {"data": []}
