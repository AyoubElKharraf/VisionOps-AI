"""
VisionOps AI — offline detection eval harness.

Runs a detector (ONNX or Ultralytics) against a labeled dataset JSON, or scores
precomputed predictions, and writes a report with mAP@0.5 + false-alarm rate.

Dataset JSON schema (labels.json):
{
  "name": "site-a",
  "classes": ["person"],
  "images": [
    {
      "id": "frame_001",
      "file": "images/001.jpg",
      "width": 640,
      "height": 480,
      "boxes": [{"class_name": "person", "xyxy": [x1, y1, x2, y2]}]
    }
  ]
}

Predictions JSON (optional --predictions):
{
  "images": {
    "frame_001": [
      {"class_name": "person", "confidence": 0.91, "xyxy": [x1,y1,x2,y2]}
    ]
  }
}

Usage:
  python eval_harness.py --dataset eval/fixtures/mini/labels.json --predictions eval/fixtures/mini/preds.json
  python eval_harness.py --dataset path/to/labels.json --onnx yolov8n_416.onnx --report out/report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from eval_metrics import Box, EvalReport, evaluate_dataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("visionops-eval")

ENGINE_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="VisionOps offline detection eval")
    p.add_argument("--dataset", type=Path, required=True, help="Path to labels.json")
    p.add_argument(
        "--predictions",
        type=Path,
        default=None,
        help="Optional precomputed predictions JSON (skip inference)",
    )
    p.add_argument(
        "--onnx",
        type=str,
        default=os.getenv("ONNX_MODEL", str(ENGINE_DIR / "yolov8n_416.onnx")),
        help="ONNX model path (when not using --predictions)",
    )
    p.add_argument(
        "--pt-model",
        type=str,
        default=os.getenv("YOLO_MODEL", ""),
        help="Ultralytics .pt model (takes precedence over --onnx when set)",
    )
    p.add_argument("--conf", type=float, default=float(os.getenv("YOLO_CONF", "0.25")))
    p.add_argument("--iou", type=float, default=0.5, help="IoU threshold for matching / mAP")
    p.add_argument(
        "--classes",
        type=str,
        default="person",
        help="Comma-separated class filter (empty = all GT classes)",
    )
    p.add_argument("--report", type=Path, default=None, help="Write JSON report here")
    p.add_argument("--max-images", type=int, default=0, help="0 = all images")
    return p.parse_args()


def load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "images" not in data or not isinstance(data["images"], list):
        raise ValueError("labels.json must contain an images[] array")
    return data


def load_predictions(path: Path) -> dict[str, list[Box]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    images = raw.get("images") or {}
    out: dict[str, list[Box]] = {}
    for image_id, boxes in images.items():
        out[str(image_id)] = [
            Box(
                xyxy=tuple(float(v) for v in b["xyxy"]),  # type: ignore[arg-type]
                class_name=str(b["class_name"]),
                confidence=float(b.get("confidence", 1.0)),
            )
            for b in boxes
        ]
    return out


def gt_boxes_from_image(item: dict[str, Any], allowed: set[str] | None) -> list[Box]:
    boxes: list[Box] = []
    for b in item.get("boxes") or []:
        name = str(b["class_name"])
        if allowed is not None and name not in allowed:
            continue
        boxes.append(
            Box(
                xyxy=tuple(float(v) for v in b["xyxy"]),  # type: ignore[arg-type]
                class_name=name,
                confidence=1.0,
            )
        )
    return boxes


def _class_name(names: dict[int, str] | list[str], class_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(int(class_id), str(class_id)))
    if 0 <= int(class_id) < len(names):
        return str(names[int(class_id)])
    return str(class_id)


def run_onnx(
    image_bgr: np.ndarray,
    *,
    engine: Any,
    allowed: set[str] | None,
) -> list[Box]:
    dets, _ms = engine.predict(image_bgr)
    out: list[Box] = []
    for row in dets:
        x1, y1, x2, y2, conf, cls_id = row.tolist()
        name = _class_name(engine.names, int(cls_id))
        if allowed is not None and name not in allowed:
            continue
        out.append(
            Box(xyxy=(x1, y1, x2, y2), class_name=name, confidence=float(conf))
        )
    return out


def run_ultralytics(
    image_bgr: np.ndarray,
    *,
    model: Any,
    conf: float,
    allowed: set[str] | None,
) -> list[Box]:
    results = model.predict(image_bgr, conf=conf, verbose=False)
    out: list[Box] = []
    if not results:
        return out
    r0 = results[0]
    names = r0.names if hasattr(r0, "names") else model.names
    if r0.boxes is None or len(r0.boxes) == 0:
        return out
    xyxy = r0.boxes.xyxy.cpu().numpy()
    confs = r0.boxes.conf.cpu().numpy()
    clss = r0.boxes.cls.cpu().numpy().astype(int)
    for box, c, cls_id in zip(xyxy, confs, clss, strict=True):
        name = _class_name(names, int(cls_id))
        if allowed is not None and name not in allowed:
            continue
        out.append(
            Box(
                xyxy=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                class_name=name,
                confidence=float(c),
            )
        )
    return out


def resolve_image_path(dataset_path: Path, rel: str) -> Path:
    root = dataset_path.parent
    candidate = root / rel
    if candidate.exists():
        return candidate
    # Also allow absolute paths embedded in JSON
    abs_path = Path(rel)
    if abs_path.exists():
        return abs_path
    raise FileNotFoundError(f"Image not found: {rel} (looked under {root})")


def run_eval(args: argparse.Namespace) -> EvalReport:
    dataset = load_dataset(args.dataset)
    class_filter = [c.strip() for c in args.classes.split(",") if c.strip()]
    allowed: set[str] | None = set(class_filter) if class_filter else None
    if allowed is None and dataset.get("classes"):
        allowed = {str(c) for c in dataset["classes"]}

    images_meta = list(dataset["images"])
    if args.max_images and args.max_images > 0:
        images_meta = images_meta[: args.max_images]

    precomputed: dict[str, list[Box]] | None = None
    if args.predictions:
        precomputed = load_predictions(args.predictions)
        logger.info("Loaded predictions for %d images", len(precomputed))

    onnx_engine = None
    pt_model = None
    if precomputed is None:
        if args.pt_model:
            from ultralytics import YOLO

            logger.info("Loading Ultralytics model %s", args.pt_model)
            pt_model = YOLO(args.pt_model)
        else:
            from onnx_engine import ONNXInferenceEngine

            onnx_path = Path(args.onnx)
            if not onnx_path.exists():
                raise FileNotFoundError(
                    f"ONNX model not found: {onnx_path}. Pass --predictions or --pt-model."
                )
            logger.info("Loading ONNX model %s", onnx_path)
            onnx_engine = ONNXInferenceEngine(onnx_path, conf_thres=args.conf)

    pairs: list[tuple[list[Box], list[Box]]] = []
    t0 = time.perf_counter()
    for item in images_meta:
        image_id = str(item.get("id") or item.get("file"))
        gts = gt_boxes_from_image(item, allowed)
        if precomputed is not None:
            preds = list(precomputed.get(image_id, []))
            if allowed is not None:
                preds = [b for b in preds if b.class_name in allowed]
        else:
            img_path = resolve_image_path(args.dataset, str(item["file"]))
            frame = cv2.imread(str(img_path))
            if frame is None:
                raise RuntimeError(f"Failed to read image: {img_path}")
            if pt_model is not None:
                preds = run_ultralytics(
                    frame, model=pt_model, conf=args.conf, allowed=allowed
                )
            else:
                preds = run_onnx(frame, engine=onnx_engine, allowed=allowed)
        pairs.append((gts, preds))

    elapsed = time.perf_counter() - t0
    class_list = sorted(allowed) if allowed else None
    report = evaluate_dataset(pairs, classes=class_list, iou_threshold=args.iou)
    logger.info(
        "Eval done | images=%d | mAP@%.2f=%.4f | FAR=%.4f | FP/img=%.3f | %.1fms/img",
        report.num_images,
        args.iou,
        report.map50,
        report.false_alarm_rate,
        report.false_alarms_per_image,
        (elapsed * 1000.0 / max(1, report.num_images)),
    )
    return report


def main() -> int:
    args = parse_args()
    try:
        report = run_eval(args)
    except Exception as exc:  # noqa: BLE001
        logger.error("%s", exc)
        return 1

    payload = report.to_dict()
    payload["dataset"] = str(args.dataset)
    if args.predictions:
        payload["predictions"] = str(args.predictions)
    else:
        payload["model"] = args.pt_model or args.onnx
    payload["conf_threshold"] = args.conf

    text = json.dumps(payload, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
        logger.info("Wrote report %s", args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
