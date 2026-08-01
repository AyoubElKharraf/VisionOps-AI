"""Notification configuration status (read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_auth
from app.config import get_settings
from app.notifications import channels_enabled, parse_notify_events

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_auth)],
)


@router.get("/status")
def notification_status() -> dict:
    settings = get_settings()
    channels = channels_enabled(settings)
    return {
        "enabled": any(channels.values()),
        "channels": channels,
        "events": sorted(parse_notify_events(settings.notify_events)),
        "dashboard_base_url": settings.notify_dashboard_base_url or None,
    }
