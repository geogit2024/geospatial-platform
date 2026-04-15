"""
GCS Storage Client — Application Default Credentials via metadata server.

Download and upload use curl instead of the Python GCS SDK to avoid
SSLEOFError (OpenSSL 3.0 + Ubuntu 22.04 inside VPC).  curl uses libcurl
which handles GCP's network paths correctly.

Signed URLs (get_cog_public_url) still use the SDK because they call
iam.googleapis.com (signBlob), which is not affected by the SSL issue.
"""

import datetime
import json
import os
import subprocess
import time
from urllib.parse import quote

from google.cloud import storage
from google.auth import default
from google.auth.transport import requests as google_requests

from config import get_settings

settings = get_settings()

_gcs_client = None
_token_cache: dict = {"token": None, "expires": 0.0}

METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1"
    "/instance/service-accounts/default/token"
)


# ── Access token (cached) ────────────────────────────────────────────────────

def _get_access_token() -> str:
    """Return a valid GCP access token from the metadata server (cached)."""
    now = time.monotonic()
    if _token_cache["token"] and now < _token_cache["expires"] - 60:
        return _token_cache["token"]

    result = subprocess.run(
        ["curl", "-sf", "-H", "Metadata-Flavor: Google", METADATA_TOKEN_URL],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    _token_cache["token"] = data["access_token"]
    _token_cache["expires"] = now + data["expires_in"]
    return _token_cache["token"]


# ── GCS client (for signed URLs only) ────────────────────────────────────────

def get_gcs() -> storage.Client:
    global _gcs_client
    if _gcs_client is None:
        _gcs_client = storage.Client()
    return _gcs_client


# ── Download ─────────────────────────────────────────────────────────────────

def download_from_bucket(bucket: str, key: str, local_path: str) -> None:
    """Download a GCS object to a local file using curl."""
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    token = _get_access_token()
    encoded_key = quote(key, safe="")
    url = (
        f"https://storage.googleapis.com/download/storage/v1"
        f"/b/{bucket}/o/{encoded_key}?alt=media"
    )
    subprocess.run(
        [
            "curl", "-sfL",
            "-H", f"Authorization: Bearer {token}",
            "-o", local_path,
            url,
        ],
        check=True,
    )


# ── Upload ───────────────────────────────────────────────────────────────────

def upload_to_bucket(local_path: str, bucket: str, key: str) -> None:
    """Upload a local file to a GCS bucket using curl."""
    token = _get_access_token()
    encoded_key = quote(key, safe="")
    url = (
        f"https://storage.googleapis.com/upload/storage/v1"
        f"/b/{bucket}/o?uploadType=media&name={encoded_key}"
    )
    subprocess.run(
        [
            "curl", "-sfL", "-X", "POST",
            "-H", f"Authorization: Bearer {token}",
            "-H", "Content-Type: image/tiff",
            "--data-binary", f"@{local_path}",
            url,
        ],
        check=True,
    )


# ── Signed URL (for GeoServer to read COG) ───────────────────────────────────

def get_cog_public_url(bucket: str, key: str) -> str:
    """
    Return a v4 signed GET URL (7-day TTL) for GeoServer to read the COG.

    Uses ADC identity to sign via iam.googleapis.com — not affected by the
    storage.googleapis.com SSL issue.
    """
    credentials, _ = default()
    credentials.refresh(google_requests.Request())

    blob = get_gcs().bucket(bucket).blob(key)
    return blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(days=7),
        method="GET",
        service_account_email=credentials.service_account_email,
        access_token=credentials.token,
    )
