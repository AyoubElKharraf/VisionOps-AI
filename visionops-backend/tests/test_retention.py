"""Retention policy unit tests — no Postgres/MinIO required."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://visionops:visionops_secret@localhost:5434/visionops_db",
)


@pytest.fixture()
def retention_settings(monkeypatch):
    monkeypatch.setenv("RETENTION_ENABLED", "true")
    monkeypatch.setenv("RETENTION_MEDIA_DAYS", "30")
    monkeypatch.setenv("RETENTION_RESOLVED_ALERT_DAYS", "90")
    monkeypatch.setenv("RETENTION_BUCKET_QUOTA_MB", "1")
    monkeypatch.setenv("RETENTION_INTERVAL_MINUTES", "60")
    from app.config import get_settings

    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def _alert(**kwargs):
    defaults = {
        "id": uuid.uuid4(),
        "created_at": datetime.now(timezone.utc) - timedelta(days=60),
        "resolved_at": None,
        "incident_status": "open",
        "snapshot_object_key": "alerts/old/snapshot.jpg",
        "clip_object_key": "alerts/old/clip.mp4",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_purge_expired_media(retention_settings):
    from app.retention import _purge_expired_media

    old = _alert()
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.all.return_value = [old]

    with patch("app.retention.delete_object") as delete:
        result = _purge_expired_media(db, retention_settings, dry_run=False)

    assert result["alerts"] == 1
    assert result["objects"] == 2
    assert old.snapshot_object_key is None
    assert old.clip_object_key is None
    assert delete.call_count == 2
    db.commit.assert_called_once()


def test_purge_resolved_alerts(retention_settings):
    from app.retention import _purge_resolved_alerts

    resolved = _alert(
        incident_status="resolved",
        resolved_at=datetime.now(timezone.utc) - timedelta(days=120),
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.all.return_value = [resolved]

    with patch("app.retention.delete_object") as delete:
        result = _purge_resolved_alerts(db, retention_settings, dry_run=False)

    assert result["alerts"] == 1
    assert delete.call_count == 2
    db.delete.assert_called_once_with(resolved)
    db.commit.assert_called_once()


def test_enforce_quota_deletes_oldest(retention_settings):
    from app.retention import _enforce_quota

    now = datetime.now(timezone.utc)
    objects = [
        {"key": "alerts/a/snap.jpg", "size": 700_000, "last_modified": now - timedelta(days=10)},
        {"key": "alerts/b/snap.jpg", "size": 700_000, "last_modified": now - timedelta(days=1)},
    ]
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    with (
        patch("app.retention.list_objects", return_value=objects),
        patch("app.retention.delete_object") as delete,
    ):
        result = _enforce_quota(db, retention_settings, dry_run=False)

    assert result["deleted_objects"] >= 1
    assert result["freed_bytes"] >= 700_000
    delete.assert_called()


def test_run_retention_disabled(monkeypatch):
    monkeypatch.setenv("RETENTION_ENABLED", "false")
    from app.config import get_settings
    from app.retention import run_retention

    get_settings.cache_clear()
    result = run_retention(dry_run=True)
    assert result["enabled"] is False
    get_settings.cache_clear()


def test_retention_status_shape(retention_settings):
    from app.retention import retention_status

    with patch("app.retention.bucket_usage_bytes", return_value=2_000_000):
        status = retention_status(retention_settings)
    assert status["enabled"] is True
    assert status["bucket_usage_bytes"] == 2_000_000
    assert status["quota_exceeded"] is True
