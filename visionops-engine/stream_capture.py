"""Robust video capture with RTSP reconnect + exponential backoff."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger("visionops-stream")

RTSP_LOW_LATENCY_OPTIONS = (
    "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|reorder_queue_size;0|max_delay;0"
)


def is_live_source(source: str) -> bool:
    lowered = (source or "").strip().lower()
    return lowered.startswith(
        ("rtsp://", "rtsps://", "rtmp://", "http://", "https://")
    )


def open_capture(source: str) -> cv2.VideoCapture:
    if source.startswith("rtsp://") or source.startswith("rtsps://"):
        # Read as close to live as possible: buffered frames would timestamp
        # detections behind the picture the browser already shows.
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", RTSP_LOW_LATENCY_OPTIONS)
        capture = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    else:
        capture = cv2.VideoCapture(source)

    if not capture.isOpened():
        raise RuntimeError(f"Unable to open video source: {source}")
    return capture


def backoff_seconds(attempt: int, initial: float, maximum: float) -> float:
    """attempt is 1-based. Caps at maximum."""
    attempt = max(1, int(attempt))
    delay = float(initial) * (2 ** (attempt - 1))
    return min(float(maximum), delay)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class RobustCapture:
    """Wraps OpenCV VideoCapture and reconnects live streams after read failures."""

    def __init__(
        self,
        source: str,
        *,
        reconnect: bool | None = None,
        initial_delay: float | None = None,
        max_delay: float | None = None,
        fail_threshold: int | None = None,
        open_retries: int | None = None,
    ) -> None:
        self.source = source
        self.reconnect = (
            _env_bool("RTSP_RECONNECT", True)
            if reconnect is None
            else bool(reconnect)
        )
        self.initial_delay = float(
            initial_delay
            if initial_delay is not None
            else os.getenv("RTSP_RECONNECT_INITIAL", "1.0")
        )
        self.max_delay = float(
            max_delay
            if max_delay is not None
            else os.getenv("RTSP_RECONNECT_MAX", "30.0")
        )
        self.fail_threshold = max(
            1,
            int(
                fail_threshold
                if fail_threshold is not None
                else os.getenv("RTSP_FAIL_THRESHOLD", "2")
            ),
        )
        self.open_retries = max(
            1,
            int(
                open_retries
                if open_retries is not None
                else os.getenv("RTSP_OPEN_RETRIES", "8")
            ),
        )
        self._cap: cv2.VideoCapture | None = None
        self._fail_streak = 0
        self.reconnect_count = 0
        self._open_initial()

    @property
    def live(self) -> bool:
        return is_live_source(self.source)

    def _should_reconnect(self) -> bool:
        return self.reconnect and self.live

    def _open_initial(self) -> None:
        last_error: Exception | None = None
        attempts = self.open_retries if self._should_reconnect() else 1
        for attempt in range(1, attempts + 1):
            try:
                self._cap = open_capture(self.source)
                self._set_stream_up(True)
                if attempt > 1:
                    logger.info("Stream opened after %d attempt(s)", attempt)
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if not self._should_reconnect() or attempt >= attempts:
                    break
                delay = backoff_seconds(attempt, self.initial_delay, self.max_delay)
                logger.warning(
                    "Unable to open stream (attempt %d/%d): %s — retry in %.1fs",
                    attempt,
                    attempts,
                    exc,
                    delay,
                )
                time.sleep(delay)
        raise RuntimeError(f"Unable to open video source: {self.source}") from last_error

    def get(self, prop_id: int) -> float:
        if self._cap is None:
            return 0.0
        return float(self._cap.get(prop_id) or 0.0)

    def release(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:  # noqa: BLE001
                pass
            self._cap = None
        self._set_stream_up(False)

    def _reconnect(self) -> bool:
        self.release()
        self.reconnect_count += 1
        self._record_reconnect()
        delay = backoff_seconds(
            min(self.reconnect_count, 10),
            self.initial_delay,
            self.max_delay,
        )
        logger.warning(
            "RTSP reconnect #%d in %.1fs | source=%s",
            self.reconnect_count,
            delay,
            self.source,
        )
        time.sleep(delay)
        try:
            self._cap = open_capture(self.source)
            self._fail_streak = 0
            self._set_stream_up(True)
            logger.info("RTSP reconnect succeeded (#%d)", self.reconnect_count)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("RTSP reconnect failed: %s", exc)
            self._set_stream_up(False)
            return False

    def read(self) -> tuple[bool, np.ndarray | None]:
        """Read next frame; reconnect live sources until success.

        For files / non-live sources, a failed read is treated as EOF.
        """
        while True:
            if self._cap is None:
                if not self._should_reconnect():
                    return False, None
                if not self._reconnect():
                    continue
            assert self._cap is not None
            ok, frame = self._cap.read()
            if ok and frame is not None:
                self._fail_streak = 0
                self._set_stream_up(True)
                return True, frame

            if not self._should_reconnect():
                self._set_stream_up(False)
                return False, None

            self._fail_streak += 1
            if self._fail_streak < self.fail_threshold:
                time.sleep(0.05)
                continue

            if not self._reconnect():
                continue

    def _set_stream_up(self, up: bool) -> None:
        try:
            from metrics_server import set_stream_up

            set_stream_up(up)
        except Exception:  # noqa: BLE001
            pass

    def _record_reconnect(self) -> None:
        try:
            from metrics_server import record_reconnect

            record_reconnect()
        except Exception:  # noqa: BLE001
            pass


def parse_reconnect_args(args: Any) -> dict[str, Any]:
    """Extract RobustCapture kwargs from an argparse Namespace."""
    return {
        "reconnect": bool(getattr(args, "rtsp_reconnect", True)),
        "initial_delay": float(getattr(args, "rtsp_reconnect_initial", 1.0)),
        "max_delay": float(getattr(args, "rtsp_reconnect_max", 30.0)),
        "fail_threshold": int(getattr(args, "rtsp_fail_threshold", 2)),
        "open_retries": int(getattr(args, "rtsp_open_retries", 8)),
    }
