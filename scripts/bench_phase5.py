"""
VisionOps AI — Phase 5 performance bench (ONNX inference FPS).

Usage:
  python scripts/bench_phase5.py
  python scripts/bench_phase5.py --frames 60
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "visionops-engine"
sys.path.insert(0, str(ENGINE))

import cv2  # noqa: E402
from export_onnx import export_onnx  # noqa: E402
from main import ensure_demo_video  # noqa: E402
from onnx_engine import ONNXInferenceEngine  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 5 ONNX performance bench")
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--warmup", type=int, default=5)
    args = parser.parse_args()

    from export_onnx import DEFAULT_IMGSZ, DEFAULT_ONNX

    video = ensure_demo_video()
    onnx_path = export_onnx(
        ENGINE / "yolov8n.pt",
        DEFAULT_ONNX,
        imgsz=DEFAULT_IMGSZ,
    )
    engine = ONNXInferenceEngine(onnx_path, conf_thres=0.25)
    print(f"model={onnx_path.name} imgsz={engine.imgsz}")

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        print("ERROR: cannot open demo video")
        return 1

    times: list[float] = []
    frames = 0
    while frames < args.warmup + args.frames:
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        _, ms = engine.predict(frame)
        if frames >= args.warmup:
            times.append(ms)
        frames += 1
    cap.release()

    avg = statistics.mean(times)
    p50 = statistics.median(times)
    p95 = sorted(times)[int(0.95 * (len(times) - 1))]
    fps = 1000.0 / avg if avg > 0 else 0.0

    print("=== VisionOps Phase 5 — ONNX Bench ===")
    print(f"frames={len(times)} warmup={args.warmup}")
    print(f"avg_infer_ms={avg:.2f}")
    print(f"p50_ms={p50:.2f}")
    print(f"p95_ms={p95:.2f}")
    print(f"fps={fps:.2f}")
    print("PASS" if avg < 200 else "WARN: avg inference > 200ms on this host")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
