"""Pydantic request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import AlertStatus, AlertType


class CameraCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    source_url: str = Field(..., min_length=1, max_length=512)
    location: str | None = None
    is_active: bool = True


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    source_url: str | None = Field(default=None, min_length=1, max_length=512)
    location: str | None = None
    is_active: bool | None = None


class CameraRead(BaseModel):
    id: uuid.UUID
    name: str
    source_url: str
    location: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertCreate(BaseModel):
    camera_id: uuid.UUID | None = None
    camera_name: str | None = Field(default=None, description="Resolve or auto-create camera by name")
    alert_type: AlertType
    zone_name: str | None = None
    class_name: str | None = None
    track_id: int | None = None
    confidence: float | None = None
    message: str
    metadata: dict[str, Any] | None = None
    source_video_path: str | None = None
    frame_index: int | None = None
    # Optional JPEG snapshot as base64 (no data: prefix)
    snapshot_base64: str | None = None
    enqueue_media: bool = True


class AlertRead(BaseModel):
    id: uuid.UUID
    camera_id: uuid.UUID | None
    camera_name: str | None = None
    alert_type: AlertType
    status: AlertStatus
    zone_name: str | None
    class_name: str | None
    track_id: int | None
    confidence: float | None
    message: str
    metadata_json: dict[str, Any] | None
    source_video_path: str | None
    frame_index: int | None
    snapshot_object_key: str | None
    clip_object_key: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    snapshot_url: str | None = None
    clip_url: str | None = None

    model_config = {"from_attributes": True}
