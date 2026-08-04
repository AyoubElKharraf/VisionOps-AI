"""Model registry — versioned inference weights in MinIO."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import Principal, require_auth, require_roles
from app.database import get_db
from app.minio_client import delete_object, download_object_bytes, presigned_get_url, upload_bytes
from app.models import ModelArtifact, ModelFormat, ModelRole, UserRole
from app.schemas import ModelActiveMap, ModelArtifactRead

router = APIRouter(
    prefix="/models",
    tags=["models"],
    dependencies=[Depends(require_auth)],
)

_SAFE_VERSION = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._+-]{1,120}$")
_MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # 512 MiB


def _infer_format(filename: str, explicit: str | None) -> ModelFormat:
    if explicit:
        try:
            return ModelFormat(explicit.lower())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="format must be onnx or pytorch") from exc
    lower = filename.lower()
    if lower.endswith(".onnx"):
        return ModelFormat.onnx
    if lower.endswith((".pt", ".pth", ".weights")):
        return ModelFormat.pytorch
    raise HTTPException(
        status_code=400,
        detail="Cannot infer format; pass format=onnx|pytorch or use .onnx/.pt extension",
    )


def _to_read(row: ModelArtifact, *, include_url: bool = False) -> ModelArtifactRead:
    data = ModelArtifactRead.model_validate(row)
    if include_url:
        data.download_url = presigned_get_url(row.object_key)
    return data


@router.get("", response_model=list[ModelArtifactRead])
def list_models(
    role: ModelRole | None = None,
    db: Session = Depends(get_db),
) -> list[ModelArtifactRead]:
    q = db.query(ModelArtifact).order_by(ModelArtifact.created_at.desc())
    if role is not None:
        q = q.filter(ModelArtifact.role == role)
    return [_to_read(row) for row in q.all()]


@router.get("/active", response_model=ModelActiveMap)
def list_active_models(db: Session = Depends(get_db)) -> ModelActiveMap:
    rows = db.query(ModelArtifact).filter(ModelArtifact.is_active.is_(True)).all()
    by_role = {row.role: row for row in rows}
    return ModelActiveMap(
        detector=_to_read(by_role[ModelRole.detector]) if ModelRole.detector in by_role else None,
        ppe=_to_read(by_role[ModelRole.ppe]) if ModelRole.ppe in by_role else None,
    )


@router.post("", response_model=ModelArtifactRead, status_code=201)
async def upload_model(
    file: UploadFile = File(...),
    name: str = Form(...),
    version: str = Form(...),
    role: str = Form(...),
    format: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    activate: bool = Form(default=False),
    principal: Principal = Depends(require_auth),
    _: object = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
) -> ModelArtifactRead:
    name = name.strip()
    version = version.strip()
    if not _SAFE_NAME.match(name):
        raise HTTPException(status_code=400, detail="Invalid name (use letters, digits, ._+-)")
    if not _SAFE_VERSION.match(version):
        raise HTTPException(status_code=400, detail="Invalid version (use letters, digits, ._+-)")
    try:
        role_enum = ModelRole(role.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="role must be detector or ppe") from exc

    filename = PurePosixPath(file.filename or "weights.bin").name
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=400, detail="Missing filename")
    fmt = _infer_format(filename, format)

    clash = (
        db.query(ModelArtifact)
        .filter(
            ModelArtifact.role == role_enum,
            ModelArtifact.name == name,
            ModelArtifact.version == version,
        )
        .first()
    )
    if clash:
        raise HTTPException(
            status_code=409,
            detail=f"Model {name}@{version} already exists for role {role_enum.value}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 512 MiB limit")

    artifact_id = uuid.uuid4()
    object_key = f"models/{role_enum.value}/{artifact_id}/{filename}"
    digest = hashlib.sha256(data).hexdigest()
    content_type = (
        "application/octet-stream"
        if fmt == ModelFormat.pytorch
        else "application/onnx"
    )
    try:
        upload_bytes(object_key, data, content_type)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"MinIO upload failed: {exc}") from exc

    created_by = principal.subject if principal else None

    now = datetime.now(timezone.utc)
    row = ModelArtifact(
        id=artifact_id,
        name=name,
        version=version,
        role=role_enum,
        format=fmt,
        filename=filename,
        object_key=object_key,
        sha256=digest,
        size_bytes=len(data),
        is_active=False,
        notes=(notes or "").strip() or None,
        created_by=created_by,
        created_at=now,
    )
    db.add(row)
    db.flush()

    if activate:
        _activate_row(db, row, now=now)

    db.commit()
    db.refresh(row)
    return _to_read(row)


def _activate_row(db: Session, row: ModelArtifact, *, now: datetime | None = None) -> None:
    stamp = now or datetime.now(timezone.utc)
    peers = (
        db.query(ModelArtifact)
        .filter(ModelArtifact.role == row.role, ModelArtifact.is_active.is_(True))
        .all()
    )
    for peer in peers:
        if peer.id != row.id:
            peer.is_active = False
            peer.activated_at = None
    row.is_active = True
    row.activated_at = stamp


@router.post("/{model_id}/activate", response_model=ModelArtifactRead)
def activate_model(
    model_id: uuid.UUID,
    _: object = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
) -> ModelArtifactRead:
    row = db.get(ModelArtifact, model_id)
    if not row:
        raise HTTPException(status_code=404, detail="Model not found")
    _activate_row(db, row)
    db.commit()
    db.refresh(row)
    return _to_read(row)


@router.get("/{model_id}/download")
def download_model(
    model_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Response:
    row = db.get(ModelArtifact, model_id)
    if not row:
        raise HTTPException(status_code=404, detail="Model not found")
    data = download_object_bytes(row.object_key)
    if data is None:
        raise HTTPException(status_code=404, detail="Object missing in MinIO")
    media = "application/onnx" if row.format == ModelFormat.onnx else "application/octet-stream"
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{row.filename}"'},
    )


@router.delete("/{model_id}", status_code=204)
def delete_model(
    model_id: uuid.UUID,
    _: object = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(ModelArtifact, model_id)
    if not row:
        raise HTTPException(status_code=404, detail="Model not found")
    if row.is_active:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete the active model; activate another version first",
        )
    key = row.object_key
    db.delete(row)
    db.commit()
    delete_object(key)
