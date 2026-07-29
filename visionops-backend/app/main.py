"""VisionOps AI — Core API (Phases 3–4)."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.minio_client import ensure_bucket
from app.routers import alerts, cameras
from app.routers import stream as stream_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("visionops-backend")

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Real-time computer vision platform API — cameras, alerts, ROI, live detections",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cameras.router, prefix=settings.api_prefix)
app.include_router(alerts.router, prefix=settings.api_prefix)
app.include_router(stream_router.router, prefix=settings.api_prefix)
app.include_router(stream_router.ws_router, prefix=settings.api_prefix)


@app.on_event("startup")
def on_startup() -> None:
    if settings.visionops_api_key:
        logger.info("API key auth enabled for %s/*", settings.api_prefix)
    else:
        logger.warning(
            "VISIONOPS_API_KEY is empty — /api/v1 is open. Set a key for local/demo security."
        )
    init_db()
    try:
        bucket = ensure_bucket()
        logger.info("MinIO bucket ready: %s", bucket)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MinIO not ready yet: %s", exc)
    logger.info("Database tables ensured")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "visionops-backend", "phase": "4"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "visionops-backend",
        "docs": "/docs",
        "health": "/health",
        "api": settings.api_prefix,
        "ws_detections": f"{settings.api_prefix}/ws/detections",
    }
