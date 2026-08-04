"""
VisionOps AI — Inference engine (Phase 1 + Phase 2 ONNX).

Loads YOLOv8n (PyTorch or ONNX Runtime), ingests RTSP/MP4, draws boxes, reports FPS.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import requests
from ultralytics import YOLO

from stream_capture import RobustCapture, parse_reconnect_args

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("visionops-engine")

ENGINE_DIR = Path(__file__).resolve().parent
DATA_DIR = ENGINE_DIR / "data"
DEMO_VIDEO_NAME = "demo.mp4"
DEMO_VIDEO_URL = (
    "https://github.com/intel-iot-devkit/sample-videos/raw/master/person-bicycle-car-detection.mp4"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VisionOps AI — YOLO inference")
    parser.add_argument(
        "--source",
        type=str,
        default=os.getenv("VIDEO_SOURCE", ""),
        help="RTSP URL or path to a video file. Empty = download demo MP4.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("YOLO_MODEL", "yolov8n.pt"),
        help="Ultralytics YOLO model weights (default: yolov8n.pt)",
    )
    parser.add_argument(
        "--onnx-model",
        type=str,
        default=os.getenv("ONNX_MODEL", str(ENGINE_DIR / "yolov8n_416.onnx")),
        help="Path to ONNX model (used with --use-onnx). Default: yolov8n_416.onnx",
    )
    parser.add_argument(
        "--use-onnx",
        action="store_true",
        default=os.getenv("USE_ONNX", "").lower() in {"1", "true", "yes"},
        help="Run inference with ONNX Runtime instead of PyTorch",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=float(os.getenv("YOLO_CONF", "0.25")),
        help="Confidence threshold",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.getenv("VIDEO_OUTPUT", ""),
        help="Optional path to write annotated MP4",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=int(os.getenv("MAX_FRAMES", "0")),
        help="Stop after N frames (0 = entire stream/file)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show OpenCV window (ignored on headless hosts)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=os.getenv("YOLO_DEVICE", ""),
        help="Inference device for PyTorch (e.g. cpu, 0).",
    )
    parser.add_argument(
        "--rtsp-reconnect",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("RTSP_RECONNECT", "true").lower() in {"1", "true", "yes", "on"},
        help="Reconnect automatically when a live RTSP/HTTP stream drops",
    )
    parser.add_argument(
        "--rtsp-reconnect-initial",
        type=float,
        default=float(os.getenv("RTSP_RECONNECT_INITIAL", "1.0")),
    )
    parser.add_argument(
        "--rtsp-reconnect-max",
        type=float,
        default=float(os.getenv("RTSP_RECONNECT_MAX", "30.0")),
    )
    parser.add_argument(
        "--rtsp-fail-threshold",
        type=int,
        default=int(os.getenv("RTSP_FAIL_THRESHOLD", "2")),
    )
    parser.add_argument(
        "--rtsp-open-retries",
        type=int,
        default=int(os.getenv("RTSP_OPEN_RETRIES", "8")),
    )
    return parser.parse_args()


def ensure_demo_video() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    demo_path = DATA_DIR / DEMO_VIDEO_NAME
    if demo_path.exists() and demo_path.stat().st_size > 0:
        logger.info("Using cached demo video: %s", demo_path)
        return demo_path

    logger.info("Downloading demo video from %s", DEMO_VIDEO_URL)
    response = requests.get(DEMO_VIDEO_URL, stream=True, timeout=120)
    response.raise_for_status()
    with open(demo_path, "wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if chunk:
                handle.write(chunk)
    logger.info("Demo video saved to %s (%.1f MB)", demo_path, demo_path.stat().st_size / 1e6)
    return demo_path


def resolve_source(source: str) -> str:
    if source and source.strip():
        return source.strip()
    return str(ensure_demo_video())


def create_writer(
    output_path: str,
    fps: float,
    frame_size: tuple[int, int],
) -> cv2.VideoWriter | None:
    if not output_path:
        return None
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out), fourcc, max(fps, 1.0), frame_size)
    if not writer.isOpened():
        raise RuntimeError(f"Unable to open video writer: {output_path}")
    logger.info("Writing annotated video to %s", out)
    return writer


def draw_detections_array(
    frame: np.ndarray,
    dets: np.ndarray,
    names: dict[int, str] | None = None,
) -> int:
    """Draw Nx6 detections [x1,y1,x2,y2,conf,cls] on frame."""
    count = 0
    if dets is None or len(dets) == 0:
        return 0
    for row in dets:
        x1, y1, x2, y2 = map(int, row[:4])
        conf = float(row[4])
        cls_id = int(row[5])
        label = (names or {}).get(cls_id, str(cls_id))
        color = (0, 200, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        text = f"{label} {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, max(0, y1 - th - 6)), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            frame,
            text,
            (x1 + 2, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
        count += 1
    return count


def draw_detections(frame: np.ndarray, result) -> int:
    """Draw Ultralytics result boxes on frame; return detection count."""
    if result.boxes is None:
        return 0
    names = result.names or {}
    xyxy = result.boxes.xyxy.cpu().numpy()
    confs = result.boxes.conf.cpu().numpy()
    clss = result.boxes.cls.cpu().numpy()
    dets = np.concatenate([xyxy, confs[:, None], clss[:, None]], axis=1)
    return draw_detections_array(frame, dets, names)


def load_onnx_engine(onnx_path: str, conf: float):
    from export_onnx import DEFAULT_IMGSZ, export_onnx
    from onnx_engine import ONNXInferenceEngine

    path = Path(onnx_path)
    if not path.exists():
        pt = ENGINE_DIR / "yolov8n.pt"
        # Infer imgsz from filename …_416.onnx / …_640.onnx, else default 416
        imgsz = DEFAULT_IMGSZ
        for candidate in (416, 640, 320, 512):
            if f"_{candidate}" in path.stem:
                imgsz = candidate
                break
        logger.info("ONNX missing — exporting from %s (imgsz=%d)", pt, imgsz)
        path = export_onnx(pt, path, imgsz=imgsz)
    return ONNXInferenceEngine(path, conf_thres=conf)


def run(args: argparse.Namespace) -> int:
    source = resolve_source(args.source)
    backend = "ONNX" if args.use_onnx else "PyTorch"
    logger.info("Source: %s | backend=%s | conf=%.2f", source, backend, args.conf)

    onnx_engine = None
    pt_model = None
    names: dict[int, str] = {}

    if args.use_onnx:
        onnx_engine = load_onnx_engine(args.onnx_model, args.conf)
        names = onnx_engine.names
    else:
        logger.info("Model: %s", args.model)
        pt_model = YOLO(args.model)

    capture = RobustCapture(source, **parse_reconnect_args(args))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
    src_fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
    writer = create_writer(args.output, src_fps, (width, height))

    predict_kwargs: dict = {"conf": args.conf, "verbose": False}
    if args.device and pt_model is not None:
        predict_kwargs["device"] = args.device

    frame_idx = 0
    total_detections = 0
    fps_window: deque[float] = deque(maxlen=30)
    show = args.show
    t0 = time.perf_counter()

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                logger.info("End of stream / failed read at frame %d", frame_idx)
                break

            annotated = frame.copy()
            if onnx_engine is not None:
                dets, infer_ms = onnx_engine.predict(frame)
                det_count = draw_detections_array(annotated, dets, names)
            else:
                t_infer = time.perf_counter()
                results = pt_model.predict(frame, **predict_kwargs)
                infer_ms = (time.perf_counter() - t_infer) * 1000.0
                det_count = draw_detections(annotated, results[0])

            fps_window.append(1000.0 / infer_ms if infer_ms > 0 else 0.0)
            total_detections += det_count

            avg_fps = sum(fps_window) / len(fps_window) if fps_window else 0.0
            overlay = f"{backend} FPS:{avg_fps:.1f}  infer:{infer_ms:.1f}ms  det:{det_count}"
            cv2.putText(
                annotated,
                overlay,
                (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (40, 255, 120),
                2,
                cv2.LINE_AA,
            )

            if writer is not None:
                writer.write(annotated)

            if show:
                try:
                    cv2.imshow("VisionOps AI", annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        logger.info("Quit requested via OpenCV window")
                        break
                except cv2.error:
                    logger.warning("Display unavailable (headless); continuing without --show")
                    show = False

            frame_idx += 1
            if frame_idx % 30 == 0:
                logger.info(
                    "frame=%d | backend=%s | avg_fps=%.1f | infer=%.1fms | dets=%d",
                    frame_idx,
                    backend,
                    avg_fps,
                    infer_ms,
                    det_count,
                )

            if args.max_frames > 0 and frame_idx >= args.max_frames:
                logger.info("Reached --max-frames=%d", args.max_frames)
                break
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        capture.release()
        if writer is not None:
            writer.release()
        if show:
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass

    elapsed = time.perf_counter() - t0
    overall_fps = frame_idx / elapsed if elapsed > 0 else 0.0
    logger.info(
        "Done. backend=%s | frames=%d | detections=%d | elapsed=%.1fs | overall_fps=%.1f",
        backend,
        frame_idx,
        total_detections,
        elapsed,
        overall_fps,
    )
    return 0 if frame_idx > 0 else 1


def main() -> None:
    args = parse_args()
    try:
        code = run(args)
    except Exception as exc:  # noqa: BLE001 — top-level CLI boundary
        logger.exception("Engine failed: %s", exc)
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
