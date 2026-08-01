"""Prometheus /metrics endpoint smoke tests — no Postgres required."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://visionops:visionops_secret@localhost:5434/visionops_db",
)


@pytest.fixture()
def metrics_client(monkeypatch):
    monkeypatch.setenv("VISIONOPS_API_KEY", "")
    monkeypatch.setenv("VISIONOPS_JWT_SECRET", "")
    from app.config import get_settings

    get_settings.cache_clear()

    with (
        patch("app.main.run_migrations"),
        patch("app.main.ensure_bootstrap_admin"),
        patch("app.main.ensure_bucket"),
        patch("app.main.SessionLocal", return_value=MagicMock()),
        patch("app.metrics.refresh_celery_queue_depth"),
    ):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            yield client

    get_settings.cache_clear()


def test_metrics_endpoint_exposes_visionops_series(metrics_client):
    r = metrics_client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "visionops_http_requests_total" in body
    assert "visionops_http_request_duration_seconds" in body
    assert "visionops_alerts_created_total" in body
    assert "visionops_celery_queue_depth" in body


def test_health_still_public(metrics_client):
    r = metrics_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
