"""Unit tests — ONNX preprocess / NMS helpers (no model weights required)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))

from onnx_engine import letterbox, nms_numpy, scale_boxes, xywh2xyxy, LetterboxMeta  # noqa: E402


def test_letterbox_square_output():
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    out, meta = letterbox(img, new_shape=640)
    assert out.shape == (640, 640, 3)
    assert meta.orig_w == 640
    assert meta.orig_h == 480
    assert meta.ratio > 0


def test_xywh2xyxy():
    boxes = np.array([[100.0, 100.0, 50.0, 40.0]], dtype=np.float32)
    xyxy = xywh2xyxy(boxes)
    assert xyxy[0, 0] == pytest.approx(75.0)
    assert xyxy[0, 1] == pytest.approx(80.0)
    assert xyxy[0, 2] == pytest.approx(125.0)
    assert xyxy[0, 3] == pytest.approx(120.0)


def test_nms_keeps_best_of_overlaps():
    boxes = np.array(
        [
            [0, 0, 10, 10],
            [1, 1, 11, 11],  # high overlap with first
            [50, 50, 60, 60],
        ],
        dtype=np.float32,
    )
    scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)
    keep = nms_numpy(boxes, scores, iou_thres=0.3)
    assert 0 in keep
    assert 2 in keep
    assert 1 not in keep


def test_scale_boxes_removes_padding():
    meta = LetterboxMeta(ratio=0.5, pad_w=10, pad_h=20, orig_w=100, orig_h=80)
    boxes = np.array([[10, 20, 60, 100]], dtype=np.float32)
    out = scale_boxes(boxes, meta)
    # after unpad: [0,0,50,80] then /ratio → [0,0,100,160] clipped to orig
    assert out[0, 0] == pytest.approx(0.0)
    assert out[0, 2] == pytest.approx(100.0)
