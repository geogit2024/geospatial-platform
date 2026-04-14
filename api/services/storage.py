"""
GCS Storage Service — Application Default Credentials (ADC).

No JSON keys. No GOOGLE_APPLICATION_CREDENTIALS.
Cloud Run provides identity automatically via metadata server.
Locally: run `gcloud auth application-default login` once.
"""

import datetime

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


def generate_upload_url(key: str, content_type: str = "image/tiff") -> str:
    """Generate a v4 signed PUT URL so browsers can upload directly to GCS."""
    credentials, _ = default()
    credentials.refresh(google_requests.Request())

    client = get_gcs()
    blob = client.bucket(settings.storage_bucket_raw).blob(key)

    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=settings.signed_url_expiry_seconds),
        method="PUT",
        content_type=content_type,
        service_account_email=credentials.service_account_email,
        access_token=credentials.token,
    )
    return url


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
