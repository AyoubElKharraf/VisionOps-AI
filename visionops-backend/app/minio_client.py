"""MinIO object storage helpers."""

from __future__ import annotations

import io
from datetime import timedelta
from functools import lru_cache

from minio import Minio
from minio.error import S3Error

from app.config import get_settings


@lru_cache
def get_minio_client() -> Minio:
    settings = get_settings()
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=settings.minio_secure,
    )


def ensure_bucket() -> str:
    settings = get_settings()
    client = get_minio_client()
    bucket = settings.minio_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    return bucket


def upload_bytes(object_key: str, data: bytes, content_type: str) -> str:
    bucket = ensure_bucket()
    client = get_minio_client()
    client.put_object(
        bucket,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return object_key


def upload_file(object_key: str, file_path: str, content_type: str) -> str:
    bucket = ensure_bucket()
    client = get_minio_client()
    client.fput_object(bucket, object_key, file_path, content_type=content_type)
    return object_key


def presigned_get_url(object_key: str, expires_hours: int = 24) -> str | None:
    if not object_key:
        return None
    try:
        client = get_minio_client()
        settings = get_settings()
        return client.presigned_get_object(
            settings.minio_bucket,
            object_key,
            expires=timedelta(hours=expires_hours),
        )
    except S3Error:
        return None
