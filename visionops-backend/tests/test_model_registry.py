"""Unit tests for model registry upload / activate / download."""

from __future__ import annotations

import hashlib
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


class ModelStore:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, SimpleNamespace] = {}

    def add(self, row: SimpleNamespace) -> SimpleNamespace:
        self.rows[row.id] = row
        return row


class FakeDB:
    def __init__(self, store: ModelStore) -> None:
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

    def all(self):
        rows = list(self.store.rows.values())
        for f in self._filters:
            left = getattr(f, "left", None)
            key = getattr(left, "key", None)
            right = getattr(f, "right", None)
            value = getattr(right, "value", right)
            if key == "role" and value is not None:
                rows = [r for r in rows if r.role == value or getattr(r.role, "value", r.role) == getattr(value, "value", value)]
            if key == "is_active":
                rows = [r for r in rows if r.is_active]
            if key == "name" and value is not None:
                rows = [r for r in rows if r.name == value]
            if key == "version" and value is not None:
                rows = [r for r in rows if r.version == value]
        return rows

    def first(self):
        items = self.all()
        return items[0] if items else None

    def get(self, model, key):  # noqa: ANN001
        return self.store.rows.get(key)

    def add(self, obj):  # noqa: ANN001
        self._pending = obj
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.store.rows[obj.id] = obj

    def flush(self):
        pass

    def commit(self):
        pass

    def refresh(self, obj):  # noqa: ANN001
        pass

    def delete(self, obj):  # noqa: ANN001
        self.store.rows.pop(obj.id, None)


@pytest.fixture()
def models_client(monkeypatch):
    monkeypatch.setenv("VISIONOPS_API_KEY", "")
    monkeypatch.setenv("VISIONOPS_JWT_SECRET", "")
    from app.config import get_settings

    get_settings.cache_clear()
    store = ModelStore()
    uploaded: dict[str, bytes] = {}

    monkeypatch.setattr("app.main.run_migrations", lambda: None)
    monkeypatch.setattr("app.main.ensure_bucket", lambda: "test-bucket")
    monkeypatch.setattr(
        "app.routers.models.upload_bytes",
        lambda key, data, content_type: uploaded.setdefault(key, data) or key,
    )
    monkeypatch.setattr(
        "app.routers.models.download_object_bytes",
        lambda key: uploaded.get(key),
    )
    monkeypatch.setattr("app.routers.models.delete_object", lambda key: True)
    monkeypatch.setattr("app.routers.models.presigned_get_url", lambda *_a, **_k: None)

    from app.main import app as fastapi_app
    from app.database import get_db
    from fastapi.testclient import TestClient

    def _db():
        yield FakeDB(store)

    fastapi_app.dependency_overrides[get_db] = _db
    with TestClient(fastapi_app) as client:
        yield client, store, uploaded
    fastapi_app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_upload_activate_and_download(models_client):
    client, store, uploaded = models_client
    payload = b"FAKE_ONNX_WEIGHTS_V1"
    files = {"file": ("yolov8n_416.onnx", payload, "application/octet-stream")}
    data = {
        "name": "yolov8n",
        "version": "1.0.0",
        "role": "detector",
        "notes": "ci fixture",
        "activate": "true",
    }
    r = client.post("/api/v1/models", data=data, files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "yolov8n"
    assert body["version"] == "1.0.0"
    assert body["role"] == "detector"
    assert body["format"] == "onnx"
    assert body["is_active"] is True
    assert body["sha256"] == hashlib.sha256(payload).hexdigest()
    assert body["object_key"] in uploaded

    listed = client.get("/api/v1/models")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    active = client.get("/api/v1/models/active")
    assert active.status_code == 200
    assert active.json()["detector"]["id"] == body["id"]
    assert active.json()["ppe"] is None

    # Second version, then activate it (deactivates first)
    payload2 = b"FAKE_ONNX_WEIGHTS_V2"
    r2 = client.post(
        "/api/v1/models",
        data={
            "name": "yolov8n",
            "version": "1.1.0",
            "role": "detector",
            "activate": "false",
        },
        files={"file": ("yolov8n_416.onnx", payload2, "application/octet-stream")},
    )
    assert r2.status_code == 201, r2.text
    mid = r2.json()["id"]
    act = client.post(f"/api/v1/models/{mid}/activate")
    assert act.status_code == 200
    assert act.json()["is_active"] is True

    active2 = client.get("/api/v1/models/active").json()
    assert active2["detector"]["version"] == "1.1.0"

    # Old active entry should be false in store
    active_count = sum(1 for row in store.rows.values() if row.is_active)
    assert active_count == 1

    dl = client.get(f"/api/v1/models/{mid}/download")
    assert dl.status_code == 200
    assert dl.content == payload2


def test_cannot_delete_active_model(models_client):
    client, store, _uploaded = models_client
    # Seed an active row without going through MinIO path edge cases
    from app.models import ModelFormat, ModelRole

    mid = uuid.uuid4()
    store.add(
        SimpleNamespace(
            id=mid,
            name="ppe-net",
            version="0.1.0",
            role=ModelRole.ppe,
            format=ModelFormat.pytorch,
            filename="hardhat.pt",
            object_key=f"models/ppe/{mid}/hardhat.pt",
            sha256="abc",
            size_bytes=3,
            is_active=True,
            notes=None,
            created_by="service",
            created_at=datetime.now(timezone.utc),
            activated_at=datetime.now(timezone.utc),
        )
    )
    r = client.delete(f"/api/v1/models/{mid}")
    assert r.status_code == 409
