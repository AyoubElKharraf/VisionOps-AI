"""Alert routes — create event, list, enqueue media processing, incident lifecycle."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import require_auth, require_roles
from app.database import get_db
from app.metrics import record_alert_created
from app.minio_client import delete_object, download_object_bytes, presigned_get_url
from app.models import (
    Alert,
    AlertEvent,
    AlertEventType,
    AlertStatus,
    Camera,
    IncidentStatus,
    UserRole,
)
from app.notifications import enqueue_alert_notification
from app.schemas import (
    AlertActorNote,
    AlertAssign,
    AlertComment,
    AlertCreate,
    AlertEventRead,
    AlertRead,
)
from app.tasks import process_alert_media

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(require_auth)],
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


def _append_event(
    db: Session,
    alert: Alert,
    event_type: AlertEventType | str,
    message: str,
    actor: str | None = None,
    metadata: dict | None = None,
) -> AlertEvent:
    event = AlertEvent(
        alert_id=alert.id,
        event_type=event_type.value if isinstance(event_type, AlertEventType) else event_type,
        actor=actor,
        message=message,
        metadata_json=metadata,
    )
    db.add(event)
    return event


def _to_read(alert: Alert, *, include_events: bool = False) -> AlertRead:
    data = AlertRead.model_validate(alert)
    data.camera_name = alert.camera.name if alert.camera else None
    data.snapshot_url = (
        presigned_get_url(alert.snapshot_object_key) if alert.snapshot_object_key else None
    )
    data.clip_url = presigned_get_url(alert.clip_object_key) if alert.clip_object_key else None
    if include_events:
        data.events = [AlertEventRead.model_validate(e) for e in (alert.events or [])]
    else:
        data.events = []
    return data


def _get_alert(db: Session, alert_id: uuid.UUID, *, with_events: bool = False) -> Alert:
    q = db.query(Alert).options(joinedload(Alert.camera))
    if with_events:
        q = q.options(joinedload(Alert.events))
    alert = q.filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("", response_model=AlertRead, status_code=201)
def create_alert(payload: AlertCreate, db: Session = Depends(get_db)) -> AlertRead:
    camera_id = _resolve_camera(db, payload)

    alert = Alert(
        camera_id=camera_id,
        alert_type=payload.alert_type,
        status=AlertStatus.pending,
        incident_status=IncidentStatus.open.value,
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
    db.flush()
    _append_event(
        db,
        alert,
        AlertEventType.created,
        "Incident opened",
        actor="system",
        metadata={"alert_type": payload.alert_type.value},
    )
    db.commit()
    alert_type = (
        payload.alert_type.value
        if hasattr(payload.alert_type, "value")
        else str(payload.alert_type)
    )
    record_alert_created(alert_type)
    alert = _get_alert(db, alert.id, with_events=True)
    enqueue_alert_notification(alert, event="created", actor="system")

    if payload.enqueue_media and (payload.snapshot_base64 or payload.source_video_path):
        process_alert_media.delay(str(alert.id), payload.snapshot_base64)

    return _to_read(alert, include_events=True)


@router.get("", response_model=list[AlertRead])
def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    status: AlertStatus | None = None,
    incident_status: IncidentStatus | None = None,
    camera_id: uuid.UUID | None = None,
    camera_name: str | None = None,
    db: Session = Depends(get_db),
) -> list[AlertRead]:
    q = db.query(Alert).options(joinedload(Alert.camera)).order_by(Alert.created_at.desc())
    if status is not None:
        q = q.filter(Alert.status == status)
    if incident_status is not None:
        q = q.filter(Alert.incident_status == incident_status.value)
    if camera_id is not None:
        q = q.filter(Alert.camera_id == camera_id)
    elif camera_name:
        cam = db.query(Camera).filter(Camera.name == camera_name).first()
        if cam is None:
            return []
        q = q.filter(Alert.camera_id == cam.id)
    return [_to_read(a) for a in q.limit(limit).all()]


@router.get("/{alert_id}", response_model=AlertRead)
def get_alert(alert_id: uuid.UUID, db: Session = Depends(get_db)) -> AlertRead:
    alert = _get_alert(db, alert_id, with_events=True)
    return _to_read(alert, include_events=True)


@router.get("/{alert_id}/export")
def export_alert_pack(alert_id: uuid.UUID, db: Session = Depends(get_db)) -> StreamingResponse:
    """Download a ZIP evidence pack: incident.json, timeline, snapshot, clip."""
    alert = _get_alert(db, alert_id, with_events=True)
    read = _to_read(alert, include_events=True)

    manifest = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "incident": json.loads(read.model_dump_json()),
        "files": [],
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        if alert.snapshot_object_key:
            snap = download_object_bytes(alert.snapshot_object_key)
            if snap:
                name = "snapshot.jpg"
                if "." in alert.snapshot_object_key.rsplit("/", 1)[-1]:
                    ext = alert.snapshot_object_key.rsplit(".", 1)[-1].lower()
                    if ext in {"jpg", "jpeg", "png", "webp"}:
                        name = f"snapshot.{ext if ext != 'jpeg' else 'jpg'}"
                zf.writestr(name, snap)
                manifest["files"].append(name)

        if alert.clip_object_key:
            clip = download_object_bytes(alert.clip_object_key)
            if clip:
                name = "clip.mp4"
                if "." in alert.clip_object_key.rsplit("/", 1)[-1]:
                    ext = alert.clip_object_key.rsplit(".", 1)[-1].lower()
                    if ext in {"mp4", "webm", "avi", "mkv"}:
                        name = f"clip.{ext}"
                zf.writestr(name, clip)
                manifest["files"].append(name)

        timeline = [
            {
                "event_type": e.event_type,
                "actor": e.actor,
                "message": e.message,
                "metadata": e.metadata_json,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in (alert.events or [])
        ]
        zf.writestr(
            "timeline.json",
            json.dumps(timeline, indent=2, default=str).encode("utf-8"),
        )
        manifest["files"].append("timeline.json")
        zf.writestr(
            "incident.json",
            json.dumps(manifest, indent=2, default=str).encode("utf-8"),
        )
        zf.writestr(
            "README.txt",
            (
                "VisionOps AI — incident evidence pack\n"
                f"Alert ID: {alert.id}\n"
                f"Type: {alert.alert_type.value if hasattr(alert.alert_type, 'value') else alert.alert_type}\n"
                f"Camera: {alert.camera.name if alert.camera else 'n/a'}\n"
                f"Message: {alert.message}\n"
                "Contents: incident.json, timeline.json, optional snapshot/clip media.\n"
            ).encode("utf-8"),
        )

    buffer.seek(0)
    filename = f"visionops-incident-{str(alert.id)[:8]}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{alert_id}", status_code=204)
def delete_alert(
    alert_id: uuid.UUID,
    _: object = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
) -> None:
    """Delete incident metadata, event timeline, and associated MinIO media."""
    alert = _get_alert(db, alert_id)
    if alert.snapshot_object_key:
        delete_object(alert.snapshot_object_key)
    if alert.clip_object_key:
        delete_object(alert.clip_object_key)
    db.delete(alert)
    db.commit()


@router.get("/{alert_id}/events", response_model=list[AlertEventRead])
def list_alert_events(alert_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AlertEventRead]:
    alert = _get_alert(db, alert_id, with_events=True)
    return [AlertEventRead.model_validate(e) for e in alert.events]


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
def acknowledge_alert(
    alert_id: uuid.UUID,
    payload: AlertActorNote,
    db: Session = Depends(get_db),
) -> AlertRead:
    alert = _get_alert(db, alert_id, with_events=True)
    if alert.incident_status == IncidentStatus.resolved.value:
        raise HTTPException(status_code=409, detail="Resolved incidents must be reopened first")

    actor = payload.actor or "operator"
    alert.incident_status = IncidentStatus.acknowledged.value
    alert.acknowledged_by = actor
    alert.acknowledged_at = datetime.now(timezone.utc)
    note = payload.note.strip() if payload.note else None
    _append_event(
        db,
        alert,
        AlertEventType.acknowledged,
        note or f"Acknowledged by {actor}",
        actor=actor,
    )
    db.commit()
    alert = _get_alert(db, alert_id, with_events=True)
    enqueue_alert_notification(alert, event="acknowledged", actor=actor, note=note)
    return _to_read(alert, include_events=True)


@router.post("/{alert_id}/assign", response_model=AlertRead)
def assign_alert(
    alert_id: uuid.UUID,
    payload: AlertAssign,
    db: Session = Depends(get_db),
) -> AlertRead:
    alert = _get_alert(db, alert_id, with_events=True)
    if alert.incident_status == IncidentStatus.resolved.value:
        raise HTTPException(status_code=409, detail="Resolved incidents must be reopened first")

    actor = payload.actor or "operator"
    alert.assigned_to = payload.assignee.strip()
    if alert.incident_status == IncidentStatus.open.value:
        alert.incident_status = IncidentStatus.acknowledged.value
        alert.acknowledged_by = actor
        alert.acknowledged_at = datetime.now(timezone.utc)

    message = payload.note.strip() if payload.note else f"Assigned to {alert.assigned_to}"
    _append_event(
        db,
        alert,
        AlertEventType.assigned,
        message,
        actor=actor,
        metadata={"assignee": alert.assigned_to},
    )
    db.commit()
    alert = _get_alert(db, alert_id, with_events=True)
    enqueue_alert_notification(alert, event="assigned", actor=actor, note=message)
    return _to_read(alert, include_events=True)


@router.post("/{alert_id}/resolve", response_model=AlertRead)
def resolve_alert(
    alert_id: uuid.UUID,
    payload: AlertActorNote,
    db: Session = Depends(get_db),
) -> AlertRead:
    alert = _get_alert(db, alert_id, with_events=True)
    actor = payload.actor or "operator"
    note = payload.note.strip() if payload.note else None
    alert.incident_status = IncidentStatus.resolved.value
    alert.resolved_by = actor
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolution_note = note
    _append_event(
        db,
        alert,
        AlertEventType.resolved,
        note or f"Resolved by {actor}",
        actor=actor,
    )
    db.commit()
    alert = _get_alert(db, alert_id, with_events=True)
    enqueue_alert_notification(alert, event="resolved", actor=actor, note=note)
    return _to_read(alert, include_events=True)


@router.post("/{alert_id}/reopen", response_model=AlertRead)
def reopen_alert(
    alert_id: uuid.UUID,
    payload: AlertActorNote,
    db: Session = Depends(get_db),
) -> AlertRead:
    alert = _get_alert(db, alert_id, with_events=True)
    actor = payload.actor or "operator"
    note = payload.note.strip() if payload.note else None
    alert.incident_status = IncidentStatus.open.value
    alert.resolved_by = None
    alert.resolved_at = None
    alert.resolution_note = None
    _append_event(
        db,
        alert,
        AlertEventType.reopened,
        note or f"Reopened by {actor}",
        actor=actor,
    )
    db.commit()
    alert = _get_alert(db, alert_id, with_events=True)
    enqueue_alert_notification(alert, event="reopened", actor=actor, note=note)
    return _to_read(alert, include_events=True)


@router.post("/{alert_id}/comments", response_model=AlertRead)
def comment_alert(
    alert_id: uuid.UUID,
    payload: AlertComment,
    db: Session = Depends(get_db),
) -> AlertRead:
    alert = _get_alert(db, alert_id, with_events=True)
    actor = payload.actor or "operator"
    _append_event(
        db,
        alert,
        AlertEventType.commented,
        payload.message.strip(),
        actor=actor,
    )
    db.commit()
    alert = _get_alert(db, alert_id, with_events=True)
    enqueue_alert_notification(
        alert, event="commented", actor=actor, note=payload.message.strip()
    )
    return _to_read(alert, include_events=True)


@router.post("/{alert_id}/reprocess", response_model=AlertRead)
def reprocess_alert(alert_id: uuid.UUID, db: Session = Depends(get_db)) -> AlertRead:
    alert = _get_alert(db, alert_id, with_events=True)
    alert.status = AlertStatus.pending
    alert.error_message = None
    _append_event(
        db,
        alert,
        AlertEventType.reprocessed,
        "Media reprocessing queued",
        actor="system",
    )
    db.commit()
    process_alert_media.delay(str(alert.id), None)
    alert = _get_alert(db, alert_id, with_events=True)
    return _to_read(alert, include_events=True)
