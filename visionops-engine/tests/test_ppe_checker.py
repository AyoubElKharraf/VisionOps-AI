"""Unit tests for PPE / hard-hat matching."""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))

from ppe_checker import (  # noqa: E402
    hardhats_from_detections,
    is_hardhat_class,
    person_has_hardhat,
)
from roi_manager import Detection, ROIEngine, ZoneROI  # noqa: E402


def test_hardhat_class_aliases():
    assert is_hardhat_class("Hardhat")
    assert is_hardhat_class("safety helmet")
    assert not is_hardhat_class("person")


def test_person_has_hardhat_overlaps_head():
    person = Detection(
        track_id=1, x1=100, y1=100, x2=200, y2=300, confidence=0.9, class_id=0, class_name="person"
    )
    hat = Detection(
        track_id=None, x1=120, y1=100, x2=180, y2=150, confidence=0.8, class_id=1, class_name="hardhat"
    )
    assert person_has_hardhat(person, [hat]) is True
    far = Detection(
        track_id=None, x1=400, y1=100, x2=450, y2=140, confidence=0.8, class_id=1, class_name="helmet"
    )
    assert person_has_hardhat(person, [far]) is False


def test_ppe_violation_when_missing_hardhat():
    engine = ROIEngine()
    engine.add_zone(
        ZoneROI(
            name="site",
            points=[(0, 0), (400, 0), (400, 400), (0, 400)],
            forbidden_classes=[],
            require_hardhat=True,
        )
    )
    person = Detection(
        track_id=9, x1=50, y1=50, x2=120, y2=220, confidence=0.9, class_id=0, class_name="person"
    )
    events = engine.check_ppe_violations([person], hardhats=[])
    assert len(events) == 1
    assert "casque" in events[0].message.lower() or "PPE" in events[0].message

    hat = Detection(
        x1=60, y1=50, x2=110, y2=90, confidence=0.85, class_id=1, class_name="hardhat"
    )
    assert engine.check_ppe_violations([person], hardhats=[hat]) == []
    assert hardhats_from_detections([person, hat]) == [hat]
