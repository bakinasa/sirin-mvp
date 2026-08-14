"""MinIO helper for attachment uploads."""

from __future__ import annotations

import io
from functools import lru_cache

from minio import Minio

from app.config import get_settings


@lru_cache
def get_minio() -> Minio:
    settings = get_settings()
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket() -> None:
    settings = get_settings()
    client = get_minio()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def upload_bytes(object_name: str, data: bytes, content_type: str) -> str:
    ensure_bucket()
    settings = get_settings()
    client = get_minio()
    client.put_object(
        settings.minio_bucket,
        object_name,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return f"{settings.minio_public_url}/{settings.minio_bucket}/{object_name}"


def delete_object_by_url(file_path: str) -> None:
    """Best-effort delete of a stored original. Ignore missing objects."""
    if not file_path:
        return
    settings = get_settings()
    prefix = f"{settings.minio_public_url.rstrip('/')}/{settings.minio_bucket}/"
    object_name = file_path
    if file_path.startswith(prefix):
        object_name = file_path[len(prefix) :]
    elif f"/{settings.minio_bucket}/" in file_path:
        object_name = file_path.split(f"/{settings.minio_bucket}/", 1)[1]
    object_name = object_name.lstrip("/")
    if not object_name:
        return
    try:
        get_minio().remove_object(settings.minio_bucket, object_name)
    except Exception:
        return
