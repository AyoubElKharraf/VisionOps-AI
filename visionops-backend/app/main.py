"""VisionOps AI — Core API (Phases 3–5 + JWT auth)."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import auth_enforced
from app.bootstrap import ensure_bootstrap_admin
from app.config import get_settings
from app.database import SessionLocal, run_migrations
from app.metrics import PrometheusMiddleware, metrics_response
from app.minio_client import ensure_bucket
from app.routers import alerts, auth, cameras, models, notifications, retention
from app.routers import stream as stream_router
from app.security import assert_secure_startup, cors_origin_list, evaluate_security, is_production

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("visionops-backend")

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Real-time computer vision platform API — cameras, alerts, ROI, live detections",
    version="0.5.0",
)

app.add_middleware(PrometheusMiddleware)
_cors_origins = cors_origin_list(settings)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(cameras.router, prefix=settings.api_prefix)
app.include_router(alerts.router, prefix=settings.api_prefix)
app.include_router(models.router, prefix=settings.api_prefix)
app.include_router(notifications.router, prefix=settings.api_prefix)
app.include_router(retention.router, prefix=settings.api_prefix)
app.include_router(stream_router.router, prefix=settings.api_prefix)
app.include_router(stream_router.ws_router, prefix=settings.api_prefix)


@app.on_event("startup")
def on_startup() -> None:
    findings = evaluate_security(settings)
    for finding in findings:
        log = logger.error if finding.level == "error" else logger.warning
        log("security[%s] %s", finding.code, finding.message)
    if is_production(settings) or settings.visionops_strict_secrets:
        assert_secure_startup(settings)

    if settings.visionops_api_key:
        logger.info("Service API-key auth enabled for %s/*", settings.api_prefix)
    if settings.visionops_jwt_secret:
        logger.info("JWT user auth enabled for %s/*", settings.api_prefix)
    if not auth_enforced():
        logger.warning(
            "Neither VISIONOPS_API_KEY nor VISIONOPS_JWT_SECRET is set — /api/v1 is open."
        )
    logger.info(
        "Environment=%s | CORS origins=%s",
        settings.visionops_env,
        ",".join(_cors_origins),
    )

    run_migrations()
    try:
        db = SessionLocal()
        try:
            ensure_bootstrap_admin(db, settings)
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not bootstrap admin user: %s", exc)

    try:
        bucket = ensure_bucket()
        logger.info("MinIO bucket ready: %s", bucket)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MinIO not ready yet: %s", exc)
    logger.info("Database migrations applied (Alembic head)")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "visionops-backend",
        "phase": "5",
        "environment": settings.visionops_env,
    }


@app.get("/metrics")
def metrics():
    return metrics_response()


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "visionops-backend",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
        "api": settings.api_prefix,
        "auth_login": f"{settings.api_prefix}/auth/login",
        "ws_detections": f"{settings.api_prefix}/ws/detections",
    }
