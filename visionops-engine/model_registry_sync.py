"""
Pull active model artifacts from the VisionOps API into WEIGHTS_DIR.

Enabled when MODEL_REGISTRY_SYNC is truthy. Falls back silently when the API
has no active models or is unreachable so the bundled yolov8n weights still work.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import requests

logger = logging.getLogger("visionops-model-registry")

ENGINE_DIR = Path(__file__).resolve().parent


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def sync_active_models(
    *,
    api_url: str | None = None,
    api_key: str | None = None,
    weights_dir: Path | None = None,
) -> dict[str, Path]:
    """
    Download active detector/ppe weights. Returns role -> local path.
    Also sets YOLO_MODEL / ONNX_MODEL / USE_ONNX / VISIONOPS_PPE_MODEL in os.environ
    when a matching active artifact is present.
    """
    if not _truthy(os.environ.get("MODEL_REGISTRY_SYNC", "0")):
        logger.info("MODEL_REGISTRY_SYNC disabled — skipping registry pull")
        return {}

    base = (api_url or os.environ.get("API_URL") or "http://backend:8001").rstrip("/")
    key = api_key if api_key is not None else os.environ.get("VISIONOPS_API_KEY", "")
    dest = Path(weights_dir or os.environ.get("WEIGHTS_DIR") or (ENGINE_DIR / "models"))
    dest.mkdir(parents=True, exist_ok=True)

    headers = {"X-API-Key": key} if key else {}
    try:
        resp = requests.get(f"{base}/api/v1/models/active", headers=headers, timeout=30)
        resp.raise_for_status()
        active = resp.json()
    except requests.RequestException as exc:
        logger.warning("Model registry unavailable (%s) — using local weights", exc)
        return {}

    resolved: dict[str, Path] = {}
    for role in ("detector", "ppe"):
        meta = active.get(role)
        if not meta:
            continue
        model_id = meta.get("id")
        filename = meta.get("filename") or f"{role}.bin"
        fmt = (meta.get("format") or "").lower()
        local = dest / f"registry_{role}_{meta.get('version', 'latest')}_{filename}"
        try:
            dl = requests.get(
                f"{base}/api/v1/models/{model_id}/download",
                headers=headers,
                timeout=300,
            )
            dl.raise_for_status()
            local.write_bytes(dl.content)
        except requests.RequestException as exc:
            logger.warning("Failed to download %s model %s: %s", role, model_id, exc)
            continue

        resolved[role] = local
        logger.info(
            "Registry sync | role=%s name=%s version=%s -> %s (%d bytes)",
            role,
            meta.get("name"),
            meta.get("version"),
            local,
            local.stat().st_size,
        )

        if role == "detector":
            if fmt == "onnx" or str(local).endswith(".onnx"):
                os.environ["ONNX_MODEL"] = str(local)
                os.environ["USE_ONNX"] = "true"
            else:
                os.environ["YOLO_MODEL"] = str(local)
                os.environ["USE_ONNX"] = "false"
        elif role == "ppe":
            os.environ["VISIONOPS_PPE_MODEL"] = str(local)

    if not resolved:
        logger.info("No active registry models — keeping bootstrap weights")
    return resolved


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    paths = sync_active_models()
    for role, path in paths.items():
        print(f"{role}={path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
