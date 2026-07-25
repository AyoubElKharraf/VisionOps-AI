"""Backend API tests — uses Postgres when DATABASE_URL is set (CI service)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# CI sets DATABASE_URL to :5432; local VisionOps compose uses :5434
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://visionops:visionops_secret@localhost:5434/visionops_db",
)
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9001")
os.environ.setdefault("MINIO_ROOT_USER", "visionops_minio")
os.environ.setdefault("MINIO_ROOT_PASSWORD", "visionops_minio_secret")
os.environ.setdefault("MINIO_BUCKET", "visionops-media-test")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")


@pytest.fixture(scope="session")
def app():
    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "visionops-backend"


def test_create_and_list_camera(client):
    name = "ci-cam-phase5"
    # cleanup-ish: create may 409 if rerun
    r = client.post(
        "/api/v1/cameras",
        json={"name": name, "source_url": "file://demo", "location": "ci"},
    )
    assert r.status_code in (201, 409)
    listed = client.get("/api/v1/cameras")
    assert listed.status_code == 200
    names = [c["name"] for c in listed.json()]
    assert name in names


def test_create_roi_zone(client):
    r = client.post(
        "/api/v1/roi-zones",
        json={
            "camera_name": "ci-cam-phase5",
            "name": "ci_zone",
            "points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
            "color": "#ef4444",
            "max_allowed_objects": 0,
            "forbidden_classes": ["person"],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "ci_zone"
    assert len(body["points"]) == 4

    zones = client.get("/api/v1/roi-zones?camera_name=ci-cam-phase5")
    assert zones.status_code == 200
    assert any(z["name"] == "ci_zone" for z in zones.json())


def test_ingest_detections(client):
    r = client.post(
        "/api/v1/detections",
        json={
            "camera_name": "ci-cam-phase5",
            "frame_index": 7,
            "width": 640,
            "height": 480,
            "infer_ms": 12.3,
            "boxes": [
                {
                    "x1": 10,
                    "y1": 20,
                    "x2": 40,
                    "y2": 80,
                    "confidence": 0.91,
                    "class_id": 0,
                    "class_name": "person",
                }
            ],
            "zone_alerts": [],
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    latest = client.get("/api/v1/detections/latest")
    assert latest.status_code == 200
    assert latest.json()["frame_index"] == 7
    assert len(latest.json()["boxes"]) == 1


def test_create_alert_without_media(client):
    r = client.post(
        "/api/v1/alerts",
        json={
            "camera_name": "ci-cam-phase5",
            "alert_type": "roi_intrusion",
            "message": "CI test alert",
            "zone_name": "ci_zone",
            "class_name": "person",
            "enqueue_media": False,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["message"] == "CI test alert"
    assert body["status"] == "pending"
