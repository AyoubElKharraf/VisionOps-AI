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


def delete_object(object_key: str) -> bool:
    """Remove one object. Missing keys are treated as success."""
    if not object_key:
        return False
    settings = get_settings()
    client = get_minio_client()
    try:
        client.remove_object(settings.minio_bucket, object_key)
        return True
    except S3Error as exc:
        if getattr(exc, "code", "") in {"NoSuchKey", "NoSuchObject"}:
            return True
        logger.warning("Failed to delete %s: %s", object_key, exc)
        return False
    except (MinioException, Urllib3HTTPError, OSError) as exc:
        logger.warning("Failed to delete %s: %s", object_key, exc)
        return False


def download_object_bytes(object_key: str) -> bytes | None:
    """Fetch object bytes from MinIO. Returns None if missing/unreachable."""
    if not object_key:
        return None
    settings = get_settings()
    client = get_minio_client()
    try:
        response = client.get_object(settings.minio_bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
    except S3Error as exc:
        if getattr(exc, "code", "") in {"NoSuchKey", "NoSuchObject"}:
            return None
        logger.warning("download failed for %s: %s", object_key, exc)
        return None
    except (MinioException, Urllib3HTTPError, OSError) as exc:
        logger.warning("download failed for %s: %s", object_key, exc)
        return None


def list_objects(prefix: str = "alerts/") -> list[dict]:
    """Return [{key, size, last_modified}] for objects under prefix."""
    settings = get_settings()
    client = get_minio_client()
    out: list[dict] = []
    try:
        for obj in client.list_objects(settings.minio_bucket, prefix=prefix, recursive=True):
            if obj.is_dir:
                continue
            out.append(
                {
                    "key": obj.object_name,
                    "size": int(obj.size or 0),
                    "last_modified": obj.last_modified,
                }
            )
    except (S3Error, MinioException, Urllib3HTTPError, OSError) as exc:
        logger.warning("list_objects failed: %s", exc)
    return out


def bucket_usage_bytes(prefix: str = "alerts/") -> int:
    return sum(int(item["size"]) for item in list_objects(prefix))
