"""
VisionOps AI — Spatial ROI / Tripwire geometry engine (Phase 2).

Uses Shapely for polygon intrusion and line-crossing detection.
"""

from __future__ import annotations

from collections import defaultdict, deque
from enum import Enum
from typing import Any, Iterable

import numpy as np
from pydantic import BaseModel, Field, field_validator
from shapely.geometry import LineString, Point, Polygon, box as shapely_box
from shapely.geometry.base import BaseGeometry


class CrossingDirection(str, Enum):
    IN = "IN"
    OUT = "OUT"
    BOTH = "BOTH"


class ZoneROI(BaseModel):
    """Polygonal region of interest with intrusion rules."""

    name: str
    points: list[tuple[float, float]] = Field(..., min_length=3)
    max_allowed_objects: int = Field(default=0, ge=0)
    forbidden_classes: list[str] = Field(default_factory=lambda: ["person"])

    @field_validator("points")
    @classmethod
    def _closed_enough(cls, value: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(value) < 3:
            raise ValueError("ZoneROI requires at least 3 points")
        return value

    def to_polygon(self) -> Polygon:
        poly = Polygon(self.points)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly


class TripwireLine(BaseModel):
    """Virtual counting / crossing line."""

    name: str
    start: tuple[float, float]
    end: tuple[float, float]
    direction: CrossingDirection = CrossingDirection.BOTH

    def to_linestring(self) -> LineString:
        return LineString([self.start, self.end])

    @property
    def segment(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return (self.start, self.end)


class Detection(BaseModel):
    """Normalized detection used by ROIEngine."""

    track_id: int | None = None
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    class_id: int
    class_name: str = "object"

    @property
    def foot_point(self) -> tuple[float, float]:
        """Bottom-center of the bounding box (typical person contact point)."""
        return ((self.x1 + self.x2) / 2.0, self.y2)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    def as_polygon(self) -> Polygon:
        return shapely_box(self.x1, self.y1, self.x2, self.y2)


class ZoneAlert(BaseModel):
    zone_name: str
    object_count: int
    max_allowed: int
    offending_classes: list[str]
    message: str


class CrossingEvent(BaseModel):
    line_name: str
    track_id: int
    direction: str
    class_name: str
    message: str


def _side_of_line(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    """Signed cross-product: >0 left of directed line, <0 right."""
    return (end[0] - start[0]) * (point[1] - start[1]) - (end[1] - start[1]) * (point[0] - start[0])


class ROIEngine:
    """Evaluates zone intrusions and tripwire crossings over time."""

    def __init__(self, history_len: int = 15) -> None:
        self.zones: list[ZoneROI] = []
        self.tripwires: list[TripwireLine] = []
        self.history_len = history_len
        self._trajectories: dict[int, deque[tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=history_len)
        )
        self._last_side: dict[tuple[int, str], float] = {}
        self._crossing_cooldown: dict[tuple[int, str], int] = {}
        self._frame_idx = 0
        self._next_track_id = 1
        self._prev_centers: dict[int, tuple[float, float]] = {}

    def add_zone(self, zone: ZoneROI) -> None:
        self.zones.append(zone)

    def replace_zones(self, zones: Iterable[ZoneROI]) -> None:
        """Atomically replace zone rules without resetting tracking state."""
        self.zones = list(zones)

    def add_tripwire(self, line: TripwireLine) -> None:
        self.tripwires.append(line)

    def assign_tracks(
        self,
        detections: list[Detection],
        max_distance: float = 80.0,
    ) -> list[Detection]:
        """
        Lightweight nearest-centroid tracker for tripwire trajectories.
        Mutates detections in-place with track_id.
        """
        unused_prev = dict(self._prev_centers)
        assigned: dict[int, tuple[float, float]] = {}

        for det in detections:
            cx, cy = det.center
            best_id = None
            best_dist = max_distance
            for tid, (px, py) in unused_prev.items():
                dist = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_id = tid
            if best_id is not None:
                det.track_id = best_id
                del unused_prev[best_id]
            else:
                det.track_id = self._next_track_id
                self._next_track_id += 1
            assigned[det.track_id] = (cx, cy)
            self._trajectories[det.track_id].append((cx, cy))

        self._prev_centers = assigned
        return detections

    def check_zone_intrusion(
        self,
        detections: Iterable[Detection],
        *,
        use_foot_point: bool = True,
        use_bbox_intersection: bool = True,
    ) -> list[ZoneAlert]:
        alerts: list[ZoneAlert] = []
        dets = list(detections)

        for zone in self.zones:
            poly = zone.to_polygon()
            inside: list[Detection] = []
            for det in dets:
                foot = Point(det.foot_point if use_foot_point else det.center)
                intersects = False
                if use_foot_point and poly.contains(foot):
                    intersects = True
                elif use_bbox_intersection and poly.intersects(det.as_polygon()):
                    intersects = True
                if intersects:
                    inside.append(det)

            offending = [
                d.class_name
                for d in inside
                if not zone.forbidden_classes or d.class_name in zone.forbidden_classes
            ]
            count = len(inside)
            forbidden_hit = any(
                d.class_name in zone.forbidden_classes for d in inside
            ) if zone.forbidden_classes else count > 0

            if count > zone.max_allowed_objects or forbidden_hit:
                alerts.append(
                    ZoneAlert(
                        zone_name=zone.name,
                        object_count=count,
                        max_allowed=zone.max_allowed_objects,
                        offending_classes=sorted(set(offending)),
                        message=f"ALERTE ROI : Intrusion détectée ! [{zone.name}] count={count}",
                    )
                )
        return alerts

    def check_line_crossings(self, detections: Iterable[Detection]) -> list[CrossingEvent]:
        """Detect crossings using recent centroid trajectory vs tripwire segment."""
        events: list[CrossingEvent] = []
        self._frame_idx += 1

        # decay cooldowns
        expired = [k for k, v in self._crossing_cooldown.items() if v <= self._frame_idx]
        for k in expired:
            del self._crossing_cooldown[k]

        for det in detections:
            if det.track_id is None:
                continue
            traj = self._trajectories.get(det.track_id)
            if not traj or len(traj) < 2:
                continue

            path = LineString(list(traj))
            for wire in self.tripwires:
                key = (det.track_id, wire.name)
                if key in self._crossing_cooldown:
                    continue

                line = wire.to_linestring()
                if not path.intersects(line):
                    # update side memory
                    self._last_side[key] = _side_of_line(traj[-1], wire.start, wire.end)
                    continue

                prev = traj[0]
                curr = traj[-1]
                side_prev = _side_of_line(prev, wire.start, wire.end)
                side_curr = _side_of_line(curr, wire.start, wire.end)

                if side_prev == 0 or side_curr == 0 or side_prev * side_curr > 0:
                    # No clear side change (tangent / same side)
                    continue

                # Positive→negative = crossed from left to right relative to start→end
                crossed_dir = "OUT" if side_prev > 0 and side_curr < 0 else "IN"

                if wire.direction != CrossingDirection.BOTH and wire.direction.value != crossed_dir:
                    continue

                events.append(
                    CrossingEvent(
                        line_name=wire.name,
                        track_id=det.track_id,
                        direction=crossed_dir,
                        class_name=det.class_name,
                        message=(
                            f"ALERTE TRIPWIRE : {wire.name} crossed {crossed_dir} "
                            f"by track={det.track_id} ({det.class_name})"
                        ),
                    )
                )
                self._crossing_cooldown[key] = self._frame_idx + 15
                self._last_side[key] = side_curr

        return events

    @staticmethod
    def geometry_overlay_points(geom: BaseGeometry) -> list[tuple[int, int]]:
        if geom.is_empty:
            return []
        if isinstance(geom, Polygon):
            coords = list(geom.exterior.coords)
        elif isinstance(geom, LineString):
            coords = list(geom.coords)
        else:
            return []
        return [(int(x), int(y)) for x, y in coords]


def zones_from_api(
    payload: Iterable[dict[str, Any]],
    width: int,
    height: int,
) -> list[ZoneROI]:
    """Convert backend ROI records (normalized or pixel points) for one frame size."""
    zones: list[ZoneROI] = []
    for item in payload:
        if not item.get("is_active", True):
            continue

        raw_points = item.get("points")
        if not isinstance(raw_points, list) or len(raw_points) < 3:
            continue
        try:
            points = [(float(point[0]), float(point[1])) for point in raw_points]
        except (IndexError, TypeError, ValueError):
            continue

        is_normalized = all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in points)
        if is_normalized:
            points = [(x * width, y * height) for x, y in points]

        try:
            zone = ZoneROI(
                name=str(item.get("name") or "zone"),
                points=points,
                max_allowed_objects=max(0, int(item.get("max_allowed_objects", 0))),
                forbidden_classes=[
                    str(class_name)
                    for class_name in (item.get("forbidden_classes") or [])
                ],
            )
        except (TypeError, ValueError):
            continue
        polygon = zone.to_polygon()
        if polygon.is_empty or polygon.area <= 0:
            continue
        zones.append(zone)
    return zones


def detections_from_array(
    dets: np.ndarray,
    names: dict[int, str] | None = None,
) -> list[Detection]:
    """Convert Nx6 [x1,y1,x2,y2,conf,cls] array to Detection models."""
    out: list[Detection] = []
    if dets is None or len(dets) == 0:
        return out
    for row in dets:
        cls_id = int(row[5])
        name = (names or {}).get(cls_id, str(cls_id))
        out.append(
            Detection(
                x1=float(row[0]),
                y1=float(row[1]),
                x2=float(row[2]),
                y2=float(row[3]),
                confidence=float(row[4]),
                class_id=cls_id,
                class_name=name,
            )
        )
    return out
