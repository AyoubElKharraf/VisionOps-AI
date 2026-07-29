"""API key auth tests — no Postgres required."""

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


class FakeCameraStore:
    def __init__(self) -> None:
        self.cameras: dict[uuid.UUID, SimpleNamespace] = {}

    def seed(self, **kwargs: object) -> SimpleNamespace:
        cam = SimpleNamespace(
            id=uuid.uuid4(),
            name="demo-camera",
            source_url="rtsp://127.0.0.1:8554/cam1",
            location="lab",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            **kwargs,
        )
        self.cameras[cam.id] = cam
        return cam


class FakeDb:
    def __init__(self, store: FakeCameraStore) -> None:
        self.store = store
        self._model = None
        self._filters: list = []
        self._pending: SimpleNamespace | None = None

    def query(self, model):  # noqa: ANN001
        self._model = model
        self._filters = []
        return self

    def filter(self, *args):  # noqa: ANN001
        self._filters.extend(args)
        return self

    def order_by(self, *_args):  # noqa: ANN001
        return self

    def all(self):  # noqa: ANN001
        cams = list(self.store.cameras.values())
        if self._filters:
            # active_only uses Camera.is_active.is_(True)
            cams = [c for c in cams if c.is_active]
        return cams

    def first(self):
        name = None
        for f in self._filters:
            left = getattr(f, "left", None)
            right = getattr(f, "right", None)
            if getattr(left, "key", None) == "name" and right is not None:
                name = getattr(right, "value", right)
        if name is not None:
            for cam in self.store.cameras.values():
                if cam.name == name:
                    return cam
            return None
        return next(iter(self.store.cameras.values()), None)

    def get(self, model, item_id):  # noqa: ANN001
        return self.store.cameras.get(item_id)

    def add(self, obj):  # noqa: ANN001
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        self._pending = obj
        self.store.cameras[obj.id] = obj

    def delete(self, obj):  # noqa: ANN001
        self.store.cameras.pop(obj.id, None)

    def commit(self) -> None:
        return None

    def refresh(self, obj):  # noqa: ANN001
        return None

    def flush(self) -> None:
        return None


@pytest.fixture()
def auth_client(monkeypatch):
    monkeypatch.setenv("VISIONOPS_API_KEY", "test-secret-key")
    from app.config import get_settings

    get_settings.cache_clear()

    monkeypatch.setattr("app.main.init_db", lambda: None)
    monkeypatch.setattr("app.main.ensure_bucket", lambda: "test-bucket")

    from app.main import app as fastapi_app
    from app.database import get_db
    from fastapi.testclient import TestClient

    store = FakeCameraStore()
    store.seed()

    def fake_db():
        yield FakeDb(store)

    fastapi_app.dependency_overrides[get_db] = fake_db
    with TestClient(fastapi_app) as client:
        client.fake_camera_store = store  # type: ignore[attr-defined]
        yield client

    fastapi_app.dependency_overrides.clear()
    get_settings.cache_clear()
    monkeypatch.delenv("VISIONOPS_API_KEY", raising=False)
    get_settings.cache_clear()


def _headers() -> dict[str, str]:
    return {"X-API-Key": "test-secret-key"}


def test_health_stays_public(auth_client):
    r = auth_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_api_rejects_missing_key(auth_client):
    r = auth_client.get("/api/v1/cameras")
    assert r.status_code == 401
    assert "API key" in r.json()["detail"]


def test_api_rejects_wrong_key(auth_client):
    r = auth_client.get("/api/v1/cameras", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_api_accepts_header_key(auth_client):
    r = auth_client.get("/api/v1/detections/latest", headers=_headers())
    assert r.status_code == 200
    assert "boxes" in r.json()


def test_api_accepts_query_key(auth_client):
    r = auth_client.get("/api/v1/detections/latest?api_key=test-secret-key")
    assert r.status_code == 200


def test_list_and_update_camera(auth_client):
    listed = auth_client.get("/api/v1/cameras", headers=_headers())
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    camera_id = listed.json()[0]["id"]

    updated = auth_client.patch(
        f"/api/v1/cameras/{camera_id}",
        headers=_headers(),
        json={"location": "Warehouse B", "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["location"] == "Warehouse B"
    assert updated.json()["is_active"] is False


def test_create_and_delete_camera(auth_client):
    created = auth_client.post(
        "/api/v1/cameras",
        headers=_headers(),
        json={
            "name": "entrance",
            "source_url": "rtsp://127.0.0.1:8554/entrance",
            "location": "Gate",
        },
    )
    assert created.status_code == 201, created.text
    camera_id = created.json()["id"]

    deleted = auth_client.delete(f"/api/v1/cameras/{camera_id}", headers=_headers())
    assert deleted.status_code == 204

    missing = auth_client.get(f"/api/v1/cameras/{camera_id}", headers=_headers())
    assert missing.status_code == 404


def test_detection_frame_is_enriched_with_camera_and_receive_time(auth_client):
    captured_at_ms = 1_722_000_000_000
    r = auth_client.post(
        "/api/v1/detections",
        headers=_headers(),
        json={
            "camera_name": "demo-camera",
            "frame_index": 42,
            "captured_at_ms": captured_at_ms,
            "sent_at_ms": captured_at_ms + 10,
            "source_position_ms": 1680.0,
            "width": 1920,
            "height": 1080,
            "boxes": [],
            "zone_alerts": [],
        },
    )
    assert r.status_code == 200
    assert r.json()["camera_id"]
    assert r.json()["received_at_ms"] >= captured_at_ms

    latest = auth_client.get("/api/v1/detections/latest", headers=_headers()).json()
    assert latest["camera_id"] == r.json()["camera_id"]
    assert latest["captured_at_ms"] == captured_at_ms
    assert latest["source_position_ms"] == 1680.0


def test_websocket_rejects_missing_key(auth_client):
    with pytest.raises(Exception):
        with auth_client.websocket_connect("/api/v1/ws/detections"):
            pass


def test_websocket_accepts_query_key(auth_client):
    with auth_client.websocket_connect(
        "/api/v1/ws/detections?api_key=test-secret-key"
    ) as ws:
        ws.close()
