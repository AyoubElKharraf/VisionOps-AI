"""Pydantic request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import AlertStatus, AlertType, IncidentStatus, UserRole


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


class AlertEventRead(BaseModel):
    id: uuid.UUID
    alert_id: uuid.UUID
    event_type: str
    actor: str | None
    message: str
    metadata_json: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertRead(BaseModel):
    id: uuid.UUID
    camera_id: uuid.UUID | None
    camera_name: str | None = None
    alert_type: AlertType
    status: AlertStatus
    incident_status: IncidentStatus | str = IncidentStatus.open
    zone_name: str | None
    class_name: str | None
    track_id: int | None
    confidence: float | None
    message: str
    metadata_json: dict[str, Any] | None
    assigned_to: str | None = None
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None
    source_video_path: str | None
    frame_index: int | None
    snapshot_object_key: str | None
    clip_object_key: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    snapshot_url: str | None = None
    clip_url: str | None = None
    events: list[AlertEventRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AlertActorNote(BaseModel):
    actor: str | None = Field(default="operator", max_length=120)
    note: str | None = Field(default=None, max_length=2000)


class AlertAssign(BaseModel):
    assignee: str = Field(..., min_length=1, max_length=120)
    actor: str | None = Field(default="operator", max_length=120)
    note: str | None = Field(default=None, max_length=2000)


class AlertComment(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    actor: str | None = Field(default="operator", max_length=120)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserRead"


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=80)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=160)
    role: UserRole = UserRole.operator
    is_active: bool = True


class UserRead(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthStatus(BaseModel):
    auth_enforced: bool
    api_key_enabled: bool
    jwt_enabled: bool

