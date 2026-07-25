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
    database_url: str = "postgresql://visionops:visionops_secret@localhost:5434/visionops_db"

    celery_broker_url: str = "redis://localhost:6380/0"
    celery_result_backend: str = "redis://localhost:6380/1"

    minio_endpoint: str = "localhost:9001"
    minio_root_user: str = "visionops_minio"
    minio_root_password: str = "visionops_minio_secret"
    minio_bucket: str = "visionops-media"
    minio_secure: bool = False

    # Default clip window around alert (seconds)
    alert_clip_pre_seconds: float = 2.0
    alert_clip_post_seconds: float = 3.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
