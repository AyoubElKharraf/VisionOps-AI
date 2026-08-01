"""Prometheus metrics HTTP server for the VisionOps engine process."""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from prometheus_client import Counter, Gauge, Histogram, start_http_server

logger = logging.getLogger("visionops-engine.metrics")

ENGINE_FPS = Gauge("visionops_engine_fps", "Rolling inference FPS")
ENGINE_INFER_MS = Gauge("visionops_engine_infer_ms", "Latest inference latency in milliseconds")
ENGINE_INFER_HIST = Histogram(
    "visionops_engine_infer_duration_seconds",
    "Inference latency histogram in seconds",
    buckets=(0.005, 0.01, 0.02, 0.035, 0.05, 0.075, 0.1, 0.15, 0.25, 0.5, 1.0),
)
ENGINE_FRAMES = Counter("visionops_engine_frames_total", "Frames processed by the engine")
ENGINE_DETECTIONS = Counter(
    "visionops_engine_detections_total",
    "Detection boxes produced by the engine",
)
ENGINE_ALERTS_POSTED = Counter(
    "visionops_engine_alerts_posted_total",
    "Alerts successfully posted to the backend",
)

_started = False
_lock = threading.Lock()


def start_metrics_server(port: Optional[int] = None) -> int:
    """Start the Prometheus scrape endpoint once. Returns the listen port."""
    global _started
    listen_port = int(port if port is not None else os.getenv("METRICS_PORT", "9101"))
    with _lock:
        if _started:
            return listen_port
        start_http_server(listen_port)
        _started = True
        logger.info("Prometheus metrics listening on :%d", listen_port)
    return listen_port


def record_frame(*, fps: float, infer_ms: float, detection_count: int) -> None:
    ENGINE_FPS.set(max(0.0, fps))
    ENGINE_INFER_MS.set(max(0.0, infer_ms))
    if infer_ms > 0:
        ENGINE_INFER_HIST.observe(infer_ms / 1000.0)
    ENGINE_FRAMES.inc()
    if detection_count > 0:
        ENGINE_DETECTIONS.inc(detection_count)


def record_alert_posted() -> None:
    ENGINE_ALERTS_POSTED.inc()
