"""
VisionOps AI — Spatial ROI / Tripwire geometry engine (Phase 2).

Uses Shapely for polygon intrusion and line-crossing detection.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
from pydantic import BaseModel, Field, field_validator
from shapely.geometry import LineString, Point, Polygon, box as shapely_box
from shapely.geometry.base import BaseGeometry


class CrossingDirection(str, Enum):
    IN = "IN"
    OUT = "OUT"
    BOTH = "BOTH"


class ZoneROI(BaseModel):
    """Polygonal region of interest with intrusion / occupancy / loitering rules."""

    name: str
    points: list[tuple[float, float]] = Field(..., min_length=3)
    max_allowed_objects: int = Field(default=0, ge=0)
    forbidden_classes: list[str] = Field(default_factory=lambda: ["person"])
    loitering_seconds: int = Field(default=0, ge=0)
    schedule_enabled: bool = False
    schedule_start: str = "00:00"
    schedule_end: str = "23:59"
    schedule_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    schedule_timezone: str = "UTC"
    require_hardhat: bool = False

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


def _parse_hhmm(value: str) -> int:
    """Return minutes since midnight for HH:MM."""
    parts = (value or "00:00").strip().split(":")
    if len(parts) != 2:
        return 0
    try:
        hour = max(0, min(23, int(parts[0])))
        minute = max(0, min(59, int(parts[1])))
    except ValueError:
        return 0
    return hour * 60 + minute


def is_within_schedule(zone: ZoneROI, when: datetime | None = None) -> bool:
    """
    True when rules should fire.

    schedule_enabled=False => always active.
    Days use Python weekday() (Mon=0 … Sun=6). Overnight windows
    (e.g. 22:00–06:00) are supported.
    """
    if not zone.schedule_enabled:
        return True

    clock = when or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    try:
        tz = ZoneInfo(zone.schedule_timezone or "UTC")
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    local = clock.astimezone(tz)

    days = zone.schedule_days if zone.schedule_days is not None else list(range(7))
    if days and local.weekday() not in {int(d) for d in days}:
        return False

    start = _parse_hhmm(zone.schedule_start)
    end = _parse_hhmm(zone.schedule_end)
    minutes = local.hour * 60 + local.minute
    if start == end:
        return True
    if start < end:
        return start <= minutes < end
    # Overnight window
    return minutes >= start or minutes < end


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
    reason: str = "intrusion"  # intrusion | over_capacity
    occupancy_pct: float = 0.0


class ZoneOccupancy(BaseModel):
    """Live person occupancy for one ROI polygon."""

    zone_name: str
    count: int
    max_allowed: int
    occupancy_pct: float
    over_capacity: bool
    track_ids: list[int] = Field(default_factory=list)
    loitering_seconds: int = 0
    max_dwell_seconds: float = 0.0
    loitering_active: bool = False
    schedule_active: bool = True


class LoiteringEvent(BaseModel):
    zone_name: str
    track_id: int
    dwell_seconds: float
    threshold_seconds: int
    class_name: str = "person"
    message: str


class PPEViolation(BaseModel):
    zone_name: str
    track_id: int | None
    class_name: str = "person"
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
        # (zone_name, track_id) -> first monotonic timestamp inside zone
        self._zone_enter_ts: dict[tuple[str, int], float] = {}
        self._loiter_fired: set[tuple[str, int]] = set()
        self._last_dwell_now: float | None = None

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

    def record_tracks(self, detections: Iterable[Detection]) -> None:
        """Record trajectories for detections already identified by a tracker."""
        active: dict[int, tuple[float, float]] = {}
        for det in detections:
            if det.track_id is None:
                continue
            center = det.center
            active[det.track_id] = center
            self._trajectories[det.track_id].append(center)
        self._prev_centers = active

    def _detections_inside(
        self,
        zone: ZoneROI,
        detections: Iterable[Detection],
        *,
        use_foot_point: bool = True,
        use_bbox_intersection: bool = True,
    ) -> list[Detection]:
        poly = zone.to_polygon()
        inside: list[Detection] = []
        for det in detections:
            foot = Point(det.foot_point if use_foot_point else det.center)
            intersects = False
            if use_foot_point and poly.contains(foot):
                intersects = True
            elif use_bbox_intersection and poly.intersects(det.as_polygon()):
                intersects = True
            if intersects:
                inside.append(det)
        return inside

    @staticmethod
    def _person_track_ids(inside: Iterable[Detection]) -> list[int]:
        """Unique person identities inside a zone (prefer ByteTrack ids)."""
        seen: set[int] = set()
        ordered: list[int] = []
        anon = -1
        for det in inside:
            if det.class_name != "person":
                continue
            if det.track_id is not None:
                tid = int(det.track_id)
            else:
                tid = anon
                anon -= 1
            if tid in seen:
                continue
            seen.add(tid)
            ordered.append(tid)
        return ordered

    @staticmethod
    def _occupancy_pct(count: int, max_allowed: int) -> float:
        if max_allowed > 0:
            return round(100.0 * count / max_allowed, 1)
        return 100.0 if count > 0 else 0.0

    def zone_occupancy(
        self,
        detections: Iterable[Detection],
        *,
        use_foot_point: bool = True,
        use_bbox_intersection: bool = True,
        now: float | None = None,
        wall_clock: datetime | None = None,
    ) -> list[ZoneOccupancy]:
        dets = list(detections)
        clock = now if now is not None else self._last_dwell_now
        snapshots: list[ZoneOccupancy] = []
        for zone in self.zones:
            schedule_active = is_within_schedule(zone, wall_clock)
            inside = self._detections_inside(
                zone,
                dets,
                use_foot_point=use_foot_point,
                use_bbox_intersection=use_bbox_intersection,
            )
            track_ids = self._person_track_ids(inside)
            count = len(track_ids)
            max_allowed = zone.max_allowed_objects
            threshold = int(zone.loitering_seconds or 0)
            max_dwell = 0.0
            loitering_active = False
            if schedule_active and clock is not None and threshold > 0:
                for tid in track_ids:
                    if tid < 0:
                        continue
                    key = (zone.name, tid)
                    entered = self._zone_enter_ts.get(key)
                    if entered is None:
                        continue
                    dwell = max(0.0, clock - entered)
                    max_dwell = max(max_dwell, dwell)
                    if dwell >= threshold:
                        loitering_active = True
            snapshots.append(
                ZoneOccupancy(
                    zone_name=zone.name,
                    count=count,
                    max_allowed=max_allowed,
                    occupancy_pct=self._occupancy_pct(count, max_allowed),
                    over_capacity=schedule_active and max_allowed > 0 and count > max_allowed,
                    track_ids=track_ids,
                    loitering_seconds=threshold,
                    max_dwell_seconds=round(max_dwell, 1),
                    loitering_active=loitering_active,
                    schedule_active=schedule_active,
                )
            )
        return snapshots

    def check_loitering(
        self,
        detections: Iterable[Detection],
        *,
        now: float,
        use_foot_point: bool = True,
        use_bbox_intersection: bool = True,
        wall_clock: datetime | None = None,
    ) -> list[LoiteringEvent]:
        """
        Alert when a tracked person remains continuously inside a zone
        for at least ``zone.loitering_seconds`` (0 disables).
        """
        self._last_dwell_now = now
        events: list[LoiteringEvent] = []
        dets = list(detections)
        active_keys: set[tuple[str, int]] = set()

        for zone in self.zones:
            threshold = int(zone.loitering_seconds or 0)
            if threshold <= 0:
                continue
            if not is_within_schedule(zone, wall_clock):
                # Outside window: drop dwell state for this zone
                for key in list(self._zone_enter_ts):
                    if key[0] == zone.name:
                        self._zone_enter_ts.pop(key, None)
                        self._loiter_fired.discard(key)
                continue
            inside = self._detections_inside(
                zone,
                dets,
                use_foot_point=use_foot_point,
                use_bbox_intersection=use_bbox_intersection,
            )
            for det in inside:
                if det.class_name != "person" or det.track_id is None:
                    continue
                tid = int(det.track_id)
                if tid < 0:
                    continue
                key = (zone.name, tid)
                active_keys.add(key)
                if key not in self._zone_enter_ts:
                    self._zone_enter_ts[key] = now
                dwell = now - self._zone_enter_ts[key]
                if dwell >= threshold and key not in self._loiter_fired:
                    self._loiter_fired.add(key)
                    events.append(
                        LoiteringEvent(
                            zone_name=zone.name,
                            track_id=tid,
                            dwell_seconds=round(dwell, 1),
                            threshold_seconds=threshold,
                            class_name=det.class_name,
                            message=(
                                f"ALERTE LOITERING : [{zone.name}] track={tid} "
                                f"dwell={dwell:.0f}s (seuil {threshold}s)"
                            ),
                        )
                    )

        stale = [
            key
            for key in list(self._zone_enter_ts)
            if key[0] in {z.name for z in self.zones if (z.loitering_seconds or 0) > 0}
            and key not in active_keys
        ]
        for key in stale:
            self._zone_enter_ts.pop(key, None)
            self._loiter_fired.discard(key)

        return events

    def check_zone_intrusion(
        self,
        detections: Iterable[Detection],
        *,
        use_foot_point: bool = True,
        use_bbox_intersection: bool = True,
        wall_clock: datetime | None = None,
    ) -> list[ZoneAlert]:
        """
        Emit alerts for forbidden-class intrusion and/or over-capacity.

        Occupancy mode: max_allowed_objects > 0 and empty forbidden_classes.
        Intrusion mode: forbidden_classes lists banned labels (classic max=0).
        Outside an enabled schedule window, no alerts are emitted.
        """
        alerts: list[ZoneAlert] = []
        dets = list(detections)

        for zone in self.zones:
            if not is_within_schedule(zone, wall_clock):
                continue
            inside = self._detections_inside(
                zone,
                dets,
                use_foot_point=use_foot_point,
                use_bbox_intersection=use_bbox_intersection,
            )
            track_ids = self._person_track_ids(inside)
            person_count = len(track_ids)
            max_allowed = zone.max_allowed_objects
            pct = self._occupancy_pct(person_count, max_allowed)

            forbidden = zone.forbidden_classes or []
            forbidden_hit = any(d.class_name in forbidden for d in inside)
            over_capacity = max_allowed > 0 and person_count > max_allowed

            if over_capacity:
                alerts.append(
                    ZoneAlert(
                        zone_name=zone.name,
                        object_count=person_count,
                        max_allowed=max_allowed,
                        offending_classes=["person"],
                        reason="over_capacity",
                        occupancy_pct=pct,
                        message=(
                            f"ALERTE CAPACITÉ : [{zone.name}] {person_count}/{max_allowed} "
                            f"({pct:.0f}%)"
                        ),
                    )
                )
            elif forbidden_hit:
                offending = sorted({d.class_name for d in inside if d.class_name in forbidden})
                alerts.append(
                    ZoneAlert(
                        zone_name=zone.name,
                        object_count=person_count if "person" in forbidden else len(inside),
                        max_allowed=max_allowed,
                        offending_classes=offending,
                        reason="intrusion",
                        occupancy_pct=pct,
                        message=(
                            f"ALERTE ROI : Intrusion détectée ! [{zone.name}] "
                            f"count={person_count if 'person' in forbidden else len(inside)}"
                        ),
                    )
                )
        return alerts

    def check_ppe_violations(
        self,
        detections: Iterable[Detection],
        hardhats: Iterable[Detection],
        *,
        wall_clock: datetime | None = None,
        use_foot_point: bool = True,
        use_bbox_intersection: bool = True,
    ) -> list[PPEViolation]:
        """Persons inside require_hardhat zones without an overlapping hardhat."""
        from ppe_checker import person_has_hardhat

        hats = list(hardhats)
        dets = list(detections)
        events: list[PPEViolation] = []
        for zone in self.zones:
            if not zone.require_hardhat:
                continue
            if not is_within_schedule(zone, wall_clock):
                continue
            inside = self._detections_inside(
                zone,
                dets,
                use_foot_point=use_foot_point,
                use_bbox_intersection=use_bbox_intersection,
            )
            for det in inside:
                if det.class_name != "person":
                    continue
                if person_has_hardhat(det, hats):
                    continue
                tid = det.track_id
                events.append(
                    PPEViolation(
                        zone_name=zone.name,
                        track_id=tid,
                        class_name=det.class_name,
                        message=(
                            f"ALERTE PPE : [{zone.name}] personne sans casque"
                            + (f" track={tid}" if tid is not None else "")
                        ),
                    )
                )
        return events

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
                loitering_seconds=max(0, int(item.get("loitering_seconds", 0) or 0)),
                schedule_enabled=bool(item.get("schedule_enabled", False)),
                schedule_start=str(item.get("schedule_start") or "00:00"),
                schedule_end=str(item.get("schedule_end") or "23:59"),
                schedule_days=[
                    int(day)
                    for day in (item.get("schedule_days") or [0, 1, 2, 3, 4, 5, 6])
                ],
                schedule_timezone=str(item.get("schedule_timezone") or "UTC"),
                require_hardhat=bool(item.get("require_hardhat", False)),
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
