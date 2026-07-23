"""
VisionOps AI — Export YOLOv8 PyTorch weights to ONNX (Phase 2).

Usage:
  python export_onnx.py
  python export_onnx.py --model yolov8n.pt --imgsz 640
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ultralytics import YOLO

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("visionops-export-onnx")

ENGINE_DIR = Path(__file__).resolve().parent
DEFAULT_PT = ENGINE_DIR / "yolov8n.pt"
DEFAULT_ONNX = ENGINE_DIR / "yolov8n.onnx"


def export_onnx(
    model_path: Path,
    output_path: Path | None = None,
    imgsz: int = 640,
    force: bool = False,
) -> Path:
    """Export Ultralytics YOLO `.pt` to ONNX. Skip if target already exists."""
    if not model_path.exists():
        logger.info("Weights not found locally — Ultralytics will download: %s", model_path.name)
        model = YOLO(str(model_path.name))
    else:
        model = YOLO(str(model_path))

    target = output_path or model_path.with_suffix(".onnx")
    if target.exists() and not force:
        logger.info("ONNX already present, skipping export: %s", target)
        return target

    logger.info("Exporting %s → ONNX (imgsz=%d)…", model_path.name, imgsz)
    exported = model.export(format="onnx", imgsz=imgsz, simplify=True, opset=12)
    exported_path = Path(str(exported))

    if exported_path.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        exported_path.replace(target)
        logger.info("Moved export to %s", target)
    else:
        logger.info("ONNX ready: %s (%.1f MB)", target, target.stat().st_size / 1e6)

    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export YOLOv8 to ONNX")
    parser.add_argument("--model", type=str, default=str(DEFAULT_PT), help="Path to .pt weights")
    parser.add_argument("--output", type=str, default=str(DEFAULT_ONNX), help="Output .onnx path")
    parser.add_argument("--imgsz", type=int, default=640, help="Export input size")
    parser.add_argument("--force", action="store_true", help="Re-export even if ONNX exists")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        path = export_onnx(
            model_path=Path(args.model),
            output_path=Path(args.output),
            imgsz=args.imgsz,
            force=args.force,
        )
        logger.info("Done: %s", path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Export failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
