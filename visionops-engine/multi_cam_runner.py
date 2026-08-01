"""Supervise one demo_roi worker process per active camera.

Polls the backend camera list and keeps subprocesses in sync:
- new/updated cameras → start or restart worker
- inactive/removed cameras → stop worker
- crashed workers → restart on next poll

Falls back to VIDEO_SOURCE + CAMERA_NAME when the API returns no cameras.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

import requests

from metrics_server import start_metrics_server

try:
    from prometheus_client import Gauge

    WORKERS_GAUGE = Gauge(
        "visionops_engine_workers",
        "Active per-camera inference workers supervised by multi_cam_runner",
    )
    WORKER_UP_GAUGE = Gauge(
        "visionops_engine_worker_up",
        "1 if the supervised worker process is alive",
        ["camera"],
    )
except Exception:  # noqa: BLE001
    WORKERS_GAUGE = None
    WORKER_UP_GAUGE = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("visionops-multi-cam")


@dataclass(frozen=True)
class CameraSpec:
    name: str
    source_url: str
    camera_id: str | None = None

    @property
    def key(self) -> str:
        return self.name


@dataclass
class WorkerState:
    spec: CameraSpec
    process: subprocess.Popen


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="VisionOps multi-camera engine supervisor")
    p.add_argument("--api-url", default=os.getenv("API_URL", "http://127.0.0.1:8001"))
    p.add_argument(
        "--api-key",
        default=os.getenv("VISIONOPS_API_KEY", ""),
        help="Service API key for listing cameras",
    )
    p.add_argument(
        "--poll-seconds",
        type=float,
        default=float(os.getenv("CAMERA_POLL_SECONDS", "15")),
    )
    p.add_argument(
        "--fallback-source",
        default=os.getenv("VIDEO_SOURCE", "rtsp://mediamtx:8554/cam1"),
        help="Used when the API has no active cameras",
    )
    p.add_argument(
        "--fallback-camera",
        default=os.getenv("CAMERA_NAME", "demo-camera"),
    )
    p.add_argument(
        "--stream-every",
        type=int,
        default=int(os.getenv("DETECTION_STREAM_EVERY", "1")),
    )
    p.add_argument(
        "--metrics-port",
        type=int,
        default=int(os.getenv("METRICS_PORT", "9101")),
    )
    p.add_argument(
        "--demo-script",
        default=os.path.join(os.path.dirname(__file__), "demo_roi.py"),
    )
    p.add_argument("--python", default=sys.executable)
    return p.parse_args()


def fetch_active_cameras(api_url: str, api_key: str, timeout: float = 5.0) -> list[CameraSpec]:
    headers = {"X-API-Key": api_key} if api_key else {}
    url = f"{api_url.rstrip('/')}/api/v1/cameras"
    resp = requests.get(url, params={"active_only": "true"}, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError("cameras endpoint did not return a list")
    out: list[CameraSpec] = []
    for row in data:
        name = str(row.get("name") or "").strip()
        source = str(row.get("source_url") or "").strip()
        if not name or not source:
            continue
        out.append(
            CameraSpec(
                name=name,
                source_url=source,
                camera_id=str(row["id"]) if row.get("id") else None,
            )
        )
    return out


def desired_cameras(
    api_cameras: list[CameraSpec] | None,
    *,
    fallback_source: str,
    fallback_camera: str,
) -> dict[str, CameraSpec]:
    """Build the target worker map. API list wins; otherwise a single fallback cam."""
    if api_cameras:
        return {cam.key: cam for cam in api_cameras}
    source = (fallback_source or "").strip()
    name = (fallback_camera or "demo-camera").strip() or "demo-camera"
    if not source:
        return {}
    return {name: CameraSpec(name=name, source_url=source)}


def plan_reconcile(
    desired: dict[str, CameraSpec],
    running: dict[str, CameraSpec],
) -> tuple[list[str], list[CameraSpec], list[CameraSpec]]:
    """Return (stop_keys, start_specs, restart_specs)."""
    stop_keys = [key for key in running if key not in desired]
    start_specs = [desired[key] for key in desired if key not in running]
    restart_specs = [
        desired[key]
        for key in desired
        if key in running and running[key].source_url != desired[key].source_url
    ]
    return stop_keys, start_specs, restart_specs


def build_worker_command(
    spec: CameraSpec,
    *,
    python: str,
    demo_script: str,
    api_url: str,
    api_key: str,
    stream_every: int,
) -> list[str]:
    cmd = [
        python,
        demo_script,
        "--skip-benchmark",
        "--max-frames",
        "0",
        "--stream-detections",
        "--post-alerts",
        "--sync-roi",
        "--stream-every",
        str(max(1, stream_every)),
        "--source",
        spec.source_url,
        "--camera-name",
        spec.name,
        "--api-url",
        api_url,
        "--metrics-port",
        "0",
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    return cmd


def _set_worker_metrics(running: dict[str, WorkerState]) -> None:
    if WORKERS_GAUGE is None or WORKER_UP_GAUGE is None:
        return
    try:
        WORKERS_GAUGE.set(len(running))
        for name, state in running.items():
            alive = state.process.poll() is None
            WORKER_UP_GAUGE.labels(camera=name).set(1.0 if alive else 0.0)
    except Exception:  # noqa: BLE001
        pass


class MultiCameraSupervisor:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.workers: dict[str, WorkerState] = {}
        self._stop = False

    def request_stop(self, *_args: Any) -> None:
        self._stop = True

    def start_worker(self, spec: CameraSpec) -> None:
        cmd = build_worker_command(
            spec,
            python=self.args.python,
            demo_script=self.args.demo_script,
            api_url=self.args.api_url,
            api_key=self.args.api_key,
            stream_every=self.args.stream_every,
        )
        logger.info("Starting worker camera=%s source=%s", spec.name, spec.source_url)
        env = os.environ.copy()
        env["METRICS_PORT"] = "0"
        proc = subprocess.Popen(cmd, cwd=os.path.dirname(self.args.demo_script) or ".", env=env)
        self.workers[spec.key] = WorkerState(spec=spec, process=proc)

    def stop_worker(self, key: str) -> None:
        state = self.workers.pop(key, None)
        if state is None:
            return
        logger.info("Stopping worker camera=%s pid=%s", key, state.process.pid)
        try:
            state.process.terminate()
            try:
                state.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                state.process.kill()
                state.process.wait(timeout=5)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed stopping worker %s: %s", key, exc)

    def stop_all(self) -> None:
        for key in list(self.workers):
            self.stop_worker(key)

    def _running_specs(self) -> dict[str, CameraSpec]:
        return {key: state.spec for key, state in self.workers.items()}

    def _restart_dead(self) -> None:
        for key, state in list(self.workers.items()):
            code = state.process.poll()
            if code is None:
                continue
            logger.warning(
                "Worker exited camera=%s code=%s — will restart",
                key,
                code,
            )
            self.workers.pop(key, None)
            self.start_worker(state.spec)

    def reconcile_once(self) -> None:
        try:
            api_cams = fetch_active_cameras(self.args.api_url, self.args.api_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Camera poll failed: %s — keeping current workers", exc)
            self._restart_dead()
            _set_worker_metrics(self.workers)
            return

        desired = desired_cameras(
            api_cams,
            fallback_source=self.args.fallback_source,
            fallback_camera=self.args.fallback_camera,
        )
        stop_keys, start_specs, restart_specs = plan_reconcile(desired, self._running_specs())

        for key in stop_keys:
            self.stop_worker(key)
        for spec in restart_specs:
            self.stop_worker(spec.key)
            self.start_worker(spec)
        for spec in start_specs:
            self.start_worker(spec)

        self._restart_dead()
        _set_worker_metrics(self.workers)
        logger.info(
            "Supervisor sync | desired=%d running=%d cameras=%s",
            len(desired),
            len(self.workers),
            ",".join(sorted(self.workers)) or "(none)",
        )

    def run(self) -> int:
        if self.args.metrics_port > 0:
            start_metrics_server(self.args.metrics_port)

        signal.signal(signal.SIGINT, self.request_stop)
        signal.signal(signal.SIGTERM, self.request_stop)

        logger.info(
            "Multi-cam supervisor started | api=%s poll=%.1fs fallback=%s@%s",
            self.args.api_url,
            self.args.poll_seconds,
            self.args.fallback_camera,
            self.args.fallback_source,
        )

        while not self._stop:
            self.reconcile_once()
            deadline = time.monotonic() + max(2.0, float(self.args.poll_seconds))
            while not self._stop and time.monotonic() < deadline:
                time.sleep(0.5)

        logger.info("Shutting down multi-cam supervisor")
        self.stop_all()
        return 0


def main() -> None:
    args = parse_args()
    raise SystemExit(MultiCameraSupervisor(args).run())


if __name__ == "__main__":
    main()
