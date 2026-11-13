"""Health Check and Service Readiness Endpoints."""

import os
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None  # type: ignore

from app.api.v1.deps import get_db_session
from app.core.config import settings

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict[str, str]:
    """Basic liveness check verifying the application process is running."""
    return {"status": "alive", "version": settings.VERSION}


@router.get("/ready")
async def readiness_probe(
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Deep readiness probe verifying database, cache, and filesystem access."""
    checks: dict[str, str] = {}
    is_ready = True

    # 1. PostgreSQL Check
    try:
        result = await session.execute(text("SELECT 1"))
        if result.scalar() == 1:
            checks["postgres"] = "ok"
        else:
            checks["postgres"] = "unexpected_response"
            is_ready = False
    except Exception as e:
        checks["postgres"] = f"error: {str(e)}"
        is_ready = False

    # 2. Redis Check
    if Redis is not None:
        try:
            redis_client = Redis.from_url(settings.REDIS_URL, socket_timeout=2)
            ping_result = await redis_client.ping()
            await redis_client.aclose()
            if ping_result:
                checks["redis"] = "ok"
            else:
                checks["redis"] = "no_pong"
                is_ready = False
        except Exception as e:
            checks["redis"] = f"error: {str(e)}"
            if settings.ENVIRONMENT == "production":
                is_ready = False
    else:
        checks["redis"] = "not_installed"

    # 3. DuckDB / Storage directory check
    storage_dir = os.path.dirname(settings.DUCKDB_DATABASE_PATH) or "."
    try:
        os.makedirs(storage_dir, exist_ok=True)
        checks["storage"] = "ok"
    except Exception as e:
        checks["storage"] = f"error: {str(e)}"
        is_ready = False

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "checks": checks}

    return {"status": "healthy", "checks": checks}
