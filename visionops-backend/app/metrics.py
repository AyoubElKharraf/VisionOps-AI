"""Prometheus metrics for the VisionOps backend."""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlsplit

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings

logger = logging.getLogger("visionops-backend.metrics")

HTTP_REQUESTS = Counter(
    "visionops_http_requests_total",
    "Total HTTP requests handled by the VisionOps API",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "visionops_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
ALERTS_CREATED = Counter(
    "visionops_alerts_created_total",
    "Alerts successfully created",
    ["alert_type"],
)
CELERY_QUEUE_DEPTH = Gauge(
    "visionops_celery_queue_depth",
    "Approximate Celery broker queue depth (Redis LLEN)",
)

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def normalize_route(path: str) -> str:
    path = path.split("?", 1)[0] or "/"
    return _UUID_RE.sub("{id}", path)


def record_alert_created(alert_type: str) -> None:
    ALERTS_CREATED.labels(alert_type=alert_type or "unknown").inc()


def refresh_celery_queue_depth() -> None:
    """Best-effort Redis LLEN on the default Celery queue."""
    settings = get_settings()
    try:
        import redis

        parsed = urlsplit(settings.celery_broker_url)
        db = int((parsed.path or "/0").lstrip("/") or "0")
        client = redis.Redis(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            db=db,
            password=parsed.password,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        depth = int(client.llen("celery"))
        CELERY_QUEUE_DEPTH.set(depth)
        client.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Celery queue depth unavailable: %s", exc)


def metrics_response() -> Response:
    refresh_celery_queue_depth()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


class PrometheusMiddleware:
    """ASGI middleware that records HTTP request counts and durations."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or "/"
        if path == "/metrics":
            await self.app(scope, receive, send)
            return

        method = scope.get("method") or "GET"
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = path
            endpoint = scope.get("route")
            if endpoint is not None and getattr(endpoint, "path", None):
                route = endpoint.path
            else:
                route = normalize_route(path)
            labels = {"method": method, "route": route}
            HTTP_DURATION.labels(**labels).observe(time.perf_counter() - started)
            HTTP_REQUESTS.labels(
                method=method,
                route=route,
                status=str(status_code),
            ).inc()
