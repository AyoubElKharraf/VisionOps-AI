"""ByteTrack adapter for VisionOps Detection models."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from ultralytics.trackers.byte_tracker import BYTETracker

from roi_manager import Detection


class _TrackerDetections:
    """Minimal Ultralytics Results-like input consumed by BYTETracker."""

    def __init__(self, detections: list[Detection]) -> None:
        self._detections = detections
        if detections:
            xyxy = np.asarray(
                [[d.x1, d.y1, d.x2, d.y2] for d in detections],
                dtype=np.float32,
            )
            self.conf = np.asarray([d.confidence for d in detections], dtype=np.float32)
            self.cls = np.asarray([d.class_id for d in detections], dtype=np.float32)
        else:
            xyxy = np.empty((0, 4), dtype=np.float32)
            self.conf = np.empty((0,), dtype=np.float32)
            self.cls = np.empty((0,), dtype=np.float32)
        self.xyxy = xyxy

    @property
    def xywh(self) -> np.ndarray:
        out = self.xyxy.copy()
        if len(out):
            out[:, 0] = (self.xyxy[:, 0] + self.xyxy[:, 2]) / 2
            out[:, 1] = (self.xyxy[:, 1] + self.xyxy[:, 3]) / 2
            out[:, 2] = self.xyxy[:, 2] - self.xyxy[:, 0]
            out[:, 3] = self.xyxy[:, 3] - self.xyxy[:, 1]
        return out

    def __len__(self) -> int:
        return len(self._detections)

    def __getitem__(self, index: np.ndarray) -> _TrackerDetections:
        selected = np.flatnonzero(index) if np.asarray(index).dtype.kind == "b" else index
        return _TrackerDetections([self._detections[int(i)] for i in selected])


class ByteTrackAdapter:
    """Assign persistent ByteTrack IDs and return only activated tracks."""

    def __init__(
        self,
        *,
        track_high_thresh: float = 0.25,
        track_low_thresh: float = 0.1,
        new_track_thresh: float = 0.25,
        track_buffer: int = 30,
        match_thresh: float = 0.8,
        fuse_score: bool = True,
    ) -> None:
        if not 0 <= track_low_thresh <= track_high_thresh <= 1:
            raise ValueError("Expected 0 <= track_low_thresh <= track_high_thresh <= 1")
        self._tracker = BYTETracker(
            SimpleNamespace(
                track_high_thresh=track_high_thresh,
                track_low_thresh=track_low_thresh,
                new_track_thresh=new_track_thresh,
                track_buffer=track_buffer,
                match_thresh=match_thresh,
                fuse_score=fuse_score,
            )
        )

    def update(self, detections: list[Detection]) -> list[Detection]:
        """Update tracks and mutate matched detections with stable track IDs."""
        tracked = self._tracker.update(_TrackerDetections(detections))
        output: list[Detection] = []
        for row in tracked:
            # BYTETracker output: x1,y1,x2,y2,track_id,score,class_id,input_idx
            input_idx = int(row[7])
            if not 0 <= input_idx < len(detections):
                continue
            detection = detections[input_idx]
            detection.track_id = int(row[4])
            # Use Kalman-filtered coordinates to reduce box jitter.
            detection.x1, detection.y1, detection.x2, detection.y2 = map(float, row[:4])
            output.append(detection)
        return output
