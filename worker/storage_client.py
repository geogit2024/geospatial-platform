"""
GCS Storage Client — Application Default Credentials via metadata server.

Download and upload use curl instead of the Python GCS SDK to avoid
SSLEOFError (OpenSSL 3.0 + Ubuntu 22.04 inside VPC).  curl uses libcurl
which handles GCP's network paths correctly.

get_cog_public_url() returns a permanent public URL — the processed bucket
is configured with allUsers:objectViewer so GeoServer can read COGs via
HTTP Range requests without expiring signed URLs.
"""

import json
import logging
import os
import subprocess
import time
from urllib.parse import quote

log = logging.getLogger("worker.storage")

from config import get_settings

settings = get_settings()

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


# ── curl helper (with retries) ────────────────────────────────────────────────

def _run_curl(args: list[str], description: str) -> None:
    """Run a curl command with retries. Raises RuntimeError on failure (no token leak)."""
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode == 0:
            return
        log.warning(
            "%s failed (attempt %d/%d) — curl exit %d  stderr: %s",
            description, attempt, max_retries,
            result.returncode, result.stderr.strip()[:200],
        )
        if attempt < max_retries:
            time.sleep(2 * attempt)
    raise RuntimeError(
        f"{description} failed after {max_retries} attempts (curl exit {result.returncode})"
    )


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
    _run_curl(
        ["curl", "-fL", "--retry", "3", "--retry-connrefused",
         "-H", f"Authorization: Bearer {token}",
         "-o", local_path, url],
        f"GCS download gs://{bucket}/{key}",
    )
    size = os.path.getsize(local_path)
    if size == 0:
        raise RuntimeError(f"GCS download produced empty file: gs://{bucket}/{key}")
    log.info("Downloaded gs://%s/%s → %s (%d bytes)", bucket, key, local_path, size)


# ── Upload ───────────────────────────────────────────────────────────────────

def upload_to_bucket(local_path: str, bucket: str, key: str) -> None:
    """Upload a local file to a GCS bucket using curl."""
    token = _get_access_token()
    encoded_key = quote(key, safe="")
    url = (
        f"https://storage.googleapis.com/upload/storage/v1"
        f"/b/{bucket}/o?uploadType=media&name={encoded_key}"
    )
    _run_curl(
        ["curl", "-fL", "--retry", "3", "--retry-connrefused",
         "-X", "POST",
         "-H", f"Authorization: Bearer {token}",
         "-H", "Content-Type: image/tiff",
         "--data-binary", f"@{local_path}", url],
        f"GCS upload gs://{bucket}/{key}",
    )


# ── Public URL (permanent, no expiry) ────────────────────────────────────────

def get_cog_public_url(bucket: str, key: str) -> str:
    """
    Return the permanent public HTTPS URL for a COG in the processed bucket.

    The processed bucket has allUsers:objectViewer — GeoServer reads COGs via
    HTTP Range requests using this URL.  No expiry, no signed-URL renewal needed.
    """
    encoded_key = quote(key, safe="/")
    return f"https://storage.googleapis.com/{bucket}/{encoded_key}"
