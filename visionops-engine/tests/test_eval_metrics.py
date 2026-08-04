"""Unit tests for offline eval metrics and harness (prediction mode)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))

from eval_metrics import (  # noqa: E402
    Box,
    average_precision,
    box_iou,
    evaluate_dataset,
)


def test_box_iou_identical_is_one():
    a = Box((0, 0, 10, 10), "person")
    assert box_iou(a, a) == pytest.approx(1.0)


def test_box_iou_no_overlap_is_zero():
    a = Box((0, 0, 10, 10), "person")
    b = Box((20, 20, 30, 30), "person")
    assert box_iou(a, b) == 0.0


def test_box_iou_partial():
    a = Box((0, 0, 10, 10), "person")
    b = Box((5, 0, 15, 10), "person")
    # intersection 5*10=50, union 100+100-50=150
    assert box_iou(a, b) == pytest.approx(50 / 150)


def test_average_precision_perfect():
    recalls = [0.5, 1.0]
    precisions = [1.0, 1.0]
    assert average_precision(recalls, precisions) == pytest.approx(1.0)


def test_evaluate_perfect_match():
    gt = [Box((10, 10, 50, 80), "person")]
    pred = [Box((11, 11, 49, 79), "person", confidence=0.9)]
    report = evaluate_dataset([(gt, pred)], classes=["person"], iou_threshold=0.5)
    assert report.map50 == pytest.approx(1.0)
    assert report.total_tp == 1
    assert report.total_fp == 0
    assert report.false_alarm_rate == 0.0


def test_evaluate_false_alarm_only():
    gt: list[Box] = []
    pred = [Box((0, 0, 20, 20), "person", confidence=0.8)]
    report = evaluate_dataset([(gt, pred)], classes=["person"], iou_threshold=0.5)
    assert report.total_fp == 1
    assert report.total_tp == 0
    assert report.false_alarm_rate == pytest.approx(1.0)
    assert report.false_alarms_per_image == pytest.approx(1.0)
    assert report.map50 == 0.0


def test_evaluate_missed_detection():
    gt = [Box((0, 0, 40, 40), "person")]
    pred: list[Box] = []
    report = evaluate_dataset([(gt, pred)], classes=["person"], iou_threshold=0.5)
    assert report.total_fn == 1
    assert report.micro_recall == 0.0


def test_harness_cli_predictions_mode(tmp_path: Path):
    fixture = ENGINE / "eval" / "fixtures" / "mini"
    report_path = tmp_path / "report.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ENGINE / "eval_harness.py"),
            "--dataset",
            str(fixture / "labels.json"),
            "--predictions",
            str(fixture / "preds.json"),
            "--alerts",
            "off",
            "--report",
            str(report_path),
        ],
        cwd=str(ENGINE),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["num_images"] == 3
    assert "map50" in data
    assert "false_alarm_rate" in data
    # fixture: 1 perfect TP, 1 TP + 1 FP on partial, 1 FP on empty → TP=2 FP=2 FAR=0.5
    assert data["total_tp"] == 2
    assert data["total_fp"] == 2
    assert data["false_alarm_rate"] == pytest.approx(0.5)
    assert data["map50"] > 0.0
    assert data.get("alert_mode") == "off"


def test_alert_evaluate_false_alarm_and_miss():
    from eval_metrics import AlertLabel, evaluate_alerts

    pairs = [
        (
            [AlertLabel("roi_intrusion", "dock", "intrusion")],
            [AlertLabel("roi_intrusion", "dock", "intrusion")],
        ),
        (
            [],
            [AlertLabel("roi_intrusion", "dock", "intrusion")],
        ),
        (
            [AlertLabel("roi_intrusion", "lobby", "over_capacity")],
            [],
        ),
    ]
    report = evaluate_alerts(pairs)
    assert report.total_tp == 1
    assert report.total_fp == 1
    assert report.total_fn == 1
    assert report.false_alarm_rate == pytest.approx(0.5)
    assert report.frames_with_fp == 1
    assert report.frames_with_fn == 1


def test_harness_cli_alert_predictions_mode(tmp_path: Path):
    fixture = ENGINE / "eval" / "fixtures" / "alerts_mini"
    report_path = tmp_path / "alerts_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ENGINE / "eval_harness.py"),
            "--dataset",
            str(fixture / "labels.json"),
            "--predictions",
            str(fixture / "preds.json"),
            "--alerts",
            "predictions",
            "--report",
            str(report_path),
        ],
        cwd=str(ENGINE),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(report_path.read_text(encoding="utf-8"))
    alerts = data["alerts"]
    # intrusion_tp TP, clean_frame FP, capacity TP, missed FN → TP=2 FP=1 FN=1
    assert alerts["total_tp"] == 2
    assert alerts["total_fp"] == 1
    assert alerts["total_fn"] == 1
    assert alerts["false_alarm_rate"] == pytest.approx(1 / 3)


def test_harness_cli_alert_simulate_mode(tmp_path: Path):
    fixture = ENGINE / "eval" / "fixtures" / "alerts_mini"
    report_path = tmp_path / "sim_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ENGINE / "eval_harness.py"),
            "--dataset",
            str(fixture / "labels.json"),
            "--predictions",
            str(fixture / "preds.json"),
            "--alerts",
            "simulate",
            "--report",
            str(report_path),
        ],
        cwd=str(ENGINE),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(report_path.read_text(encoding="utf-8"))
    alerts = data["alerts"]
    # ROIEngine on boxes: intrusion TP, clean no alert, capacity TP, miss FN
    assert alerts["total_tp"] == 2
    assert alerts["total_fp"] == 0
    assert alerts["total_fn"] == 1
    assert alerts["false_alarm_rate"] == 0.0


def test_generate_fixture_images_for_manual_onnx(tmp_path: Path):
    """Ensure OpenCV can materialize placeholder frames (optional local ONNX runs)."""
    import cv2

    out = tmp_path / "images"
    out.mkdir()
    for name in ("img_perfect", "img_partial", "img_empty"):
        img = np.zeros((120, 160, 3), dtype=np.uint8)
        img[:] = (40, 40, 40)
        if name != "img_empty":
            cv2.rectangle(img, (20, 15), (70, 100), (0, 200, 0), -1)
        ok = cv2.imwrite(str(out / f"{name}.jpg"), img)
        assert ok
