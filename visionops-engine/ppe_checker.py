"""Optional PPE / hard-hat detector used by ROI must-wear rules."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

import numpy as np

from roi_manager import Detection

logger = logging.getLogger("visionops-ppe")

HARDHAT_ALIASES = {
    "hardhat",
    "hard_hat",
    "helmet",
    "safety helmet",
    "safety_helmet",
    "head",
    "hat",
}


def normalize_class(name: str) -> str:
    return (name or "").strip().lower().replace("-", "_").replace(" ", "_")


def is_hardhat_class(name: str) -> bool:
    n = normalize_class(name)
    if n in HARDHAT_ALIASES:
        return True
    return "hardhat" in n or "helmet" in n


def hardhats_from_detections(detections: Iterable[Detection]) -> list[Detection]:
    return [d for d in detections if is_hardhat_class(d.class_name)]


def person_has_hardhat(
    person: Detection,
    hardhats: Iterable[Detection],
    *,
    min_iou: float = 0.02,
) -> bool:
    """True if any hardhat box overlaps the upper portion of the person box."""
    px1, py1, px2, py2 = person.x1, person.y1, person.x2, person.y2
    head_y2 = py1 + max(8.0, (py2 - py1) * 0.45)
    head_area = max(1.0, (px2 - px1) * (head_y2 - py1))
    for hat in hardhats:
        ix1 = max(px1, hat.x1)
        iy1 = max(py1, hat.y1)
        ix2 = min(px2, hat.x2)
        iy2 = min(head_y2, hat.y2)
        iw = max(0.0, ix2 - ix1)
        ih = max(0.0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            # also accept hardhat center inside head band
            cx, cy = hat.center
            if px1 <= cx <= px2 and py1 <= cy <= head_y2:
                return True
            continue
        hat_area = max(1.0, (hat.x2 - hat.x1) * (hat.y2 - hat.y1))
        iou = inter / (head_area + hat_area - inter)
        if iou >= min_iou or inter / head_area >= 0.08:
            return True
    return False


class PPEDetector:
    """
    Secondary hard-hat detector.

    Loads Ultralytics weights from VISIONOPS_PPE_MODEL / --ppe-model when set.
    If unavailable, only hardhat classes already present in primary detections are used.
    """

    def __init__(self, model_path: str | None = None, conf: float = 0.35) -> None:
        env_path = (model_path or os.environ.get("VISIONOPS_PPE_MODEL") or "").strip()
        self.conf = conf
        self.model = None
        self.model_path = env_path
        self.enabled = False
        if not env_path:
            logger.info("PPE model not configured (set VISIONOPS_PPE_MODEL to enable)")
            return
        path = Path(env_path)
        if not path.exists() and "/" not in env_path and "\\" not in env_path:
            # Allow ultralytics hub-style names (e.g. keremberke/...)
            pass
        elif env_path and not path.exists() and not env_path.startswith("keremberke/"):
            logger.warning("PPE model path not found: %s", env_path)
            return
        try:
            from ultralytics import YOLO

            self.model = YOLO(env_path)
            self.enabled = True
            logger.info("PPE detector ready | model=%s", env_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PPE detector disabled: %s", exc)
            self.model = None
            self.enabled = False

    def detect(self, frame: np.ndarray) -> list[Detection]:
        if self.model is None or frame is None or frame.size == 0:
            return []
        try:
            results = self.model.predict(frame, conf=self.conf, verbose=False)
        except Exception as exc:  # noqa: BLE001
            logger.debug("PPE predict failed: %s", exc)
            return []
        if not results:
            return []
        out: list[Detection] = []
        result = results[0]
        names = result.names or {}
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []
        for box in boxes:
            try:
                cls_id = int(box.cls.item())
                name = str(names.get(cls_id, cls_id))
                if not is_hardhat_class(name):
                    continue
                xyxy = box.xyxy[0].tolist()
                conf = float(box.conf.item()) if box.conf is not None else 0.0
                out.append(
                    Detection(
                        x1=float(xyxy[0]),
                        y1=float(xyxy[1]),
                        x2=float(xyxy[2]),
                        y2=float(xyxy[3]),
                        confidence=conf,
                        class_id=cls_id,
                        class_name=name,
                    )
                )
            except Exception:  # noqa: BLE001
                continue
        return out
