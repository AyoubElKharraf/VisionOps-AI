"""Retention policy status and manual trigger."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth import require_auth, require_roles
from app.models import UserRole
from app.retention import retention_status, run_retention
from app.tasks import run_retention_task

router = APIRouter(
    prefix="/retention",
    tags=["retention"],
    dependencies=[Depends(require_auth)],
)


@router.get("/status")
def get_retention_status() -> dict:
    return retention_status()


@router.post("/run")
def trigger_retention(
    dry_run: bool = Query(False),
    async_run: bool = Query(True),
    _: object = Depends(require_roles(UserRole.admin)),
) -> dict:
    """Run retention now. Admins only. Default: enqueue Celery task."""
    if async_run:
        run_retention_task.delay(dry_run=dry_run)
        return {"ok": True, "queued": True, "dry_run": dry_run}
    return run_retention(dry_run=dry_run)
