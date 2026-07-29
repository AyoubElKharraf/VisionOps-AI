"""Alert routes — create event, list, enqueue media processing."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.minio_client import ensure_bucket, presigned_get_url
from app.models import Alert, AlertStatus, Camera
from app.schemas import AlertCreate, AlertRead
from app.tasks import process_alert_media

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(require_api_key)],
)


def _resolve_camera(db: Session, payload: AlertCreate) -> uuid.UUID | None:
    if payload.camera_id:
        cam = db.get(Camera, payload.camera_id)
        if not cam:
            raise HTTPException(status_code=404, detail="camera_id not found")
        return cam.id
    if payload.camera_name:
        cam = db.query(Camera).filter(Camera.name == payload.camera_name).first()
        if cam is None:
            cam = Camera(
                name=payload.camera_name,
                source_url=payload.source_video_path or "file://demo",
                location="auto",
            )
            db.add(cam)
            db.flush()
        return cam.id
    return None


def _to_read(alert: Alert) -> AlertRead:
    data = AlertRead.model_validate(alert)
    data.snapshot_url = presigned_get_url(alert.snapshot_object_key) if alert.snapshot_object_key else None
    data.clip_url = presigned_get_url(alert.clip_object_key) if alert.clip_object_key else None
    return data


@router.post("", response_model=AlertRead, status_code=201)
def create_alert(payload: AlertCreate, db: Session = Depends(get_db)) -> AlertRead:
    ensure_bucket()
    camera_id = _resolve_camera(db, payload)

    alert = Alert(
        camera_id=camera_id,
        alert_type=payload.alert_type,
        status=AlertStatus.pending,
        zone_name=payload.zone_name,
        class_name=payload.class_name,
        track_id=payload.track_id,
        confidence=payload.confidence,
        message=payload.message,
        metadata_json=payload.metadata,
        source_video_path=payload.source_video_path,
        frame_index=payload.frame_index,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    if payload.enqueue_media and (payload.snapshot_base64 or payload.source_video_path):
        process_alert_media.delay(str(alert.id), payload.snapshot_base64)

    return _to_read(alert)


@router.get("", response_model=list[AlertRead])
def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    status: AlertStatus | None = None,
    db: Session = Depends(get_db),
) -> list[AlertRead]:
    q = db.query(Alert).order_by(Alert.created_at.desc())
    if status is not None:
        q = q.filter(Alert.status == status)
    return [_to_read(a) for a in q.limit(limit).all()]


@router.get("/{alert_id}", response_model=AlertRead)
def get_alert(alert_id: uuid.UUID, db: Session = Depends(get_db)) -> AlertRead:
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _to_read(alert)


@router.post("/{alert_id}/reprocess", response_model=AlertRead)
def reprocess_alert(alert_id: uuid.UUID, db: Session = Depends(get_db)) -> AlertRead:
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = AlertStatus.pending
    alert.error_message = None
    db.commit()
    db.refresh(alert)
    process_alert_media.delay(str(alert.id), None)
    return _to_read(alert)
