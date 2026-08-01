"""Celery application factory."""

from datetime import timedelta

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "visionops",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)

_retention_minutes = max(1, int(settings.retention_interval_minutes or 60))

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "visionops-retention": {
            "task": "visionops.run_retention",
            "schedule": timedelta(minutes=_retention_minutes),
        }
    },
)
