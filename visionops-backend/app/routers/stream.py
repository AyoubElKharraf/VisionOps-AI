"""ROI zone CRUD + live detection ingest / WebSocket."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Camera, RoiZone
from app.ws_hub import detection_hub

router = APIRouter(tags=["stream", "roi"])


class RoiZoneCreate(BaseModel):
    camera_id: uuid.UUID | None = None
    camera_name: str | None = None
    name: str = Field(..., min_length=1, max_length=120)
    points: list[list[float]] = Field(..., min_length=3)
    color: str = "#ef4444"
    max_allowed_objects: int = 0
    forbidden_classes: list[str] | None = ["person"]
    is_active: bool = True


class RoiZoneRead(BaseModel):
    id: uuid.UUID
    camera_id: uuid.UUID | None
    name: str
    points: list[list[float]]
    color: str
    max_allowed_objects: int
    forbidden_classes: list[str] | None
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


class DetectionFrame(BaseModel):
    camera_name: str = "demo-camera"
    frame_index: int = 0
    width: int
    height: int
    infer_ms: float | None = None
    boxes: list[DetectionBox] = Field(default_factory=list)
    zone_alerts: list[str] = Field(default_factory=list)


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


@router.post("/detections")
async def ingest_detections(payload: DetectionFrame) -> dict[str, Any]:
    """Engine pushes frame detections; fan-out to dashboard WebSocket clients."""
    data = payload.model_dump()
    sent = await detection_hub.broadcast(data)
    return {"ok": True, "clients": sent}


@router.get("/detections/latest")
def latest_detections() -> dict[str, Any]:
    return detection_hub.latest or {"boxes": [], "width": 0, "height": 0}


@router.websocket("/ws/detections")
async def ws_detections(websocket: WebSocket) -> None:
    await detection_hub.connect(websocket)
    try:
        while True:
            # Keep-alive / ignore client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        await detection_hub.disconnect(websocket)
    except Exception:  # noqa: BLE001
        await detection_hub.disconnect(websocket)
