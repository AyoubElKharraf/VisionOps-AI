"""HTTP client used by the vision engine to push alerts / detections (non-blocking)."""

from __future__ import annotations

import base64
import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

import cv2
import numpy as np
import requests

logger = logging.getLogger("visionops-alert-client")


class AlertClient:
    """
    Network I/O runs in a background thread so the inference loop stays fast.
    Detection pushes use latest-wins: if a previous POST is still in-flight, skip.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8001",
        timeout: float = 2.0,
        detection_timeout: float = 0.4,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.detection_timeout = detection_timeout
        self._session = requests.Session()
        if api_key:
            self._session.headers["X-API-Key"] = api_key
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vo-net")
        self._det_future: Future | None = None
        self._roi_future: Future | None = None

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._session.close()

    def encode_snapshot(self, frame: np.ndarray, quality: int = 70) -> str:
        # Downscale before encode to cut payload size / CPU
        h, w = frame.shape[:2]
        if max(h, w) > 960:
            scale = 960 / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            raise RuntimeError("Failed to encode JPEG snapshot")
        return base64.b64encode(buf.tobytes()).decode("ascii")

    def create_alert(
        self,
        *,
        alert_type: str,
        message: str,
        camera_name: str = "demo-camera",
        zone_name: str | None = None,
        class_name: str | None = None,
        track_id: int | None = None,
        confidence: float | None = None,
        source_video_path: str | None = None,
        frame_index: int | None = None,
        snapshot_frame: np.ndarray | None = None,
        metadata: dict[str, Any] | None = None,
        enqueue_media: bool = True,
    ) -> None:
        """Fire-and-forget alert POST (does not block inference)."""
        snapshot_b64 = None
        if snapshot_frame is not None:
            try:
                snapshot_b64 = self.encode_snapshot(snapshot_frame)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Snapshot encode failed: %s", exc)

        payload: dict[str, Any] = {
            "camera_name": camera_name,
            "alert_type": alert_type,
            "message": message,
            "zone_name": zone_name,
            "class_name": class_name,
            "track_id": track_id,
            "confidence": confidence,
            "source_video_path": source_video_path,
            "frame_index": frame_index,
            "metadata": metadata or {},
            "enqueue_media": enqueue_media,
            "snapshot_base64": snapshot_b64,
        }
        self._pool.submit(self._post_alert, payload)

    def _post_alert(self, payload: dict[str, Any]) -> None:
        url = f"{self.base_url}/api/v1/alerts"
        try:
            resp = self._session.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            logger.info("Alert posted id=%s status=%s", data.get("id"), data.get("status"))
        except requests.RequestException as exc:
            logger.warning("Failed to post alert to %s: %s", url, exc)

    def push_detections(
        self,
        *,
        width: int,
        height: int,
        frame_index: int,
        captured_at_ms: int,
        boxes: list[dict],
        infer_ms: float | None = None,
        source_position_ms: float | None = None,
        zone_alerts: list[str] | None = None,
        camera_name: str = "demo-camera",
    ) -> bool:
        """
        Non-blocking detection push. Returns False if skipped (previous still sending).
        """
        if self._det_future is not None and not self._det_future.done():
            return False  # drop frame — keep inference realtime

        payload = {
            "camera_name": camera_name,
            "frame_index": frame_index,
            "captured_at_ms": captured_at_ms,
            "sent_at_ms": time.time_ns() // 1_000_000,
            "source_position_ms": source_position_ms,
            "width": width,
            "height": height,
            "infer_ms": infer_ms,
            "boxes": boxes,
            "zone_alerts": zone_alerts or [],
        }
        self._det_future = self._pool.submit(self._post_detections, payload)
        return True

    def _post_detections(self, payload: dict[str, Any]) -> None:
        url = f"{self.base_url}/api/v1/detections"
        try:
            resp = self._session.post(url, json=payload, timeout=self.detection_timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.debug("Detection push failed: %s", exc)

    def request_roi_zones(self, camera_name: str = "demo-camera") -> bool:
        """Start a non-blocking ROI refresh unless one is already in flight."""
        if self._roi_future is not None and not self._roi_future.done():
            return False
        self._roi_future = self._pool.submit(self._get_roi_zones, camera_name)
        return True

    def poll_roi_zones(self) -> tuple[bool, list[dict[str, Any]]]:
        """Return (updated, zones); failures keep the current engine configuration."""
        if self._roi_future is None or not self._roi_future.done():
            return False, []
        future = self._roi_future
        self._roi_future = None
        try:
            zones = future.result()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ROI refresh failed: %s", exc)
            return False, []
        return (True, zones) if zones is not None else (False, [])

    def _get_roi_zones(self, camera_name: str) -> list[dict[str, Any]] | None:
        url = f"{self.base_url}/api/v1/roi-zones"
        try:
            resp = self._session.get(
                url,
                params={"camera_name": camera_name},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError("ROI endpoint did not return a list")
            return data
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Failed to load ROI zones from %s: %s", url, exc)
            return None
