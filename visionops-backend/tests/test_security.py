"""Unit tests for production security hardening guards."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://visionops:visionops_secret@localhost:5434/visionops_db",
)


def _settings(**overrides):
    base = dict(
        visionops_env="development",
        visionops_strict_secrets=False,
        cors_origins="*",
        visionops_api_key="visionops-dev-key",
        visionops_jwt_secret="visionops-dev-jwt-secret-change-me",
        visionops_jwt_expire_minutes=480,
        visionops_admin_password="visionops-admin",
        database_url="postgresql://visionops:visionops_secret@localhost:5434/visionops_db",
        minio_endpoint="localhost:9001",
        minio_root_password="visionops_minio_secret",
        minio_secure=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_development_warns_but_allows_defaults():
    from app.security import evaluate_security

    findings = evaluate_security(_settings())
    codes = {f.code for f in findings}
    assert "api_key_weak" in codes
    assert "jwt_weak" in codes
    assert all(f.level == "warning" for f in findings if f.code.endswith("_weak"))


def test_production_rejects_dev_defaults():
    from app.security import assert_secure_startup, evaluate_security

    settings = _settings(visionops_env="production", cors_origins="https://ops.example.com")
    findings = evaluate_security(settings)
    assert any(f.level == "error" for f in findings)
    with pytest.raises(RuntimeError, match="insecure production"):
        assert_secure_startup(settings)


def test_production_accepts_strong_secrets():
    from app.security import assert_secure_startup, evaluate_security

    settings = _settings(
        visionops_env="production",
        cors_origins="https://ops.example.com,https://admin.example.com",
        visionops_api_key="prod-service-key-9f3c2a1b7e8d4c6a",
        visionops_jwt_secret="prod-jwt-signing-secret-32chars-min!!",
        visionops_admin_password="Correct-Horse-Battery-Staple-9",
        database_url="postgresql://visionops:DbPass-Strong-918273@db:5432/visionops_db",
        minio_root_password="MinioPass-Strong-445566",
        minio_secure=True,
        visionops_jwt_expire_minutes=60,
    )
    findings = evaluate_security(settings)
    assert not any(f.level == "error" for f in findings)
    assert_secure_startup(settings) == findings


def test_cors_origin_list_parses_csv():
    from app.security import cors_origin_list

    assert cors_origin_list(_settings(cors_origins="*")) == ["*"]
    assert cors_origin_list(
        _settings(cors_origins=" https://a.example ,https://b.example ")
    ) == ["https://a.example", "https://b.example"]


def test_strict_flag_enforces_without_production_env():
    from app.security import assert_secure_startup

    with pytest.raises(RuntimeError):
        assert_secure_startup(_settings(visionops_strict_secrets=True, cors_origins="https://x.test"))
