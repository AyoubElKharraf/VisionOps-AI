"""Unit tests for RTSP reconnect helpers — no live camera required."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from stream_capture import (
    RobustCapture,
    backoff_seconds,
    is_live_source,
)


def test_is_live_source():
    assert is_live_source("rtsp://mediamtx:8554/cam1")
    assert is_live_source("rtsps://host/stream")
    assert is_live_source("http://127.0.0.1:8888/cam1")
    assert not is_live_source("data/demo.mp4")
    assert not is_live_source("")


def test_backoff_seconds_caps():
    assert backoff_seconds(1, 1.0, 30.0) == 1.0
    assert backoff_seconds(2, 1.0, 30.0) == 2.0
    assert backoff_seconds(3, 1.0, 30.0) == 4.0
    assert backoff_seconds(10, 1.0, 30.0) == 30.0


def test_file_eof_does_not_reconnect():
    fake_cap = MagicMock()
    fake_cap.isOpened.return_value = True
    fake_cap.read.return_value = (False, None)
    fake_cap.get.return_value = 0

    with patch("stream_capture.open_capture", return_value=fake_cap):
        capture = RobustCapture("data/demo.mp4", reconnect=True, open_retries=1)
        ok, frame = capture.read()

    assert ok is False
    assert frame is None
    assert capture.reconnect_count == 0
    capture.release()


def test_rtsp_reconnects_after_failures():
    class FailingCap:
        def isOpened(self):
            return True

        def read(self):
            return False, None

        def get(self, _prop):
            return 640.0

        def release(self):
            return None

        def set(self, *_args):
            return True

    class GoodCap:
        def __init__(self):
            self.reads = 0

        def isOpened(self):
            return True

        def read(self):
            self.reads += 1
            return True, np.zeros((8, 8, 3), dtype=np.uint8)

        def get(self, _prop):
            return 640.0

        def release(self):
            return None

        def set(self, *_args):
            return True

    caps = [FailingCap(), GoodCap()]

    def open_side_effect(_source):
        return caps.pop(0) if caps else GoodCap()

    with (
        patch("stream_capture.open_capture", side_effect=open_side_effect),
        patch("stream_capture.time.sleep", return_value=None),
    ):
        capture = RobustCapture(
            "rtsp://127.0.0.1:8554/cam1",
            reconnect=True,
            fail_threshold=2,
            initial_delay=0.01,
            max_delay=0.05,
            open_retries=1,
        )
        ok, frame = capture.read()

    assert ok is True
    assert frame is not None
    assert capture.reconnect_count >= 1
    capture.release()


def test_open_retries_on_live_source():
    attempts = {"n": 0}

    def flaky_open(_source):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("temporary fail")
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.return_value = 640.0
        return cap

    with (
        patch("stream_capture.open_capture", side_effect=flaky_open),
        patch("stream_capture.time.sleep", return_value=None),
    ):
        capture = RobustCapture(
            "rtsp://127.0.0.1:8554/cam1",
            reconnect=True,
            open_retries=5,
            initial_delay=0.01,
            max_delay=0.05,
        )

    assert attempts["n"] == 3
    capture.release()
