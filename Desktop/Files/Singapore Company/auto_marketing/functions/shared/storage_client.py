from __future__ import annotations

import datetime

from google.cloud import storage

from shared.logger import get_logger

logger = get_logger("storage")

_client: storage.Client | None = None


def _get_client() -> storage.Client:
    global _client
    if _client is None:
        _client = storage.Client()
    return _client


def get_bucket(bucket_name: str) -> storage.Bucket:
    return _get_client().bucket(bucket_name)


def _resolve_blob_path(blob_path: str, tenant_id: str | None) -> str:
    if tenant_id is not None:
        if not tenant_id:
            raise ValueError("tenant_id must not be empty when provided")
        return f"tenants/{tenant_id}/{blob_path}"
    return blob_path


def upload_bytes(
    bucket_name: str,
    blob_path: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    *,
    tenant_id: str | None = None,
) -> str:
    resolved = _resolve_blob_path(blob_path, tenant_id)
    bucket = get_bucket(bucket_name)
    blob = bucket.blob(resolved)
    blob.upload_from_string(data, content_type=content_type)
    gs_path = f"gs://{bucket_name}/{resolved}"
    logger.info("storage.upload", extra={"path": gs_path, "size": len(data)})
    return gs_path


def download_bytes(
    bucket_name: str, blob_path: str, *, tenant_id: str | None = None
) -> bytes:
    resolved = _resolve_blob_path(blob_path, tenant_id)
    bucket = get_bucket(bucket_name)
    blob = bucket.blob(resolved)
    data = blob.download_as_bytes()
    logger.info(
        "storage.download",
        extra={"path": f"gs://{bucket_name}/{resolved}", "size": len(data)},
    )
    return data


def generate_signed_url(
    bucket_name: str,
    blob_path: str,
    expiry_hours: int = 168,
    method: str = "GET",
    *,
    tenant_id: str | None = None,
) -> str:
    resolved = _resolve_blob_path(blob_path, tenant_id)
    bucket = get_bucket(bucket_name)
    blob = bucket.blob(resolved)
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(hours=expiry_hours),
        method=method,
    )
    logger.info(
        "storage.signed_url",
        extra={"path": f"gs://{bucket_name}/{resolved}", "expiry_hours": expiry_hours},
    )
    return url


def delete_blob(
    bucket_name: str, blob_path: str, *, tenant_id: str | None = None
) -> None:
    resolved = _resolve_blob_path(blob_path, tenant_id)
    bucket = get_bucket(bucket_name)
    blob = bucket.blob(resolved)
    blob.delete()
    logger.info("storage.delete", extra={"path": f"gs://{bucket_name}/{resolved}"})
