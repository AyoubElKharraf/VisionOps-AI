"""Camera CRUD routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_auth, require_roles
from app.database import get_db
from app.models import Camera, UserRole
from app.schemas import CameraCreate, CameraRead, CameraUpdate

router = APIRouter(
    prefix="/cameras",
    tags=["cameras"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[CameraRead])
def list_cameras(
    active_only: bool = False,
    db: Session = Depends(get_db),
) -> list[Camera]:
    q = db.query(Camera).order_by(Camera.created_at.desc())
    if active_only:
        q = q.filter(Camera.is_active.is_(True))
    return q.all()


@router.post("", response_model=CameraRead, status_code=201)
def create_camera(
    payload: CameraCreate,
    _: object = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
) -> Camera:
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


@router.patch("/{camera_id}", response_model=CameraRead)
def update_camera(
    camera_id: uuid.UUID,
    payload: CameraUpdate,
    _: object = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
) -> Camera:
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] != cam.name:
        clash = db.query(Camera).filter(Camera.name == data["name"]).first()
        if clash:
            raise HTTPException(status_code=409, detail=f"Camera '{data['name']}' already exists")

    for key, value in data.items():
        setattr(cam, key, value)

    db.commit()
    db.refresh(cam)
    return cam


@router.delete("/{camera_id}", status_code=204)
def delete_camera(
    camera_id: uuid.UUID,
    _: object = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
) -> None:
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    db.delete(cam)
    db.commit()
