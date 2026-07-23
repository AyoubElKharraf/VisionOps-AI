"""
VisionOps AI — ONNX Runtime YOLOv8 inference engine (Phase 2).

Preprocess (letterbox) → ONNX session → NMS → boxes [x1,y1,x2,y2,conf,cls].
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

logger = logging.getLogger("visionops-onnx")

# COCO class names (YOLOv8 default)
COCO_NAMES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    4: "airplane",
    5: "bus",
    6: "train",
    7: "truck",
    8: "boat",
    9: "traffic light",
    10: "fire hydrant",
    11: "stop sign",
    12: "parking meter",
    13: "bench",
    14: "bird",
    15: "cat",
    16: "dog",
    17: "horse",
    18: "sheep",
    19: "cow",
    20: "elephant",
    21: "bear",
    22: "zebra",
    23: "giraffe",
    24: "backpack",
    25: "umbrella",
    26: "handbag",
    27: "tie",
    28: "suitcase",
    29: "frisbee",
    30: "skis",
    31: "snowboard",
    32: "sports ball",
    33: "kite",
    34: "baseball bat",
    35: "baseball glove",
    36: "skateboard",
    37: "surfboard",
    38: "tennis racket",
    39: "bottle",
    40: "wine glass",
    41: "cup",
    42: "fork",
    43: "knife",
    44: "spoon",
    45: "bowl",
    46: "banana",
    47: "apple",
    48: "orange",
    49: "broccoli",
    50: "carrot",
    51: "hot dog",
    52: "pizza",
    53: "donut",
    54: "cake",
    55: "chair",
    56: "couch",
    57: "potted plant",
    58: "bed",
    59: "dining table",
    60: "toilet",
    61: "tv",
    62: "laptop",
    63: "mouse",
    64: "remote",
    65: "keyboard",
    66: "cell phone",
    67: "microwave",
    68: "oven",
    69: "toaster",
    70: "sink",
    71: "refrigerator",
    72: "book",
    73: "clock",
    74: "vase",
    75: "scissors",
    76: "teddy bear",
    77: "hair drier",
    78: "toothbrush",
}


@dataclass
class LetterboxMeta:
    ratio: float
    pad_w: float
    pad_h: float
    orig_w: int
    orig_h: int


def letterbox(
    image: np.ndarray,
    new_shape: int = 640,
    color: tuple[int, int, int] = (114, 114, 114),
) -> tuple[np.ndarray, LetterboxMeta]:
    """Resize + pad to square while preserving aspect ratio."""
    h, w = image.shape[:2]
    shape = (new_shape, new_shape)
    ratio = min(shape[0] / h, shape[1] / w)
    new_unpad = (int(round(w * ratio)), int(round(h * ratio)))
    dw = shape[1] - new_unpad[0]
    dh = shape[0] - new_unpad[1]
    dw /= 2.0
    dh /= 2.0

    if (w, h) != new_unpad:
        image = cv2.resize(image, new_unpad, interpolation=cv2.INTER_LINEAR)

    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    image = cv2.copyMakeBorder(image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)

    meta = LetterboxMeta(ratio=ratio, pad_w=dw, pad_h=dh, orig_w=w, orig_h=h)
    return image, meta


def xywh2xyxy(boxes: np.ndarray) -> np.ndarray:
    out = np.empty_like(boxes)
    out[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
    out[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
    out[:, 2] = boxes[:, 0] + boxes[:, 2] / 2.0
    out[:, 3] = boxes[:, 1] + boxes[:, 3] / 2.0
    return out


def nms_numpy(boxes: np.ndarray, scores: np.ndarray, iou_thres: float) -> list[int]:
    """Greedy NMS. boxes in xyxy."""
    if len(boxes) == 0:
        return []

    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1).clip(min=0) * (y2 - y1).clip(min=0)
    order = scores.argsort()[::-1]

    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = (xx2 - xx1).clip(min=0) * (yy2 - yy1).clip(min=0)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-7)
        inds = np.where(iou <= iou_thres)[0]
        order = order[inds + 1]
    return keep


def scale_boxes(boxes: np.ndarray, meta: LetterboxMeta) -> np.ndarray:
    """Map boxes from letterboxed coords back to original image size."""
    boxes = boxes.copy()
    boxes[:, [0, 2]] -= meta.pad_w
    boxes[:, [1, 3]] -= meta.pad_h
    boxes[:, :4] /= meta.ratio
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, meta.orig_w)
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, meta.orig_h)
    return boxes


class ONNXInferenceEngine:
    """YOLOv8 ONNX Runtime inference with letterbox + NMS post-process."""

    def __init__(
        self,
        model_path: str | Path,
        conf_thres: float = 0.25,
        iou_thres: float = 0.45,
        imgsz: int = 640,
        providers: list[str] | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"ONNX model not found: {self.model_path}")

        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.imgsz = imgsz
        self.names = COCO_NAMES

        available = ort.get_available_providers()
        if providers is None:
            providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in available]
            if not providers:
                providers = ["CPUExecutionProvider"]

        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(self.model_path), sess_options=so, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]

        in_shape = self.session.get_inputs()[0].shape
        if isinstance(in_shape[2], int) and in_shape[2] > 0:
            self.imgsz = int(in_shape[2])

        logger.info(
            "ONNX session ready | model=%s | providers=%s | imgsz=%d",
            self.model_path.name,
            self.session.get_providers(),
            self.imgsz,
        )

    def preprocess(self, frame: np.ndarray) -> tuple[np.ndarray, LetterboxMeta]:
        img, meta = letterbox(frame, new_shape=self.imgsz)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))[None, ...]  # NCHW
        return np.ascontiguousarray(img), meta

    def postprocess(self, output: np.ndarray, meta: LetterboxMeta) -> np.ndarray:
        """
        Parse YOLOv8 ONNX output → Nx6 array [x1,y1,x2,y2,conf,cls].

        Typical raw shape: (1, 84, 8400) → transpose to (8400, 84).
        """
        pred = output[0]
        if pred.ndim == 3:
            pred = pred[0]
        # (84, N) → (N, 84) or already (N, 84)
        if pred.shape[0] < pred.shape[1] and pred.shape[0] <= 84 + 10:
            pred = pred.T

        boxes_xywh = pred[:, :4]
        class_scores = pred[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        confidences = class_scores[np.arange(len(class_scores)), class_ids]

        mask = confidences >= self.conf_thres
        boxes_xywh = boxes_xywh[mask]
        confidences = confidences[mask]
        class_ids = class_ids[mask]

        if len(boxes_xywh) == 0:
            return np.zeros((0, 6), dtype=np.float32)

        boxes_xyxy = xywh2xyxy(boxes_xywh)
        keep = nms_numpy(boxes_xyxy, confidences, self.iou_thres)
        boxes_xyxy = boxes_xyxy[keep]
        confidences = confidences[keep]
        class_ids = class_ids[keep]

        boxes_xyxy = scale_boxes(boxes_xyxy, meta)
        dets = np.concatenate(
            [
                boxes_xyxy,
                confidences[:, None],
                class_ids[:, None].astype(np.float32),
            ],
            axis=1,
        ).astype(np.float32)
        return dets

    def predict(self, frame: np.ndarray) -> tuple[np.ndarray, float]:
        """
        Run inference on a BGR frame.

        Returns:
            detections: Nx6 float32 [x1, y1, x2, y2, confidence, class_id]
            infer_ms: pure session.run latency in milliseconds
        """
        blob, meta = self.preprocess(frame)
        t0 = time.perf_counter()
        outputs = self.session.run(self.output_names, {self.input_name: blob})
        infer_ms = (time.perf_counter() - t0) * 1000.0
        dets = self.postprocess(outputs[0], meta)
        return dets, infer_ms

    def class_name(self, class_id: int) -> str:
        return self.names.get(int(class_id), str(int(class_id)))
