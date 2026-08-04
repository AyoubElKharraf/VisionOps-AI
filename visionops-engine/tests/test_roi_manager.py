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
    zones_from_api,
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
    assert alerts[0].reason == "intrusion"
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


def test_occupancy_counts_unique_person_tracks():
    engine = ROIEngine()
    engine.add_zone(
        ZoneROI(
            name="lobby",
            points=[(0, 0), (300, 0), (300, 300), (0, 300)],
            max_allowed_objects=2,
            forbidden_classes=[],
        )
    )
    dets = [
        Detection(
            track_id=1, x1=10, y1=10, x2=40, y2=80, confidence=0.9, class_id=0, class_name="person"
        ),
        Detection(
            track_id=1, x1=12, y1=12, x2=42, y2=82, confidence=0.9, class_id=0, class_name="person"
        ),
        Detection(
            track_id=2, x1=100, y1=20, x2=140, y2=100, confidence=0.9, class_id=0, class_name="person"
        ),
        Detection(
            track_id=3, x1=50, y1=50, x2=90, y2=90, confidence=0.8, class_id=2, class_name="car"
        ),
    ]
    occ = engine.zone_occupancy(dets)
    assert len(occ) == 1
    assert occ[0].count == 2
    assert occ[0].max_allowed == 2
    assert occ[0].occupancy_pct == pytest.approx(100.0)
    assert occ[0].over_capacity is False
    assert engine.check_zone_intrusion(dets) == []


def test_over_capacity_alert_without_intrusion():
    engine = ROIEngine()
    engine.add_zone(
        ZoneROI(
            name="elevator",
            points=[(0, 0), (200, 0), (200, 200), (0, 200)],
            max_allowed_objects=1,
            forbidden_classes=[],
        )
    )
    dets = [
        Detection(
            track_id=7, x1=20, y1=20, x2=50, y2=100, confidence=0.9, class_id=0, class_name="person"
        ),
        Detection(
            track_id=8, x1=80, y1=20, x2=110, y2=100, confidence=0.9, class_id=0, class_name="person"
        ),
    ]
    alerts = engine.check_zone_intrusion(dets)
    assert len(alerts) == 1
    assert alerts[0].reason == "over_capacity"
    assert alerts[0].object_count == 2
    assert alerts[0].max_allowed == 1
    assert "CAPACITÉ" in alerts[0].message
    assert engine.zone_occupancy(dets)[0].over_capacity is True

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


def test_zones_from_api_scales_normalized_points():
    zones = zones_from_api(
        [
            {
                "name": "loading-dock",
                "points": [[0.1, 0.2], [0.9, 0.2], [0.9, 0.8], [0.1, 0.8]],
                "max_allowed_objects": 1,
                "forbidden_classes": ["person"],
                "is_active": True,
            }
        ],
        width=1000,
        height=500,
    )

    assert len(zones) == 1
    assert zones[0].points[0] == pytest.approx((100, 100))
    assert zones[0].points[2] == pytest.approx((900, 400))
    assert zones[0].max_allowed_objects == 1


def test_zones_from_api_skips_inactive_and_invalid_zones():
    zones = zones_from_api(
        [
            {
                "name": "inactive",
                "points": [[0, 0], [1, 0], [1, 1]],
                "is_active": False,
            },
            {
                "name": "invalid",
                "points": [[0, 0], [1, 1]],
                "is_active": True,
            },
        ],
        width=640,
        height=480,
    )

    assert zones == []
