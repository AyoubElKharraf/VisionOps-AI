"""MinIO object storage helpers."""

from __future__ import annotations

import io
import logging
from datetime import timedelta
from functools import lru_cache

from minio import Minio
from minio.error import MinioException, S3Error
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_minio_client() -> Minio:
    """Internal client for put/get (Docker service hostname)."""
    settings = get_settings()
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=settings.minio_secure,
    )


@lru_cache
def get_minio_presign_client() -> Minio:
    """Sign browser URLs with the public Host (rewriting breaks SigV4)."""
    settings = get_settings()
    endpoint = (settings.minio_public_endpoint or settings.minio_endpoint).strip()
    return Minio(
        endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=settings.minio_secure,
        # Pinned so signing never calls the public endpoint, unreachable in Docker.
        region=settings.minio_region,
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
        settings = get_settings()
        return get_minio_presign_client().presigned_get_object(
            settings.minio_bucket,
            object_key,
            expires=timedelta(hours=expires_hours),
        )
    except (S3Error, MinioException, Urllib3HTTPError, OSError):
        logger.warning("Presign failed for %s", object_key, exc_info=True)
        return None
