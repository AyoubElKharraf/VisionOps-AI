"""VisionOps AI — application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "VisionOps AI Backend"
    api_prefix: str = "/api/v1"
    # Empty = auth disabled (local/CI). Set VISIONOPS_API_KEY to enforce X-API-Key.
    visionops_api_key: str = ""
    # Human JWT sessions (dashboard). Leave empty to disable JWT login.
    visionops_jwt_secret: str = ""
    visionops_jwt_expire_minutes: int = 480
    # Bootstrap admin created on startup when JWT is enabled and no users exist.
    visionops_admin_username: str = "admin"
    visionops_admin_password: str = "visionops-admin"
    visionops_admin_full_name: str = "VisionOps Admin"
    database_url: str = "postgresql://visionops:visionops_secret@localhost:5434/visionops_db"

    celery_broker_url: str = "redis://localhost:6380/0"
    celery_result_backend: str = "redis://localhost:6380/1"

    minio_endpoint: str = "localhost:9001"
    # Browser-facing host:port for presigned URLs (defaults to minio_endpoint).
    # In Docker set MINIO_ENDPOINT=minio:9000 and MINIO_PUBLIC_ENDPOINT=127.0.0.1:9001
    minio_public_endpoint: str = ""
    minio_root_user: str = "visionops_minio"
    minio_root_password: str = "visionops_minio_secret"
    minio_bucket: str = "visionops-media"
    minio_secure: bool = False
    minio_region: str = "us-east-1"

    # Default clip window around alert (seconds)
    alert_clip_pre_seconds: float = 2.0
    alert_clip_post_seconds: float = 3.0

    # Notifications (empty = channel disabled)
    notify_webhook_url: str = ""
    notify_slack_webhook_url: str = ""
    notify_email_to: str = ""
    notify_smtp_host: str = ""
    notify_smtp_port: int = 587
    notify_smtp_user: str = ""
    notify_smtp_password: str = ""
    notify_smtp_from: str = "visionops@localhost"
    notify_smtp_use_tls: bool = True
    # Comma-separated: created,acknowledged,assigned,resolved,reopened,commented — or "all"
    notify_events: str = "created,resolved"
    # Optional link base for notification bodies (e.g. http://127.0.0.1:3000/alerts)
    notify_dashboard_base_url: str = "http://127.0.0.1:3000/alerts"

    # Retention / storage quotas
    retention_enabled: bool = True
    # Delete alert media older than N days (0 = skip age-based media purge)
    retention_media_days: int = 30
    # Delete resolved alert rows (+ media) older than N days (0 = keep forever)
    retention_resolved_alert_days: int = 90
    # Soft bucket quota in megabytes (0 = unlimited). Oldest objects purged first when exceeded.
    retention_bucket_quota_mb: int = 5120
    # Celery Beat interval for automatic runs
    retention_interval_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
