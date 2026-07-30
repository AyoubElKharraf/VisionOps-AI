"""Incident lifecycle tests — no Postgres required."""

from __future__ import annotations

import os
import sys
import uuid
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


class Store:
    def __init__(self) -> None:
        self.cameras: dict[uuid.UUID, SimpleNamespace] = {}
        self.alerts: dict[uuid.UUID, SimpleNamespace] = {}
        self.events: list[SimpleNamespace] = []

        cam = SimpleNamespace(
            id=uuid.uuid4(),
            name="demo-camera",
            source_url="rtsp://127.0.0.1:8554/cam1",
            location="lab",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        self.cameras[cam.id] = cam
        alert = SimpleNamespace(
            id=uuid.uuid4(),
            camera_id=cam.id,
            camera=cam,
            alert_type="roi_intrusion",
            status="ready",
            incident_status="open",
            zone_name="dock",
            class_name="person",
            track_id=1,
            confidence=0.9,
            message="Intrusion",
            metadata_json=None,
            assigned_to=None,
            acknowledged_by=None,
            acknowledged_at=None,
            resolved_by=None,
            resolved_at=None,
            resolution_note=None,
            source_video_path=None,
            frame_index=10,
            snapshot_object_key=None,
            clip_object_key=None,
            error_message=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            events=[],
        )
        self.alerts[alert.id] = alert


class FakeQuery:
    def __init__(self, store: Store, model_name: str):
        self.store = store
        self.model_name = model_name
        self._filters: list = []
        self._options: list = []

    def options(self, *args):
        self._options.extend(args)
        return self

    def filter(self, *args):
        self._filters.extend(args)
        return self

    def order_by(self, *args):
        return self

    def limit(self, _n: int):
        return self

    def all(self):
        if self.model_name == "Alert":
            items = list(self.store.alerts.values())
        elif self.model_name == "Camera":
            items = list(self.store.cameras.values())
        else:
            return []

        for f in self._filters:
            left = getattr(f, "left", None)
            right = getattr(f, "right", None)
            key = getattr(left, "key", None)
            value = getattr(right, "value", right)
            if key == "incident_status":
                items = [a for a in items if a.incident_status == value]
            elif key == "camera_id":
                items = [a for a in items if a.camera_id == value]
            elif key == "status":
                items = [a for a in items if a.status == value]
            elif key == "name":
                items = [a for a in items if a.name == value]
        return items

    def first(self):
        items = self.all()
        # Prefer id match when filtering Alert.id == ...
        for f in self._filters:
            left = getattr(f, "left", None)
            right = getattr(f, "right", None)
            key = getattr(left, "key", None)
            value = getattr(right, "value", right)
            if key == "id":
                if self.model_name == "Alert":
                    return self.store.alerts.get(value)
                if self.model_name == "Camera":
                    return self.store.cameras.get(value)
            if key == "name" and self.model_name == "Camera":
                for cam in self.store.cameras.values():
                    if cam.name == value:
                        return cam
                return None
            if key == "incident_status" and self.model_name == "Alert":
                matched = [a for a in items if a.incident_status == value]
                return matched[0] if matched else None
        return items[0] if items else None


class FakeDb:
    def __init__(self, store: Store):
        self.store = store

    def query(self, model):
        return FakeQuery(self.store, model.__name__)

    def get(self, model, item_id):
        if model.__name__ == "Alert":
            return self.store.alerts.get(item_id)
        if model.__name__ == "Camera":
            return self.store.cameras.get(item_id)
        return None

    def add(self, obj):
        if obj.__class__.__name__ == "AlertEvent":
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(timezone.utc)
            self.store.events.append(obj)
            alert = self.store.alerts.get(obj.alert_id)
            if alert is not None:
                alert.events = [*list(alert.events or []), obj]
        elif obj.__class__.__name__ == "Alert":
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            obj.events = []
            obj.camera = self.store.cameras.get(obj.camera_id)
            self.store.alerts[obj.id] = obj

    def delete(self, obj):
        if obj.__class__.__name__ == "Alert" or hasattr(obj, "incident_status"):
            self.store.alerts.pop(obj.id, None)
            self.store.events = [event for event in self.store.events if event.alert_id != obj.id]

    def flush(self):
        return None

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("VISIONOPS_API_KEY", "test-secret-key")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr("app.main.run_migrations", lambda: None)
    monkeypatch.setattr("app.main.ensure_bucket", lambda: "test-bucket")
    monkeypatch.setattr("app.routers.alerts.ensure_bucket", lambda: "test-bucket")
    monkeypatch.setattr(
        "app.routers.alerts.process_alert_media.delay",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr("app.routers.alerts.presigned_get_url", lambda *_a, **_k: None)

    from app.main import app as fastapi_app
    from app.database import get_db
    from fastapi.testclient import TestClient

    store = Store()

    def fake_db():
        yield FakeDb(store)

    fastapi_app.dependency_overrides[get_db] = fake_db
    with TestClient(fastapi_app) as c:
        c.store = store  # type: ignore[attr-defined]
        yield c

    fastapi_app.dependency_overrides.clear()
    get_settings.cache_clear()
    monkeypatch.delenv("VISIONOPS_API_KEY", raising=False)
    get_settings.cache_clear()


def _headers():
    return {"X-API-Key": "test-secret-key"}


def test_delete_alert_removes_incident_and_timeline(client):
    alert_id = next(iter(client.store.alerts))  # type: ignore[attr-defined]

    deleted = client.delete(f"/api/v1/alerts/{alert_id}", headers=_headers())
    assert deleted.status_code == 204, deleted.text

    missing = client.get(f"/api/v1/alerts/{alert_id}", headers=_headers())
    assert missing.status_code == 404


def test_acknowledge_assign_resolve_and_history(client):
    alert_id = next(iter(client.store.alerts))  # type: ignore[attr-defined]

    ack = client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge",
        headers=_headers(),
        json={"actor": "alice", "note": "Looking into it"},
    )
    assert ack.status_code == 200, ack.text
    assert ack.json()["incident_status"] == "acknowledged"
    assert ack.json()["acknowledged_by"] == "alice"

    assigned = client.post(
        f"/api/v1/alerts/{alert_id}/assign",
        headers=_headers(),
        json={"assignee": "bob", "actor": "alice"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_to"] == "bob"

    commented = client.post(
        f"/api/v1/alerts/{alert_id}/comments",
        headers=_headers(),
        json={"message": "Checking camera feed", "actor": "bob"},
    )
    assert commented.status_code == 200

    resolved = client.post(
        f"/api/v1/alerts/{alert_id}/resolve",
        headers=_headers(),
        json={"actor": "bob", "note": "False positive"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["incident_status"] == "resolved"
    assert resolved.json()["resolution_note"] == "False positive"

    events = client.get(f"/api/v1/alerts/{alert_id}/events", headers=_headers())
    assert events.status_code == 200
    types = [e["event_type"] for e in events.json()]
    assert "acknowledged" in types
    assert "assigned" in types
    assert "commented" in types
    assert "resolved" in types

    reopened = client.post(
        f"/api/v1/alerts/{alert_id}/reopen",
        headers=_headers(),
        json={"actor": "alice", "note": "Need another look"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["incident_status"] == "open"


def test_filter_alerts_by_incident_status(client):
    alert_id = next(iter(client.store.alerts))  # type: ignore[attr-defined]
    client.post(
        f"/api/v1/alerts/{alert_id}/resolve",
        headers=_headers(),
        json={"actor": "alice"},
    )
    open_alerts = client.get("/api/v1/alerts?incident_status=open", headers=_headers())
    resolved_alerts = client.get(
        "/api/v1/alerts?incident_status=resolved",
        headers=_headers(),
    )
    assert open_alerts.status_code == 200
    assert resolved_alerts.status_code == 200
    assert open_alerts.json() == []
    assert len(resolved_alerts.json()) == 1
    assert resolved_alerts.json()[0]["incident_status"] == "resolved"
