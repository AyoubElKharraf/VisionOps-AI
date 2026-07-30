from byte_tracker import ByteTrackAdapter
from roi_manager import CrossingDirection, Detection, ROIEngine, TripwireLine


def detection(x: float, y: float = 10, confidence: float = 0.9) -> Detection:
    return Detection(
        x1=x,
        y1=y,
        x2=x + 30,
        y2=y + 60,
        confidence=confidence,
        class_id=0,
        class_name="person",
    )


def test_bytetrack_keeps_identity_across_motion_low_score_and_short_gap():
    tracker = ByteTrackAdapter(track_buffer=10)

    first = tracker.update([detection(10)])
    assert len(first) == 1
    track_id = first[0].track_id
    assert track_id is not None

    moved = tracker.update([detection(16)])
    weak = tracker.update([detection(22, confidence=0.15)])
    assert moved[0].track_id == track_id
    assert weak[0].track_id == track_id

    assert tracker.update([]) == []
    recovered = tracker.update([detection(34)])
    assert recovered[0].track_id == track_id


def test_recorded_bytetrack_identity_preserves_tripwire_semantics():
    roi = ROIEngine()
    roi.add_tripwire(
        TripwireLine(
            name="gate",
            start=(0, 100),
            end=(200, 100),
            direction=CrossingDirection.BOTH,
        )
    )

    before = detection(50, y=20)
    before.track_id = 42
    roi.record_tracks([before])
    assert roi.check_line_crossings([before]) == []

    after = detection(52, y=80)
    after.track_id = 42
    roi.record_tracks([after])
    events = roi.check_line_crossings([after])

    assert len(events) == 1
    assert events[0].track_id == 42
    assert events[0].line_name == "gate"
