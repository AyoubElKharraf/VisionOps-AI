#!/bin/sh
set -e

WEIGHTS_DIR="${WEIGHTS_DIR:-/models}"
mkdir -p "$WEIGHTS_DIR"

python - <<'PY'
from pathlib import Path
import os
import shutil

from export_onnx import DEFAULT_IMGSZ, export_onnx
from ultralytics import YOLO

weights = Path(os.environ.get("WEIGHTS_DIR", "/models"))
weights.mkdir(parents=True, exist_ok=True)
pt = weights / "yolov8n.pt"
onnx = weights / "yolov8n_416.onnx"

if not pt.exists():
    YOLO("yolov8n.pt")  # downloads into CWD / Ultralytics cache
    for candidate in (
        Path("yolov8n.pt"),
        Path("/root/.cache/ultralytics/yolov8n.pt"),
    ):
        if candidate.exists():
            shutil.copy2(candidate, pt)
            break

export_onnx(pt if pt.exists() else Path("yolov8n.pt"), onnx, imgsz=DEFAULT_IMGSZ)
print(f"Weights ready under {weights}")
PY

ln -sfn "$WEIGHTS_DIR/yolov8n.pt" /app/yolov8n.pt
ln -sfn "$WEIGHTS_DIR/yolov8n_416.onnx" /app/yolov8n_416.onnx

# Optional: overwrite YOLO_MODEL / ONNX_MODEL / VISIONOPS_PPE_MODEL from the API registry.
if [ "${MODEL_REGISTRY_SYNC:-0}" = "1" ] || [ "${MODEL_REGISTRY_SYNC:-}" = "true" ] || [ "${MODEL_REGISTRY_SYNC:-}" = "yes" ]; then
  python model_registry_sync.py || echo "model registry sync skipped"
fi

exec "$@"
