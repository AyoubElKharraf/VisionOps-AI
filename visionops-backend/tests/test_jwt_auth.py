"""JWT login and role-based access tests — no Postgres required."""

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
        self.users: dict[uuid.UUID, SimpleNamespace] = {}
        self.cameras: dict[uuid.UUID, SimpleNamespace] = {}

        from app.auth import hash_password

        admin = SimpleNamespace(
            id=uuid.uuid4(),
            username="admin",
            password_hash=hash_password("admin-pass-123"),
            full_name="Admin",
            role="admin",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        operator = SimpleNamespace(
            id=uuid.uuid4(),
            username="operator",
            password_hash=hash_password("operator-pass"),
            full_name="Operator",
            role="operator",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.users[admin.id] = admin
        self.users[operator.id] = operator
        cam = SimpleNamespace(
            id=uuid.uuid4(),
            name="demo-camera",
            source_url="rtsp://127.0.0.1:8554/cam1",
            location="lab",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        self.cameras[cam.id] = cam


class FakeQuery:
    def __init__(self, store: Store, model_name: str):
        self.store = store
        self.model_name = model_name
        self._filters: list = []

    def filter(self, *args):
        self._filters.extend(args)
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        if self.model_name == "User":
            return list(self.store.users.values())
        if self.model_name == "Camera":
            return list(self.store.cameras.values())
        return []

    def count(self):
        return len(self.all())

    def first(self):
        items = self.all()
        for f in self._filters:
            left = getattr(f, "left", None)
            right = getattr(f, "right", None)
            key = getattr(left, "key", None)
            value = getattr(right, "value", right)
            if key == "username":
                for user in self.store.users.values():
                    if user.username == value:
                        return user
                return None
            if key == "name":
                for cam in self.store.cameras.values():
                    if cam.name == value:
                        return cam
                return None
            if key == "id":
                if self.model_name == "User":
                    return self.store.users.get(value)
                if self.model_name == "Camera":
                    return self.store.cameras.get(value)
        return items[0] if items else None


class FakeDb:
    def __init__(self, store: Store):
        self.store = store

    def query(self, model):
        return FakeQuery(self.store, model.__name__)

    def get(self, model, item_id):
        if model.__name__ == "User":
            return self.store.users.get(item_id)
        if model.__name__ == "Camera":
            return self.store.cameras.get(item_id)
        return None

    def add(self, obj):
        if obj.__class__.__name__ == "User" or hasattr(obj, "password_hash"):
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(timezone.utc)
            if getattr(obj, "updated_at", None) is None:
                obj.updated_at = datetime.now(timezone.utc)
            self.store.users[obj.id] = obj
        elif obj.__class__.__name__ == "Camera" or hasattr(obj, "source_url"):
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(timezone.utc)
            self.store.cameras[obj.id] = obj

    def delete(self, obj):
        self.store.cameras.pop(getattr(obj, "id", None), None)
        self.store.users.pop(getattr(obj, "id", None), None)

    def commit(self):
        return None

    def refresh(self, _obj):
        return None

    def flush(self):
        return None


@pytest.fixture()
def jwt_client(monkeypatch):
    monkeypatch.setenv("VISIONOPS_API_KEY", "service-key")
    monkeypatch.setenv("VISIONOPS_JWT_SECRET", "unit-test-jwt-secret-key-32bytes!!")
    monkeypatch.setenv("VISIONOPS_JWT_EXPIRE_MINUTES", "60")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr("app.main.run_migrations", lambda: None)
    monkeypatch.setattr("app.main.ensure_bucket", lambda: "test-bucket")
    monkeypatch.setattr("app.bootstrap.ensure_bootstrap_admin", lambda *_a, **_k: None)

    from app.main import app as fastapi_app
    from app.database import get_db
    from fastapi.testclient import TestClient

    store = Store()

    def fake_db():
        yield FakeDb(store)

    fastapi_app.dependency_overrides[get_db] = fake_db
    with TestClient(fastapi_app) as client:
        client.store = store  # type: ignore[attr-defined]
        yield client

    fastapi_app.dependency_overrides.clear()
    get_settings.cache_clear()
    for key in (
        "VISIONOPS_API_KEY",
        "VISIONOPS_JWT_SECRET",
        "VISIONOPS_JWT_EXPIRE_MINUTES",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()


def _login(client, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_auth_status_reports_modes(jwt_client):
    status = jwt_client.get("/api/v1/auth/status")
    assert status.status_code == 200
    body = status.json()
    assert body["auth_enforced"] is True
    assert body["api_key_enabled"] is True
    assert body["jwt_enabled"] is True


def test_login_and_me(jwt_client):
    token = _login(jwt_client, "admin", "admin-pass-123")
    me = jwt_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert me.json()["role"] == "admin"


def test_login_rejects_bad_password(jwt_client):
    response = jwt_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_operator_can_list_cameras_but_cannot_create(jwt_client):
    token = _login(jwt_client, "operator", "operator-pass")
    headers = {"Authorization": f"Bearer {token}"}

    listed = jwt_client.get("/api/v1/cameras", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    created = jwt_client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "blocked",
            "source_url": "rtsp://127.0.0.1:8554/blocked",
        },
    )
    assert created.status_code == 403


def test_admin_can_create_camera_and_user(jwt_client):
    token = _login(jwt_client, "admin", "admin-pass-123")
    headers = {"Authorization": f"Bearer {token}"}

    created = jwt_client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "gate",
            "source_url": "rtsp://127.0.0.1:8554/gate",
            "location": "North",
        },
    )
    assert created.status_code == 201, created.text

    user = jwt_client.post(
        "/api/v1/auth/users",
        headers=headers,
        json={
            "username": "viewer",
            "password": "viewer-pass",
            "role": "operator",
            "full_name": "Night Viewer",
        },
    )
    assert user.status_code == 201, user.text
    assert user.json()["role"] == "operator"


def test_service_api_key_still_works(jwt_client):
    response = jwt_client.get(
        "/api/v1/cameras",
        headers={"X-API-Key": "service-key"},
    )
    assert response.status_code == 200
