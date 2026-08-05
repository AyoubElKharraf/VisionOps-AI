"""Production hardening — secret strength and auth enforcement checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.config import Settings

# Well-known compose / .env.example defaults that must never ship to production.
KNOWN_INSECURE_VALUES = frozenset(
    {
        "",
        "admin",
        "password",
        "secret",
        "changeme",
        "change-me",
        "visionops-dev-key",
        "visionops-dev-jwt-secret-change-me",
        "visionops-admin",
        "visionops_secret",
        "visionops_minio",
        "visionops_minio_secret",
        "minioadmin",
        "minioadmin123",
    }
)


@dataclass(frozen=True)
class SecurityFinding:
    level: str  # "error" | "warning"
    code: str
    message: str


def is_production(settings: Settings) -> bool:
    env = (settings.visionops_env or "development").strip().lower()
    return env in {"production", "prod"}


def _is_insecure(value: str | None, *, min_len: int) -> bool:
    text = (value or "").strip()
    if len(text) < min_len:
        return True
    if text.lower() in KNOWN_INSECURE_VALUES:
        return True
    # Reject trivial repeats / keyboard walks lightly
    if len(set(text.lower())) < 4 and len(text) < 24:
        return True
    return False


def _db_password(database_url: str) -> str | None:
    try:
        parsed = urlparse(database_url)
    except ValueError:
        return None
    return parsed.password


def cors_origin_list(settings: Settings) -> list[str]:
    raw = (settings.cors_origins or "*").strip()
    if not raw or raw == "*":
        return ["*"]
    return [part.strip() for part in raw.split(",") if part.strip()]


def evaluate_security(settings: Settings) -> list[SecurityFinding]:
    """Return security findings for the current settings (errors + warnings)."""
    findings: list[SecurityFinding] = []
    prod = is_production(settings)
    strict = prod or bool(settings.visionops_strict_secrets)

    def add(level: str, code: str, message: str) -> None:
        findings.append(SecurityFinding(level=level, code=code, message=message))

    api_key = settings.visionops_api_key or ""
    jwt_secret = settings.visionops_jwt_secret or ""
    admin_password = settings.visionops_admin_password or ""

    if not api_key and not jwt_secret:
        add(
            "error" if strict else "warning",
            "auth_open",
            "Neither VISIONOPS_API_KEY nor VISIONOPS_JWT_SECRET is set — /api/v1 is open.",
        )

    if strict and not api_key:
        add("error", "api_key_missing", "VISIONOPS_API_KEY is required in production.")
    elif api_key and _is_insecure(api_key, min_len=16 if not strict else 24):
        add(
            "error" if strict else "warning",
            "api_key_weak",
            "VISIONOPS_API_KEY looks weak or matches a known development default.",
        )

    if strict and not jwt_secret:
        add("error", "jwt_missing", "VISIONOPS_JWT_SECRET is required in production.")
    elif jwt_secret and _is_insecure(jwt_secret, min_len=24 if not strict else 32):
        add(
            "error" if strict else "warning",
            "jwt_weak",
            "VISIONOPS_JWT_SECRET looks weak or matches a known development default.",
        )

    if admin_password and _is_insecure(admin_password, min_len=8 if not strict else 12):
        add(
            "error" if strict else "warning",
            "admin_password_weak",
            "VISIONOPS_ADMIN_PASSWORD looks weak or matches a known development default.",
        )

    db_password = _db_password(settings.database_url)
    if db_password is not None and _is_insecure(db_password, min_len=8 if not strict else 12):
        add(
            "error" if strict else "warning",
            "database_password_weak",
            "DATABASE_URL password looks weak or matches a known development default.",
        )

    if settings.minio_root_password and _is_insecure(
        settings.minio_root_password, min_len=8 if not strict else 12
    ):
        add(
            "error" if strict else "warning",
            "minio_password_weak",
            "MINIO_ROOT_PASSWORD looks weak or matches a known development default.",
        )

    origins = cors_origin_list(settings)
    if strict and origins == ["*"]:
        add(
            "error",
            "cors_wildcard",
            "CORS_ORIGINS must be an explicit allow-list in production (not *).",
        )

    if settings.visionops_jwt_expire_minutes > 60 * 24:
        add(
            "warning",
            "jwt_ttl_long",
            "VISIONOPS_JWT_EXPIRE_MINUTES exceeds 24h — prefer shorter sessions in production.",
        )

    if prod and not settings.minio_secure and not re.search(
        r"(localhost|127\.0\.0\.1)", settings.minio_endpoint or ""
    ):
        add(
            "warning",
            "minio_insecure",
            "MINIO_SECURE=false while not on localhost — enable TLS for object storage in production.",
        )

    return findings


def assert_secure_startup(settings: Settings) -> list[SecurityFinding]:
    """
    Log-friendly gate used at process start.

    Raises RuntimeError when production/strict mode has error-level findings.
    """
    findings = evaluate_security(settings)
    errors = [f for f in findings if f.level == "error"]
    if errors:
        details = "; ".join(f"{f.code}: {f.message}" for f in errors)
        raise RuntimeError(f"Refusing to start with insecure production settings — {details}")
    return findings
