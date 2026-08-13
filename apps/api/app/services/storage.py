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
