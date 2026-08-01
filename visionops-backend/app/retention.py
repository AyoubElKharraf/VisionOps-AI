"""Retention policies — purge old alert media and enforce storage quotas."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.minio_client import bucket_usage_bytes, delete_object, list_objects
from app.models import Alert, IncidentStatus

logger = logging.getLogger("visionops.retention")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def retention_status(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    usage = 0
    try:
        usage = bucket_usage_bytes("alerts/")
    except Exception as exc:  # noqa: BLE001
        logger.debug("Bucket usage unavailable: %s", exc)
    quota_bytes = max(0, int(s.retention_bucket_quota_mb)) * 1024 * 1024
    return {
        "enabled": bool(s.retention_enabled),
        "media_days": s.retention_media_days,
        "resolved_alert_days": s.retention_resolved_alert_days,
        "bucket_quota_mb": s.retention_bucket_quota_mb,
        "interval_minutes": s.retention_interval_minutes,
        "bucket_usage_bytes": usage,
        "bucket_usage_mb": round(usage / (1024 * 1024), 2),
        "quota_exceeded": bool(quota_bytes and usage > quota_bytes),
    }


def _clear_alert_media(alert: Alert, *, dry_run: bool) -> list[str]:
    removed: list[str] = []
    for attr in ("snapshot_object_key", "clip_object_key"):
        key = getattr(alert, attr)
        if not key:
            continue
        removed.append(key)
        if not dry_run:
            delete_object(key)
            setattr(alert, attr, None)
    return removed


def _purge_expired_media(db: Session, settings: Settings, *, dry_run: bool) -> dict[str, Any]:
    days = int(settings.retention_media_days)
    if days <= 0:
        return {"skipped": True, "alerts": 0, "objects": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    alerts = (
        db.query(Alert)
        .filter(Alert.created_at < cutoff)
        .filter(
            or_(
                Alert.snapshot_object_key.isnot(None),
                Alert.clip_object_key.isnot(None),
            )
        )
        .all()
    )
    objects = 0
    for alert in alerts:
        objects += len(_clear_alert_media(alert, dry_run=dry_run))
    if not dry_run and alerts:
        db.commit()
    return {"skipped": False, "alerts": len(alerts), "objects": objects, "cutoff": cutoff.isoformat()}


def _purge_resolved_alerts(db: Session, settings: Settings, *, dry_run: bool) -> dict[str, Any]:
    days = int(settings.retention_resolved_alert_days)
    if days <= 0:
        return {"skipped": True, "alerts": 0, "objects": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    alerts = (
        db.query(Alert)
        .filter(Alert.incident_status == IncidentStatus.resolved.value)
        .filter(
            or_(
                and_(Alert.resolved_at.isnot(None), Alert.resolved_at < cutoff),
                and_(Alert.resolved_at.is_(None), Alert.created_at < cutoff),
            )
        )
        .all()
    )
    objects = 0
    for alert in alerts:
        objects += len(_clear_alert_media(alert, dry_run=dry_run))
        if not dry_run:
            db.delete(alert)
    if not dry_run and alerts:
        db.commit()
    return {"skipped": False, "alerts": len(alerts), "objects": objects, "cutoff": cutoff.isoformat()}


def _enforce_quota(db: Session, settings: Settings, *, dry_run: bool) -> dict[str, Any]:
    quota_mb = int(settings.retention_bucket_quota_mb)
    if quota_mb <= 0:
        return {"skipped": True, "deleted_objects": 0, "freed_bytes": 0}

    quota_bytes = quota_mb * 1024 * 1024
    objects = sorted(
        list_objects("alerts/"),
        key=lambda item: _aware(item.get("last_modified")) or datetime.min.replace(tzinfo=timezone.utc),
    )
    usage = sum(int(item["size"]) for item in objects)
    if usage <= quota_bytes:
        return {
            "skipped": False,
            "deleted_objects": 0,
            "freed_bytes": 0,
            "usage_bytes": usage,
            "quota_bytes": quota_bytes,
        }

    deleted = 0
    freed = 0
    keys_removed: list[str] = []
    for item in objects:
        if usage - freed <= quota_bytes:
            break
        key = item["key"]
        size = int(item["size"])
        keys_removed.append(key)
        if not dry_run:
            delete_object(key)
        deleted += 1
        freed += size

    if not dry_run and keys_removed:
        key_set = set(keys_removed)
        alerts = (
            db.query(Alert)
            .filter(
                or_(
                    Alert.snapshot_object_key.in_(key_set),
                    Alert.clip_object_key.in_(key_set),
                )
            )
            .all()
        )
        for alert in alerts:
            if alert.snapshot_object_key in key_set:
                alert.snapshot_object_key = None
            if alert.clip_object_key in key_set:
                alert.clip_object_key = None
        db.commit()

    return {
        "skipped": False,
        "deleted_objects": deleted,
        "freed_bytes": freed,
        "usage_bytes_before": usage,
        "quota_bytes": quota_bytes,
    }


def run_retention(*, dry_run: bool = False, db: Session | None = None) -> dict[str, Any]:
    """Apply age-based media purge, resolved-alert cleanup, then quota enforcement."""
    settings = get_settings()
    if not settings.retention_enabled:
        return {"ok": True, "enabled": False, "dry_run": dry_run}

    owns_session = db is None
    if owns_session:
        from app.database import SessionLocal

        db = SessionLocal()
    assert db is not None

    try:
        media = _purge_expired_media(db, settings, dry_run=dry_run)
        resolved = _purge_resolved_alerts(db, settings, dry_run=dry_run)
        quota = _enforce_quota(db, settings, dry_run=dry_run)
        status = retention_status(settings)
        result = {
            "ok": True,
            "enabled": True,
            "dry_run": dry_run,
            "media_purge": media,
            "resolved_purge": resolved,
            "quota_enforcement": quota,
            "status": status,
        }
        logger.info(
            "Retention complete dry_run=%s media_alerts=%s resolved_alerts=%s quota_deleted=%s",
            dry_run,
            media.get("alerts"),
            resolved.get("alerts"),
            quota.get("deleted_objects"),
        )
        return result
    finally:
        if owns_session:
            db.close()
