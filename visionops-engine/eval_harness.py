"""
VisionOps AI — offline detection + alert eval harness.

Detection mode reports mAP@0.5 and box-level false-alarm rate.
Alert mode compares ROI/loitering alerts per frame (GT vs predicted or simulated).

Dataset JSON schema (labels.json):
{
  "name": "site-a",
  "classes": ["person"],
  "zones": [
    {
      "name": "dock",
      "points": [[x,y], ...],
      "forbidden_classes": ["person"],
      "max_allowed_objects": 0,
      "loitering_seconds": 0
    }
  ],
  "images": [
    {
      "id": "frame_001",
      "file": "images/001.jpg",
      "width": 640,
      "height": 480,
      "boxes": [{"class_name": "person", "xyxy": [x1,y1,x2,y2], "track_id": 1}],
      "alerts": [
        {"alert_type": "roi_intrusion", "zone_name": "dock", "reason": "intrusion"}
      ]
    }
  ]
}

Predictions JSON may include boxes and/or alerts:
{
  "images": { "frame_001": [ {"class_name":"person","confidence":0.9,"xyxy":[...]} ] },
  "alerts":  { "frame_001": [ {"alert_type":"roi_intrusion","zone_name":"dock","reason":"intrusion"} ] }
}

Usage:
  python eval_harness.py --dataset eval/fixtures/mini/labels.json --predictions eval/fixtures/mini/preds.json
  python eval_harness.py --dataset eval/fixtures/alerts_mini/labels.json --predictions eval/fixtures/alerts_mini/preds.json --alerts predictions
  python eval_harness.py --dataset eval/fixtures/alerts_mini/labels.json --predictions eval/fixtures/alerts_mini/preds.json --alerts simulate
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from eval_metrics import (
    AlertEvalReport,
    AlertLabel,
    Box,
    EvalReport,
    evaluate_alerts,
    evaluate_dataset,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("visionops-eval")

ENGINE_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="VisionOps offline detection / alert eval")
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
    p.add_argument(
        "--alerts",
        choices=("auto", "off", "predictions", "simulate"),
        default="auto",
        help="Alert eval: auto|off|predictions|simulate via ROIEngine on boxes",
    )
    p.add_argument(
        "--alert-match-reason",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include alert reason in matching key (default: true)",
    )
    p.add_argument("--report", type=Path, default=None, help="Write JSON report here")
    p.add_argument("--max-images", type=int, default=0, help="0 = all images")
    return p.parse_args()


def load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "images" not in data or not isinstance(data["images"], list):
        raise ValueError("labels.json must contain an images[] array")
    return data


def _parse_box(raw: dict[str, Any], *, default_conf: float = 1.0) -> Box:
    track_raw = raw.get("track_id")
    track_id = int(track_raw) if track_raw is not None else None
    return Box(
        xyxy=tuple(float(v) for v in raw["xyxy"]),  # type: ignore[arg-type]
        class_name=str(raw["class_name"]),
        confidence=float(raw.get("confidence", default_conf)),
        track_id=track_id,
    )


def _parse_alert(raw: dict[str, Any]) -> AlertLabel:
    return AlertLabel(
        alert_type=str(raw.get("alert_type") or raw.get("type") or "roi_intrusion"),
        zone_name=str(raw.get("zone_name") or raw.get("zone") or ""),
        reason=str(raw.get("reason") or ""),
    )


def load_predictions(path: Path) -> tuple[dict[str, list[Box]], dict[str, list[AlertLabel]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    images = raw.get("images") or {}
    boxes_out: dict[str, list[Box]] = {}
    for image_id, boxes in images.items():
        boxes_out[str(image_id)] = [_parse_box(b) for b in boxes]

    alerts_raw = raw.get("alerts") or {}
    alerts_out: dict[str, list[AlertLabel]] = {
        str(image_id): [_parse_alert(a) for a in alerts]
        for image_id, alerts in alerts_raw.items()
    }
    return boxes_out, alerts_out


def gt_boxes_from_image(item: dict[str, Any], allowed: set[str] | None) -> list[Box]:
    boxes: list[Box] = []
    for b in item.get("boxes") or []:
        box = _parse_box(b, default_conf=1.0)
        if allowed is not None and box.class_name not in allowed:
            continue
        boxes.append(box)
    return boxes


def gt_alerts_from_image(item: dict[str, Any]) -> list[AlertLabel]:
    return [_parse_alert(a) for a in (item.get("alerts") or [])]


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
    for idx, row in enumerate(dets):
        x1, y1, x2, y2, conf, cls_id = row.tolist()
        name = _class_name(engine.names, int(cls_id))
        if allowed is not None and name not in allowed:
            continue
        out.append(
            Box(
                xyxy=(x1, y1, x2, y2),
                class_name=name,
                confidence=float(conf),
                track_id=idx + 1,
            )
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
    for i, (box, c, cls_id) in enumerate(zip(xyxy, confs, clss, strict=True)):
        name = _class_name(names, int(cls_id))
        if allowed is not None and name not in allowed:
            continue
        out.append(
            Box(
                xyxy=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                class_name=name,
                confidence=float(c),
                track_id=i + 1,
            )
        )
    return out


def resolve_image_path(dataset_path: Path, rel: str) -> Path:
    root = dataset_path.parent
    candidate = root / rel
    if candidate.exists():
        return candidate
    abs_path = Path(rel)
    if abs_path.exists():
        return abs_path
    raise FileNotFoundError(f"Image not found: {rel} (looked under {root})")


def _scale_zone_points(
    points: list[list[float]] | list[tuple[float, float]],
    width: float,
    height: float,
) -> list[tuple[float, float]]:
    vals = [(float(p[0]), float(p[1])) for p in points]
    if vals and max(max(abs(x), abs(y)) for x, y in vals) <= 1.5:
        return [(x * width, y * height) for x, y in vals]
    return vals


def build_roi_engine(zones_raw: list[dict[str, Any]], *, width: float, height: float):
    from roi_manager import ROIEngine, ZoneROI

    engine = ROIEngine()
    for item in zones_raw:
        if "forbidden_classes" in item:
            forbidden = list(item.get("forbidden_classes") or [])
        else:
            forbidden = ["person"]
        zone = ZoneROI(
            name=str(item["name"]),
            points=_scale_zone_points(item.get("points") or [], width, height),
            max_allowed_objects=int(item.get("max_allowed_objects", 0) or 0),
            forbidden_classes=forbidden,
            loitering_seconds=int(item.get("loitering_seconds", 0) or 0),
            schedule_enabled=bool(item.get("schedule_enabled", False)),
            schedule_start=str(item.get("schedule_start", "00:00")),
            schedule_end=str(item.get("schedule_end", "23:59")),
            schedule_days=list(item.get("schedule_days") or [0, 1, 2, 3, 4, 5, 6]),
            schedule_timezone=str(item.get("schedule_timezone", "UTC")),
            require_hardhat=bool(item.get("require_hardhat", False)),
        )
        engine.add_zone(zone)
    return engine


def boxes_to_detections(boxes: Sequence[Box], *, class_id: int = 0):
    from roi_manager import Detection

    dets = []
    for i, box in enumerate(boxes):
        tid = box.track_id if box.track_id is not None else i + 1
        dets.append(
            Detection(
                track_id=tid,
                x1=box.x1,
                y1=box.y1,
                x2=box.x2,
                y2=box.y2,
                confidence=box.confidence,
                class_id=class_id,
                class_name=box.class_name,
            )
        )
    return dets


def simulate_alerts(
    zones_raw: list[dict[str, Any]],
    boxes: list[Box],
    *,
    width: float,
    height: float,
    now: float,
) -> list[AlertLabel]:
    if not zones_raw:
        return []
    engine = build_roi_engine(zones_raw, width=width, height=height)
    dets = boxes_to_detections(boxes)
    out: list[AlertLabel] = []
    for alert in engine.check_zone_intrusion(dets):
        out.append(
            AlertLabel(
                alert_type="roi_intrusion",
                zone_name=alert.zone_name,
                reason=alert.reason or "intrusion",
            )
        )
    for event in engine.check_loitering(dets, now=now):
        out.append(
            AlertLabel(
                alert_type="loitering",
                zone_name=event.zone_name,
                reason="loitering",
            )
        )
    return out


def resolve_alert_mode(
    mode: str,
    *,
    dataset: dict[str, Any],
    pred_alerts: dict[str, list[AlertLabel]] | None,
) -> str:
    if mode != "auto":
        return mode
    has_gt_alerts = any(bool(img.get("alerts")) for img in dataset.get("images") or [])
    has_zones = bool(dataset.get("zones"))
    has_pred_alerts = bool(pred_alerts)
    if not has_gt_alerts and not has_zones:
        return "off"
    if has_pred_alerts:
        return "predictions"
    if has_zones:
        return "simulate"
    return "off"


def run_eval(args: argparse.Namespace) -> tuple[EvalReport, AlertEvalReport | None, str]:
    dataset = load_dataset(args.dataset)
    class_filter = [c.strip() for c in args.classes.split(",") if c.strip()]
    allowed: set[str] | None = set(class_filter) if class_filter else None
    if allowed is None and dataset.get("classes"):
        allowed = {str(c) for c in dataset["classes"]}

    images_meta = list(dataset["images"])
    if args.max_images and args.max_images > 0:
        images_meta = images_meta[: args.max_images]

    precomputed: dict[str, list[Box]] | None = None
    pred_alerts: dict[str, list[AlertLabel]] | None = None
    if args.predictions:
        precomputed, pred_alerts = load_predictions(args.predictions)
        logger.info(
            "Loaded predictions for %d images (%d with alert labels)",
            len(precomputed),
            len(pred_alerts or {}),
        )

    alert_mode = resolve_alert_mode(
        args.alerts, dataset=dataset, pred_alerts=pred_alerts
    )
    logger.info("Alert eval mode: %s", alert_mode)

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
    alert_pairs: list[tuple[list[AlertLabel], list[AlertLabel]]] = []
    zones_raw = list(dataset.get("zones") or [])
    t0 = time.perf_counter()
    for frame_i, item in enumerate(images_meta):
        image_id = str(item.get("id") or item.get("file"))
        width = float(item.get("width") or 0) or 1.0
        height = float(item.get("height") or 0) or 1.0
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
            height, width = frame.shape[:2]
            if pt_model is not None:
                preds = run_ultralytics(
                    frame, model=pt_model, conf=args.conf, allowed=allowed
                )
            else:
                preds = run_onnx(frame, engine=onnx_engine, allowed=allowed)
        pairs.append((gts, preds))

        if alert_mode != "off":
            gt_alerts = gt_alerts_from_image(item)
            if alert_mode == "predictions":
                pred_a = list((pred_alerts or {}).get(image_id, []))
            else:
                pred_a = simulate_alerts(
                    zones_raw,
                    preds,
                    width=width,
                    height=height,
                    now=float(frame_i),
                )
            alert_pairs.append((gt_alerts, pred_a))

    elapsed = time.perf_counter() - t0
    class_list = sorted(allowed) if allowed else None
    report = evaluate_dataset(pairs, classes=class_list, iou_threshold=args.iou)
    logger.info(
        "Detection eval | images=%d | mAP@%.2f=%.4f | FAR=%.4f | FP/img=%.3f | %.1fms/img",
        report.num_images,
        args.iou,
        report.map50,
        report.false_alarm_rate,
        report.false_alarms_per_image,
        (elapsed * 1000.0 / max(1, report.num_images)),
    )

    alert_report: AlertEvalReport | None = None
    if alert_mode != "off":
        alert_report = evaluate_alerts(
            alert_pairs, match_reason=bool(args.alert_match_reason)
        )
        logger.info(
            "Alert eval | TP=%d FP=%d FN=%d | FAR=%.4f | precision=%.4f recall=%.4f",
            alert_report.total_tp,
            alert_report.total_fp,
            alert_report.total_fn,
            alert_report.false_alarm_rate,
            alert_report.micro_precision,
            alert_report.micro_recall,
        )
    return report, alert_report, alert_mode


def main() -> int:
    args = parse_args()
    try:
        report, alert_report, alert_mode = run_eval(args)
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
    payload["alert_mode"] = alert_mode
    if alert_report is not None:
        payload["alerts"] = alert_report.to_dict()

    text = json.dumps(payload, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
        logger.info("Wrote report %s", args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
