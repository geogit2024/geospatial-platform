"""
GCS Storage Service — Application Default Credentials (ADC).

No JSON keys. No GOOGLE_APPLICATION_CREDENTIALS.
Cloud Run provides identity automatically via metadata server.
Locally: run `gcloud auth application-default login` once.
"""

import datetime
from typing import Any

from google.cloud import storage
from google.auth import default
from google.auth.transport import requests as google_requests

from config import get_settings

settings = get_settings()

_gcs_client = None


def get_gcs() -> storage.Client:
    global _gcs_client
    if _gcs_client is None:
        _gcs_client = storage.Client()
    return _gcs_client


def ensure_buckets() -> None:
    """No-op for GCS — buckets are pre-created via Console/Terraform.
    Kept for interface compatibility with the Railway/MinIO version.
    """
    pass


def generate_upload_url_for_bucket(
    *,
    bucket_name: str,
    key: str,
    content_type: str = "image/tiff",
    expires_in_seconds: int | None = None,
) -> str:
    """Generate a v4 signed PUT URL so browsers can upload directly to GCS."""
    credentials, _ = default()
    credentials.refresh(google_requests.Request())

    client = get_gcs()
    blob = client.bucket(bucket_name).blob(key)

    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(
            seconds=expires_in_seconds or settings.signed_url_expiry_seconds
        ),
        method="PUT",
        content_type=content_type,
        service_account_email=credentials.service_account_email,
        access_token=credentials.token,
    )
    return url


def generate_upload_url(key: str, content_type: str = "image/tiff") -> str:
    return generate_upload_url_for_bucket(
        bucket_name=settings.storage_bucket_raw,
        key=key,
        content_type=content_type,
        expires_in_seconds=settings.signed_url_expiry_seconds,
    )


def generate_download_url(bucket: str, key: str) -> str:
    """Generate a v4 signed GET URL for client download."""
    credentials, _ = default()
    credentials.refresh(google_requests.Request())

    client = get_gcs()
    blob = client.bucket(bucket).blob(key)

    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=settings.signed_url_expiry_seconds),
        method="GET",
        service_account_email=credentials.service_account_email,
        access_token=credentials.token,
    )
    return url


def _delete_object_if_exists(client: storage.Client, bucket_name: str, key: str | None) -> int:
    normalized = (key or "").strip()
    if not normalized:
        return 0

    blob = client.bucket(bucket_name).blob(normalized)
    if not blob.exists():
        return 0

    blob.delete()
    return 1


def _delete_by_prefix(client: storage.Client, bucket_name: str, prefix: str) -> int:
    deleted = 0
    for blob in client.list_blobs(bucket_name, prefix=prefix):
        blob.delete()
        deleted += 1
    return deleted


def _has_prefix_objects(client: storage.Client, bucket_name: str, prefix: str) -> bool:
    iterator = client.list_blobs(bucket_name, prefix=prefix, max_results=1)
    return next(iter(iterator), None) is not None


def delete_image_related_files(
    *,
    image_id: str,
    original_key: str | None,
    processed_key: str | None,
) -> dict[str, Any]:
    """
    Delete all storage objects related to an image/service.

    Strategy:
    - delete explicit keys from DB (original_key / processed_key)
    - delete every object under {image_id}/ prefix in raw and processed buckets
    - verify no object under that prefix remains
    """
    normalized_id = image_id.strip()
    if not normalized_id:
        raise ValueError("image_id is required for storage cleanup")

    prefix = f"{normalized_id}/"
    client = get_gcs()
    raw_bucket = settings.storage_bucket_raw
    processed_bucket = settings.storage_bucket_processed

    deleted_objects = 0
    deleted_objects += _delete_object_if_exists(client, raw_bucket, original_key)
    deleted_objects += _delete_object_if_exists(client, processed_bucket, processed_key)

    deleted_objects += _delete_by_prefix(client, raw_bucket, prefix)
    deleted_objects += _delete_by_prefix(client, processed_bucket, prefix)

    raw_remaining = _has_prefix_objects(client, raw_bucket, prefix)
    processed_remaining = _has_prefix_objects(client, processed_bucket, prefix)

    if raw_remaining or processed_remaining:
        raise RuntimeError(
            f"Incomplete storage cleanup for image_id={normalized_id} "
            f"(raw_remaining={raw_remaining}, processed_remaining={processed_remaining})"
        )

    return {
        "image_id": normalized_id,
        "prefix": prefix,
        "deleted_objects": deleted_objects,
        "raw_bucket": raw_bucket,
        "processed_bucket": processed_bucket,
    }
