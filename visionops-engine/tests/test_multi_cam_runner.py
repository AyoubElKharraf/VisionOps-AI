"""Unit tests for multi-camera supervisor planning helpers."""

from __future__ import annotations

from multi_cam_runner import (
    CameraSpec,
    build_worker_command,
    desired_cameras,
    plan_reconcile,
)


def test_desired_cameras_uses_api_list():
    cams = [
        CameraSpec(name="gate", source_url="rtsp://x/cam2"),
        CameraSpec(name="dock", source_url="rtsp://x/cam1"),
    ]
    desired = desired_cameras(
        cams,
        fallback_source="rtsp://fallback/cam1",
        fallback_camera="demo-camera",
    )
    assert set(desired) == {"gate", "dock"}
    assert desired["gate"].source_url.endswith("/cam2")


def test_desired_cameras_fallback_when_empty():
    desired = desired_cameras(
        [],
        fallback_source="rtsp://mediamtx:8554/cam1",
        fallback_camera="demo-camera",
    )
    assert list(desired) == ["demo-camera"]
    assert desired["demo-camera"].source_url == "rtsp://mediamtx:8554/cam1"


def test_desired_cameras_empty_without_fallback_source():
    assert desired_cameras([], fallback_source="", fallback_camera="demo") == {}


def test_plan_reconcile_start_stop_restart():
    desired = {
        "a": CameraSpec(name="a", source_url="rtsp://x/a"),
        "b": CameraSpec(name="b", source_url="rtsp://x/b2"),
    }
    running = {
        "b": CameraSpec(name="b", source_url="rtsp://x/b1"),
        "c": CameraSpec(name="c", source_url="rtsp://x/c"),
    }
    stop_keys, start_specs, restart_specs = plan_reconcile(desired, running)
    assert stop_keys == ["c"]
    assert [s.name for s in start_specs] == ["a"]
    assert [s.name for s in restart_specs] == ["b"]
    assert restart_specs[0].source_url.endswith("/b2")


def test_build_worker_command_includes_camera_and_disables_child_metrics():
    cmd = build_worker_command(
        CameraSpec(name="dock", source_url="rtsp://mediamtx:8554/cam1"),
        python="python",
        demo_script="demo_roi.py",
        api_url="http://backend:8001",
        api_key="secret",
        stream_every=2,
    )
    assert cmd[0] == "python"
    assert "demo_roi.py" in cmd
    assert cmd[cmd.index("--camera-name") + 1] == "dock"
    assert cmd[cmd.index("--source") + 1] == "rtsp://mediamtx:8554/cam1"
    assert cmd[cmd.index("--metrics-port") + 1] == "0"
    assert cmd[cmd.index("--api-key") + 1] == "secret"
