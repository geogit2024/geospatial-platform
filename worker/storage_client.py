"""
GCS Storage Client — Application Default Credentials (ADC).

No JSON keys. No GOOGLE_APPLICATION_CREDENTIALS.
Cloud Run automatically provides identity via the metadata server.
Locally: run `gcloud auth application-default login` once.
"""

import datetime
import os

from google.cloud import storage
from google.auth import default
from google.auth.transport import requests as google_requests

from config import get_settings

settings = get_settings()

_gcs_client = None


def get_gcs() -> storage.Client:
    global _gcs_client
    if _gcs_client is None:
        # ADC: Cloud Run uses metadata server, local uses gcloud ADC
        _gcs_client = storage.Client()
    return _gcs_client


def download_from_bucket(bucket: str, key: str, local_path: str) -> None:
    """Download object from GCS to local path."""
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    client = get_gcs()
    blob = client.bucket(bucket).blob(key)
    blob.download_to_filename(local_path)


def upload_to_bucket(local_path: str, bucket: str, key: str) -> None:
    """Upload local file to GCS bucket."""
    client = get_gcs()
    blob = client.bucket(bucket).blob(key)
    blob.upload_from_filename(local_path)


def get_cog_public_url(bucket: str, key: str) -> str:
    """
    Return a signed URL (v4) for GeoServer to read the COG via HTTPS.

    Uses ADC identity to sign — no JSON key required.
    Expiration: 7 days (604800s, maximum for v4 signed URLs).
    """
    credentials, _ = default()
    credentials.refresh(google_requests.Request())

    client = get_gcs()
    blob = client.bucket(bucket).blob(key)

    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(days=7),
        method="GET",
        service_account_email=credentials.service_account_email,
        access_token=credentials.token,
    )
    return url
