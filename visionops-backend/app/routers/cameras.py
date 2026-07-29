"""Camera CRUD routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.models import Camera
from app.schemas import CameraCreate, CameraRead

router = APIRouter(
    prefix="/cameras",
    tags=["cameras"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=list[CameraRead])
def list_cameras(db: Session = Depends(get_db)) -> list[Camera]:
    return db.query(Camera).order_by(Camera.created_at.desc()).all()


@router.post("", response_model=CameraRead, status_code=201)
def create_camera(payload: CameraCreate, db: Session = Depends(get_db)) -> Camera:
    existing = db.query(Camera).filter(Camera.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Camera '{payload.name}' already exists")
    cam = Camera(
        name=payload.name,
        source_url=payload.source_url,
        location=payload.location,
        is_active=payload.is_active,
    )
    db.add(cam)
    db.commit()
    db.refresh(cam)
    return cam


@router.get("/{camera_id}", response_model=CameraRead)
def get_camera(camera_id: uuid.UUID, db: Session = Depends(get_db)) -> Camera:
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    return cam
