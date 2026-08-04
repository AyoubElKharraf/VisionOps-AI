"""Unit tests for incident ZIP evidence pack export."""

from __future__ import annotations

import io
import json
import os
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://visionops:visionops_secret@localhost:5434/visionops_db",
)


@pytest.fixture()
def export_client(monkeypatch):
    monkeypatch.setenv("VISIONOPS_API_KEY", "")
    monkeypatch.setenv("VISIONOPS_JWT_SECRET", "")
    from app.config import get_settings
    from app.models import AlertStatus, AlertType

    get_settings.cache_clear()

    alert_id = uuid.uuid4()
    cam = SimpleNamespace(id=uuid.uuid4(), name="export-cam")
    alert = SimpleNamespace(
        id=alert_id,
        camera_id=cam.id,
        camera=cam,
        alert_type=AlertType.roi_intrusion,
        status=AlertStatus.ready,
        incident_status="open",
        zone_name="dock",
        class_name="person",
        track_id=3,
        confidence=0.91,
        message="Export me",
        metadata_json={"reason": "intrusion"},
        assigned_to=None,
        acknowledged_by=None,
        acknowledged_at=None,
        resolved_by=None,
        resolved_at=None,
        resolution_note=None,
        source_video_path=None,
        frame_index=12,
        snapshot_object_key="alerts/snap.jpg",
        clip_object_key="alerts/clip.mp4",
        error_message=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        events=[
            SimpleNamespace(
                id=uuid.uuid4(),
                alert_id=alert_id,
                event_type="created",
                actor="system",
                message="Incident opened",
                metadata_json={"alert_type": "roi_intrusion"},
                created_at=datetime.now(timezone.utc),
            )
        ],
    )

    class FakeDB:
        def get(self, model, key):
            return None

        def query(self, model):
            class Q:
                def options(self, *a):
                    return self

                def filter(self, *a):
                    return self

                def first(self):
                    return alert

            return Q()

    monkeypatch.setattr("app.main.run_migrations", lambda: None)
    monkeypatch.setattr("app.main.ensure_bucket", lambda: "test-bucket")
    monkeypatch.setattr("app.routers.alerts.presigned_get_url", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "app.routers.alerts.download_object_bytes",
        lambda key: b"JPEGDATA" if key.endswith(".jpg") else b"MP4DATA",
    )

    from app.main import app as fastapi_app
    from app.database import get_db
    from fastapi.testclient import TestClient

    def _db():
        yield FakeDB()

    fastapi_app.dependency_overrides[get_db] = _db
    with TestClient(fastapi_app) as client:
        yield client, alert
    fastapi_app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_export_alert_pack_zip_contains_evidence(export_client):
    client, alert = export_client
    r = client.get(f"/api/v1/alerts/{alert.id}/export")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/zip")
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    assert "incident.json" in names
    assert "timeline.json" in names
    assert "README.txt" in names
    assert "snapshot.jpg" in names
    assert "clip.mp4" in names
    timeline = json.loads(zf.read("timeline.json"))
    assert timeline[0]["event_type"] == "created"
    assert zf.read("snapshot.jpg") == b"JPEGDATA"
    assert "Export me" in zf.read("README.txt").decode()
