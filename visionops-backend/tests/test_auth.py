"""API key auth tests — no Postgres required."""

from __future__ import annotations

import os
import sys
import uuid
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
def auth_client(monkeypatch):
    monkeypatch.setenv("VISIONOPS_API_KEY", "test-secret-key")
    from app.config import get_settings

    get_settings.cache_clear()

    monkeypatch.setattr("app.main.init_db", lambda: None)
    monkeypatch.setattr("app.main.ensure_bucket", lambda: "test-bucket")

    from app.main import app as fastapi_app
    from app.database import get_db
    from fastapi.testclient import TestClient

    camera = SimpleNamespace(id=uuid.uuid4())

    class FakeDb:
        def query(self, _model):
            return self

        def filter(self, *_args):
            return self

        def first(self):
            return camera

    def fake_db():
        yield FakeDb()

    fastapi_app.dependency_overrides[get_db] = fake_db
    with TestClient(fastapi_app) as client:
        yield client

    fastapi_app.dependency_overrides.clear()
    get_settings.cache_clear()
    monkeypatch.delenv("VISIONOPS_API_KEY", raising=False)
    get_settings.cache_clear()


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
    r = auth_client.get(
        "/api/v1/detections/latest",
        headers={"X-API-Key": "test-secret-key"},
    )
    assert r.status_code == 200
    assert "boxes" in r.json()


def test_api_accepts_query_key(auth_client):
    r = auth_client.get("/api/v1/detections/latest?api_key=test-secret-key")
    assert r.status_code == 200


def test_detection_frame_is_enriched_with_camera_and_receive_time(auth_client):
    captured_at_ms = 1_722_000_000_000
    r = auth_client.post(
        "/api/v1/detections",
        headers={"X-API-Key": "test-secret-key"},
        json={
            "camera_name": "isolated-sync-camera",
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

    latest = auth_client.get(
        "/api/v1/detections/latest",
        headers={"X-API-Key": "test-secret-key"},
    ).json()
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
