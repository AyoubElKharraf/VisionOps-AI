"""SQLAlchemy ORM models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AlertType(str, enum.Enum):
    roi_intrusion = "roi_intrusion"
    tripwire = "tripwire"
    loitering = "loitering"
    ppe_violation = "ppe_violation"
    custom = "custom"


class AlertStatus(str, enum.Enum):
    """Media pipeline status (Celery snapshot/clip)."""

    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class IncidentStatus(str, enum.Enum):
    """Operator workflow status for an alert/incident."""

    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"


class AlertEventType(str, enum.Enum):
    created = "created"
    acknowledged = "acknowledged"
    assigned = "assigned"
    commented = "commented"
    resolved = "resolved"
    reopened = "reopened"
    reprocessed = "reprocessed"


class UserRole(str, enum.Enum):
    admin = "admin"
    operator = "operator"


class ModelRole(str, enum.Enum):
    """Inference slot a registered weight file can fill."""

    detector = "detector"
    ppe = "ppe"


class ModelFormat(str, enum.Enum):
    onnx = "onnx"
    pytorch = "pytorch"


class User(Base):
    """Human dashboard user authenticated via JWT."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        default=UserRole.operator,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    source_url: Mapped[str] = mapped_column(String(512), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    alerts: Mapped[list[Alert]] = relationship(back_populates="camera", cascade="all, delete-orphan")
    zones: Mapped[list[RoiZone]] = relationship(back_populates="camera", cascade="all, delete-orphan")


class RoiZone(Base):
    """Polygon ROI stored for a camera (Phase 4 editor)."""

    __tablename__ = "roi_zones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    points: Mapped[list] = mapped_column(JSONB, nullable=False)  # [[x,y], ...] normalized 0-1 or pixels
    color: Mapped[str] = mapped_column(String(32), default="#ef4444")
    max_allowed_objects: Mapped[int] = mapped_column(Integer, default=0)
    forbidden_classes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    loitering_seconds: Mapped[int] = mapped_column(Integer, default=0)
    schedule_enabled: Mapped[bool] = mapped_column(default=False)
    schedule_start: Mapped[str] = mapped_column(String(5), default="00:00")
    schedule_end: Mapped[str] = mapped_column(String(5), default="23:59")
    schedule_days: Mapped[list] = mapped_column(JSONB, default=lambda: [0, 1, 2, 3, 4, 5, 6])
    schedule_timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    require_hardhat: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    camera: Mapped[Camera | None] = relationship(back_populates="zones")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True
    )
    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType, name="alert_type"), nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, name="alert_status"), default=AlertStatus.pending, nullable=False
    )
    incident_status: Mapped[str] = mapped_column(
        String(32), default=IncidentStatus.open.value, nullable=False
    )
    zone_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    class_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    assigned_to: Mapped[str | None] = mapped_column(String(120), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Local source hints for Celery workers
    source_video_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    frame_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    snapshot_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    clip_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    camera: Mapped[Camera | None] = relationship(back_populates="alerts")
    events: Mapped[list[AlertEvent]] = relationship(
        back_populates="alert",
        cascade="all, delete-orphan",
        order_by="AlertEvent.created_at",
    )


class AlertEvent(Base):
    """Immutable timeline for incident workflow actions."""

    __tablename__ = "alert_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    alert: Mapped[Alert] = relationship(back_populates="events")


class ModelArtifact(Base):
    """Versioned inference weight stored in MinIO (model registry)."""

    __tablename__ = "model_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[ModelRole] = mapped_column(
        Enum(ModelRole, name="model_role"), nullable=False, index=True
    )
    format: Mapped[ModelFormat] = mapped_column(
        Enum(ModelFormat, name="model_format"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
