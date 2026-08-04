"""ROI zone CRUD + live detection ingest / WebSocket."""

from __future__ import annotations

import uuid
from time import time_ns
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import accept_websocket_api_key, require_auth
from app.database import get_db
from app.models import Camera, RoiZone
from app.ws_hub import detection_hub

router = APIRouter(
    tags=["stream", "roi"],
    dependencies=[Depends(require_auth)],
)
ws_router = APIRouter(tags=["stream"])


class RoiZoneCreate(BaseModel):
    camera_id: uuid.UUID | None = None
    camera_name: str | None = None
    name: str = Field(..., min_length=1, max_length=120)
    points: list[list[float]] = Field(..., min_length=3)
    color: str = "#ef4444"
    max_allowed_objects: int = 0
    forbidden_classes: list[str] | None = ["person"]
    loitering_seconds: int = Field(default=0, ge=0)
    is_active: bool = True


class RoiZoneRead(BaseModel):
    id: uuid.UUID
    camera_id: uuid.UUID | None
    name: str
    points: list[list[float]]
    color: str
    max_allowed_objects: int
    forbidden_classes: list[str] | None
    loitering_seconds: int = 0
    is_active: bool

    model_config = {"from_attributes": True}


class DetectionBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    class_id: int
    class_name: str
    track_id: int | None = None


class ZoneOccupancySnapshot(BaseModel):
    zone_name: str
    count: int = 0
    max_allowed: int = 0
    occupancy_pct: float = 0.0
    over_capacity: bool = False
    track_ids: list[int] = Field(default_factory=list)
    loitering_seconds: int = 0
    max_dwell_seconds: float = 0.0
    loitering_active: bool = False


class DetectionFrame(BaseModel):
    camera_id: uuid.UUID | None = None
    camera_name: str = "demo-camera"
    frame_index: int = 0
    captured_at_ms: int = Field(..., ge=0)
    sent_at_ms: int | None = Field(default=None, ge=0)
    source_position_ms: float | None = Field(default=None, ge=0)
    width: int
    height: int
    infer_ms: float | None = None
    boxes: list[DetectionBox] = Field(default_factory=list)
    zone_alerts: list[str] = Field(default_factory=list)
    zone_occupancy: list[ZoneOccupancySnapshot] = Field(default_factory=list)


def _resolve_camera_id(db: Session, camera_id: uuid.UUID | None, camera_name: str | None) -> uuid.UUID | None:
    if camera_id:
        if not db.get(Camera, camera_id):
            raise HTTPException(404, "camera_id not found")
        return camera_id
    if camera_name:
        cam = db.query(Camera).filter(Camera.name == camera_name).first()
        if cam is None:
            cam = Camera(name=camera_name, source_url="file://demo", location="ui")
            db.add(cam)
            db.flush()
        return cam.id
    return None


@router.get("/roi-zones", response_model=list[RoiZoneRead])
def list_zones(camera_name: str | None = None, db: Session = Depends(get_db)) -> list[RoiZone]:
    q = db.query(RoiZone).order_by(RoiZone.created_at.desc())
    if camera_name:
        cam = db.query(Camera).filter(Camera.name == camera_name).first()
        if not cam:
            return []
        q = q.filter(RoiZone.camera_id == cam.id)
    return q.all()


@router.post("/roi-zones", response_model=RoiZoneRead, status_code=201)
def create_zone(payload: RoiZoneCreate, db: Session = Depends(get_db)) -> RoiZone:
    camera_id = _resolve_camera_id(db, payload.camera_id, payload.camera_name)
    zone = RoiZone(
        camera_id=camera_id,
        name=payload.name,
        points=payload.points,
        color=payload.color,
        max_allowed_objects=payload.max_allowed_objects,
        forbidden_classes=payload.forbidden_classes,
        loitering_seconds=payload.loitering_seconds,
        is_active=payload.is_active,
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


@router.delete("/roi-zones/{zone_id}", status_code=204)
def delete_zone(zone_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    zone = db.get(RoiZone, zone_id)
    if not zone:
        raise HTTPException(404, "Zone not found")
    db.delete(zone)
    db.commit()


_detection_camera_ids: dict[str, uuid.UUID] = {}


def _detection_camera_id(payload: DetectionFrame, db: Session) -> uuid.UUID:
    if payload.camera_id:
        if not db.get(Camera, payload.camera_id):
            raise HTTPException(404, "camera_id not found")
        _detection_camera_ids[payload.camera_name] = payload.camera_id
        return payload.camera_id
    cached = _detection_camera_ids.get(payload.camera_name)
    if cached:
        return cached

    camera = db.query(Camera).filter(Camera.name == payload.camera_name).first()
    if camera is None:
        camera = Camera(
            name=payload.camera_name,
            # Matches scripts/publish-demo-mediamtx.ps1 default path /cam1
            source_url="rtsp://127.0.0.1:8554/cam1",
            location="engine",
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)
    _detection_camera_ids[payload.camera_name] = camera.id
    return camera.id


@router.post("/detections")
async def ingest_detections(
    payload: DetectionFrame,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Engine pushes frame detections; fan-out to dashboard WebSocket clients."""
    data = payload.model_dump()
    data["camera_id"] = str(_detection_camera_id(payload, db))
    data["received_at_ms"] = time_ns() // 1_000_000
    sent = await detection_hub.broadcast(data)
    return {
        "ok": True,
        "clients": sent,
        "camera_id": data["camera_id"],
        "received_at_ms": data["received_at_ms"],
    }


@router.get("/detections/latest")
def latest_detections() -> dict[str, Any]:
    return detection_hub.latest or {"boxes": [], "width": 0, "height": 0}


@ws_router.websocket("/ws/detections")
async def ws_detections(websocket: WebSocket) -> None:
    await accept_websocket_api_key(websocket)
    await detection_hub.connect(websocket)
    try:
        while True:
            # Keep-alive / ignore client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        await detection_hub.disconnect(websocket)
    except Exception:  # noqa: BLE001
        await detection_hub.disconnect(websocket)
