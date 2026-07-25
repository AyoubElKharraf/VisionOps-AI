"""
VisionOps AI — Phase 2 ROI / Tripwire demo with ONNX vs PyTorch benchmarks.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from export_onnx import export_onnx
from main import (
    DATA_DIR,
    ENGINE_DIR,
    create_writer,
    open_capture,
    resolve_source,
)
from alert_client import AlertClient
from onnx_engine import COCO_NAMES, ONNXInferenceEngine
from roi_manager import (
    CrossingDirection,
    Detection,
    ROIEngine,
    TripwireLine,
    ZoneROI,
    detections_from_array,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("visionops-demo-roi")


def draw_semi_transparent_polygon(
    frame: np.ndarray,
    points: list[tuple[int, int]],
    color: tuple[int, int, int],
    alpha: float = 0.35,
) -> None:
    if len(points) < 3:
        return
    overlay = frame.copy()
    pts = np.array(points, dtype=np.int32)
    cv2.fillPoly(overlay, [pts], color)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
    cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2, lineType=cv2.LINE_AA)


def draw_tripwire(frame: np.ndarray, start: tuple[float, float], end: tuple[float, float]) -> None:
    p1 = (int(start[0]), int(start[1]))
    p2 = (int(end[0]), int(end[1]))
    cv2.line(frame, p1, p2, (0, 220, 255), 3, cv2.LINE_AA)
    mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2 - 8)
    cv2.putText(frame, "TRIPWIRE", mid, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 2, cv2.LINE_AA)


def draw_boxes(frame: np.ndarray, detections: list[Detection]) -> None:
    for det in detections:
        x1, y1, x2, y2 = map(int, (det.x1, det.y1, det.x2, det.y2))
        color = (0, 200, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        tid = f"#{det.track_id} " if det.track_id is not None else ""
        label = f"{tid}{det.class_name} {det.confidence:.2f}"
        cv2.putText(frame, label, (x1, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        fx, fy = map(int, det.foot_point)
        cv2.circle(frame, (fx, fy), 4, (80, 255, 80), -1)


def pytorch_dets(model: YOLO, frame: np.ndarray, conf: float, device: str) -> tuple[np.ndarray, float]:
    kwargs = {"conf": conf, "verbose": False}
    if device:
        kwargs["device"] = device
    t0 = time.perf_counter()
    results = model.predict(frame, **kwargs)
    infer_ms = (time.perf_counter() - t0) * 1000.0
    boxes = results[0].boxes
    if boxes is None or len(boxes) == 0:
        return np.zeros((0, 6), dtype=np.float32), infer_ms
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()[:, None]
    clss = boxes.cls.cpu().numpy()[:, None]
    return np.concatenate([xyxy, confs, clss], axis=1).astype(np.float32), infer_ms


def build_default_roi(width: int, height: int) -> ROIEngine:
    """Virtual restricted zone (center) + horizontal counting line."""
    engine = ROIEngine(history_len=20)
    # Restricted zone ~ center rectangle (polygon)
    zx0, zy0 = int(width * 0.35), int(height * 0.25)
    zx1, zy1 = int(width * 0.70), int(height * 0.75)
    engine.add_zone(
        ZoneROI(
            name="zone_restreinte",
            points=[(zx0, zy0), (zx1, zy0), (zx1, zy1), (zx0, zy1)],
            max_allowed_objects=0,
            forbidden_classes=["person", "bicycle", "car"],
        )
    )
    # Tripwire across mid-frame
    y = int(height * 0.55)
    engine.add_tripwire(
        TripwireLine(
            name="ligne_comptage",
            start=(int(width * 0.05), y),
            end=(int(width * 0.95), y),
            direction=CrossingDirection.BOTH,
        )
    )
    return engine


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="VisionOps AI — Phase 2/3 ROI demo")
    p.add_argument("--source", type=str, default="")
    p.add_argument("--max-frames", type=int, default=90)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional annotated MP4 path (empty = no video write, faster)",
    )
    p.add_argument("--benchmark-frames", type=int, default=30, help="Frames used for PT vs ONNX FPS compare")
    p.add_argument("--skip-benchmark", action="store_true")
    p.add_argument("--show", action="store_true")
    p.add_argument(
        "--post-alerts",
        action="store_true",
        help="POST ROI/tripwire alerts to visionops-backend (Phase 3)",
    )
    p.add_argument(
        "--stream-detections",
        action="store_true",
        help="Push live bounding boxes to backend WebSocket hub (Phase 4 dashboard)",
    )
    p.add_argument(
        "--stream-every",
        type=int,
        default=2,
        help="Push detections every N frames (default 2 — lighter on network)",
    )
    p.add_argument(
        "--api-url",
        type=str,
        default="http://127.0.0.1:8001",
        help="Backend base URL (default port 8001 — avoids Windows :8000 conflicts)",
    )
    p.add_argument("--alert-cooldown", type=int, default=45, help="Min frames between identical API alerts")
    return p.parse_args()


def benchmark(
    source: str,
    onnx_engine: ONNXInferenceEngine,
    pt_model: YOLO,
    conf: float,
    device: str,
    n_frames: int,
) -> tuple[float, float, float, float]:
    """Return (pt_avg_ms, onnx_avg_ms, pt_fps, onnx_fps)."""
    cap = open_capture(source)
    pt_ms: list[float] = []
    onnx_ms: list[float] = []
    frames = 0
    while frames < n_frames:
        ok, frame = cap.read()
        if not ok:
            break
        _, ms_pt = pytorch_dets(pt_model, frame, conf, device)
        _, ms_onnx = onnx_engine.predict(frame)
        pt_ms.append(ms_pt)
        onnx_ms.append(ms_onnx)
        frames += 1
    cap.release()

    avg_pt = sum(pt_ms) / len(pt_ms) if pt_ms else 0.0
    avg_onnx = sum(onnx_ms) / len(onnx_ms) if onnx_ms else 0.0
    fps_pt = 1000.0 / avg_pt if avg_pt > 0 else 0.0
    fps_onnx = 1000.0 / avg_onnx if avg_onnx > 0 else 0.0
    return avg_pt, avg_onnx, fps_pt, fps_onnx


def run(args: argparse.Namespace) -> int:
    source = resolve_source(args.source)
    onnx_path = export_onnx(ENGINE_DIR / "yolov8n.pt", ENGINE_DIR / "yolov8n.onnx")
    onnx_engine = ONNXInferenceEngine(onnx_path, conf_thres=args.conf)

    # Only load heavy PyTorch weights when benchmarking (was slowing every run)
    if not args.skip_benchmark:
        pt_model = YOLO(str(ENGINE_DIR / "yolov8n.pt"))
        logger.info("Benchmarking PyTorch vs ONNX over %d frames…", args.benchmark_frames)
        avg_pt, avg_onnx, fps_pt, fps_onnx = benchmark(
            source, onnx_engine, pt_model, args.conf, args.device, args.benchmark_frames
        )
        speedup = avg_pt / avg_onnx if avg_onnx > 0 else 0.0
        logger.info("METRICS | PyTorch avg_infer=%.1fms (%.1f FPS)", avg_pt, fps_pt)
        logger.info("METRICS | ONNX     avg_infer=%.1fms (%.1f FPS)", avg_onnx, fps_onnx)
        logger.info("METRICS | Latency gain: %.2fx faster with ONNX", speedup)
        del pt_model

    capture = open_capture(source)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
    src_fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
    # Writing MP4 every frame is costly — off by default now
    writer = create_writer(args.output, src_fps, (width, height)) if args.output else None
    roi = build_default_roi(width, height)

    fps_window: deque[float] = deque(maxlen=30)
    frame_idx = 0
    intrusion_frames = 0
    crossing_total = 0
    posted_alerts = 0
    show = args.show
    alert_client = (
        AlertClient(args.api_url) if (args.post_alerts or args.stream_detections) else None
    )
    last_posted: dict[str, int] = {}
    stream_every = max(1, args.stream_every)

    logger.info(
        "Running ROI demo | source=%s | max_frames=%d | post_alerts=%s | stream=%s (every %d) | write_mp4=%s",
        source,
        args.max_frames,
        args.post_alerts,
        args.stream_detections,
        stream_every,
        bool(writer),
    )

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break

            dets_arr, infer_ms = onnx_engine.predict(frame)
            fps_window.append(1000.0 / infer_ms if infer_ms > 0 else 0.0)
            detections = detections_from_array(dets_arr, COCO_NAMES)
            detections = roi.assign_tracks(detections)

            alerts = roi.check_zone_intrusion(detections)
            crossings = roi.check_line_crossings(detections)

            if (
                alert_client is not None
                and args.stream_detections
                and frame_idx % stream_every == 0
            ):
                boxes_payload = [
                    {
                        "x1": d.x1,
                        "y1": d.y1,
                        "x2": d.x2,
                        "y2": d.y2,
                        "confidence": d.confidence,
                        "class_id": d.class_id,
                        "class_name": d.class_name,
                        "track_id": d.track_id,
                    }
                    for d in detections
                ]
                # Non-blocking; drops if previous HTTP still in flight
                alert_client.push_detections(
                    width=width,
                    height=height,
                    frame_index=frame_idx,
                    boxes=boxes_payload,
                    infer_ms=infer_ms,
                    zone_alerts=[a.message for a in alerts],
                )

            if alerts:
                intrusion_frames += 1
                for a in alerts:
                    logger.warning("%s | infer=%.1fms", a.message, infer_ms)
                    if alert_client is not None and args.post_alerts:
                        key = f"roi:{a.zone_name}"
                        if frame_idx - last_posted.get(key, -10_000) >= args.alert_cooldown:
                            alert_client.create_alert(
                                alert_type="roi_intrusion",
                                message=a.message,
                                camera_name="demo-camera",
                                zone_name=a.zone_name,
                                class_name=(a.offending_classes[0] if a.offending_classes else None),
                                source_video_path=source,
                                frame_index=frame_idx,
                                snapshot_frame=frame,
                                metadata={"object_count": a.object_count, "infer_ms": infer_ms},
                            )
                            posted_alerts += 1
                            last_posted[key] = frame_idx
            for c in crossings:
                crossing_total += 1
                logger.warning("%s | infer=%.1fms", c.message, infer_ms)
                if alert_client is not None and args.post_alerts:
                    key = f"tw:{c.line_name}:{c.track_id}:{c.direction}"
                    if frame_idx - last_posted.get(key, -10_000) >= args.alert_cooldown:
                        alert_client.create_alert(
                            alert_type="tripwire",
                            message=c.message,
                            camera_name="demo-camera",
                            zone_name=c.line_name,
                            class_name=c.class_name,
                            track_id=c.track_id,
                            source_video_path=source,
                            frame_index=frame_idx,
                            snapshot_frame=frame,
                            metadata={"direction": c.direction, "infer_ms": infer_ms},
                        )
                        posted_alerts += 1
                        last_posted[key] = frame_idx

            avg_fps = sum(fps_window) / len(fps_window) if fps_window else 0.0
            need_draw = writer is not None or show
            if need_draw:
                annotated = frame.copy()
                zone = roi.zones[0]
                zone_pts = [(int(x), int(y)) for x, y in zone.points]
                zone_color = (40, 40, 220) if alerts else (40, 200, 80)
                draw_semi_transparent_polygon(annotated, zone_pts, zone_color, alpha=0.35)
                label = "INTRUSION" if alerts else "ZONE OK"
                cv2.putText(
                    annotated,
                    f"{zone.name}: {label}",
                    (zone_pts[0][0], max(20, zone_pts[0][1] - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    zone_color,
                    2,
                    cv2.LINE_AA,
                )
                wire = roi.tripwires[0]
                draw_tripwire(annotated, wire.start, wire.end)
                draw_boxes(annotated, detections)
                hud = f"ONNX {avg_fps:.1f}FPS | infer {infer_ms:.1f}ms | cross={crossing_total}"
                cv2.putText(
                    annotated, hud, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 255, 120), 2, cv2.LINE_AA
                )
                if alerts:
                    cv2.putText(
                        annotated,
                        "ALERTE ROI : Intrusion detectee !",
                        (10, 58),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (40, 40, 255),
                        2,
                        cv2.LINE_AA,
                    )
                if writer is not None:
                    writer.write(annotated)
                if show:
                    try:
                        cv2.imshow("VisionOps AI — Phase 2 ROI", annotated)
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            break
                    except cv2.error:
                        show = False

            frame_idx += 1
            if frame_idx % 30 == 0:
                logger.info(
                    "frame=%d | onnx_infer=%.1fms | fps=%.1f | dets=%d | alerts=%d",
                    frame_idx,
                    infer_ms,
                    avg_fps,
                    len(detections),
                    len(alerts),
                )

            if args.max_frames > 0 and frame_idx >= args.max_frames:
                break
    finally:
        capture.release()
        if writer is not None:
            writer.release()
        if alert_client is not None:
            alert_client.close()
        if show:
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass

    logger.info(
        "Done. frames=%d | intrusion_frames=%d | crossings=%d | posted_alerts=%d | output=%s",
        frame_idx,
        intrusion_frames,
        crossing_total,
        posted_alerts,
        args.output or "(none)",
    )
    return 0 if frame_idx > 0 else 1


def main() -> None:
    args = parse_args()
    try:
        code = run(args)
    except Exception as exc:  # noqa: BLE001
        logger.exception("demo_roi failed: %s", exc)
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
