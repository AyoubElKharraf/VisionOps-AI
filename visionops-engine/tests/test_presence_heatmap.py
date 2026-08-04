"""Unit tests for presence heatmap accumulation."""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))

from presence_heatmap import PresenceHeatmap  # noqa: E402
from roi_manager import Detection  # noqa: E402


def test_heatmap_accumulates_person_footpoints():
    hm = PresenceHeatmap(cols=20, rows=10, decay=1.0, min_emit=0.01)
    det = Detection(
        track_id=1,
        x1=90,
        y1=40,
        x2=110,
        y2=80,
        confidence=0.9,
        class_id=0,
        class_name="person",
    )
    # foot at (100, 80) → col ~10, row ~8 for 200x100 frame
    hm.update([det], frame_width=200, frame_height=100)
    snap = hm.snapshot()
    assert snap["cols"] == 20
    assert snap["rows"] == 10
    assert snap["peak"] > 0
    assert len(snap["cells"]) >= 1
    # densest cell near the foot
    top = snap["cells"][0]
    assert top[2] == 1.0
    assert abs(top[0] - 10) <= 1
    assert abs(top[1] - 8) <= 1


def test_heatmap_ignores_non_person_and_decays():
    hm = PresenceHeatmap(cols=16, rows=9, decay=0.5, min_emit=0.01)
    car = Detection(
        track_id=2,
        x1=10,
        y1=10,
        x2=40,
        y2=40,
        confidence=0.8,
        class_id=2,
        class_name="car",
    )
    hm.update([car], frame_width=160, frame_height=90)
    assert hm.snapshot()["cells"] == []

    person = Detection(
        track_id=3,
        x1=70,
        y1=30,
        x2=90,
        y2=70,
        confidence=0.9,
        class_id=0,
        class_name="person",
    )
    hm.update([person], frame_width=160, frame_height=90)
    peak1 = hm.snapshot()["peak"]
    hm.update([], frame_width=160, frame_height=90)
    peak2 = hm.snapshot()["peak"]
    assert peak1 > 0
    assert peak2 < peak1
