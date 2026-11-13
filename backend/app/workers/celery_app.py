"""Celery Worker Application Setup."""

from typing import Any

try:
    from celery import Celery

    HAS_CELERY = True
except ImportError:
    Celery = None
    HAS_CELERY = False

from app.core.config import settings

celery_app: Any | None = None

if HAS_CELERY and Celery is not None:
    celery_app = Celery(
        "askyourdata_worker",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        worker_prefetch_multiplier=1,
    )

    @celery_app.task(name="health_check_task")  # type: ignore[untyped-decorator]
    def health_check_task() -> dict[str, str]:
        """Simple ping task to verify worker health."""
        return {"status": "worker_online"}
