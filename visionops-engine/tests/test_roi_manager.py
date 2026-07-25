"""Unit tests — ROI / tripwire geometry (no GPU, no Docker)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))

from roi_manager import (  # noqa: E402
    CrossingDirection,
    Detection,
    ROIEngine,
    TripwireLine,
    ZoneROI,
    detections_from_array,
)
import numpy as np


def test_zone_requires_three_points():
    with pytest.raises(Exception):
        ZoneROI(name="bad", points=[(0, 0), (1, 1)])


def test_intrusion_when_foot_inside_zone():
    engine = ROIEngine()
    engine.add_zone(
        ZoneROI(
            name="restricted",
            points=[(0, 0), (100, 0), (100, 100), (0, 100)],
            max_allowed_objects=0,
            forbidden_classes=["person"],
        )
    )
    # bbox bottom-center (50, 90) is inside
    det = Detection(
        x1=40, y1=20, x2=60, y2=90, confidence=0.9, class_id=0, class_name="person"
    )
    alerts = engine.check_zone_intrusion([det])
    assert len(alerts) == 1
    assert alerts[0].zone_name == "restricted"
    assert "Intrusion" in alerts[0].message


def test_no_intrusion_outside_zone():
    engine = ROIEngine()
    engine.add_zone(
        ZoneROI(
            name="restricted",
            points=[(0, 0), (50, 0), (50, 50), (0, 50)],
            max_allowed_objects=0,
            forbidden_classes=["person"],
        )
    )
    det = Detection(
        x1=200, y1=200, x2=240, y2=280, confidence=0.8, class_id=0, class_name="person"
    )
    assert engine.check_zone_intrusion([det]) == []


def test_tripwire_crossing_detected():
    engine = ROIEngine(history_len=10)
    engine.add_tripwire(
        TripwireLine(
            name="gate",
            start=(0, 50),
            end=(200, 50),
            direction=CrossingDirection.BOTH,
        )
    )
    # Simulate track moving from above line to below
    d1 = Detection(
        track_id=1, x1=90, y1=10, x2=110, y2=30, confidence=0.9, class_id=0, class_name="person"
    )
    d2 = Detection(
        track_id=1, x1=90, y1=70, x2=110, y2=90, confidence=0.9, class_id=0, class_name="person"
    )
    engine.assign_tracks([d1])
    engine.assign_tracks([d2])
    events = engine.check_line_crossings([d2])
    assert len(events) == 1
    assert events[0].line_name == "gate"
    assert events[0].track_id == 1


def test_detections_from_array():
    arr = np.array([[10, 20, 30, 40, 0.95, 0]], dtype=np.float32)
    dets = detections_from_array(arr, {0: "person"})
    assert len(dets) == 1
    assert dets[0].class_name == "person"
    assert dets[0].confidence == pytest.approx(0.95)
