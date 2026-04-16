"""
GCS Storage Client — ADC on Cloud Run.

Primary path uses Google Cloud Storage SDK with retries.
Fallback path uses curl + metadata token when SDK path fails transiently.

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

from google.api_core.retry import Retry
from google.cloud import storage
import requests

log = logging.getLogger("worker.storage")

from config import get_settings

settings = get_settings()

_token_cache: dict = {"token": None, "expires": 0.0}
_gcs_client: storage.Client | None = None
_GCS_DOWNLOAD_RETRY = Retry(initial=1.0, maximum=10.0, multiplier=2.0, deadline=240.0)
_GCS_UPLOAD_RETRY = Retry(initial=1.0, maximum=10.0, multiplier=2.0, deadline=240.0)

_CURL_CONNECT_TIMEOUT = int(os.getenv("GCS_CURL_CONNECT_TIMEOUT", "15"))
_CURL_DOWNLOAD_MAX_TIME = int(os.getenv("GCS_CURL_DOWNLOAD_MAX_TIME", "240"))
_CURL_UPLOAD_MAX_TIME = int(os.getenv("GCS_CURL_UPLOAD_MAX_TIME", "300"))
_CURL_RETRIES = int(os.getenv("GCS_CURL_RETRIES", "5"))
_REQ_CONNECT_TIMEOUT = int(os.getenv("GCS_HTTP_CONNECT_TIMEOUT", "10"))
_REQ_READ_TIMEOUT = int(os.getenv("GCS_HTTP_READ_TIMEOUT", "120"))
_REQ_RETRIES = int(os.getenv("GCS_HTTP_RETRIES", "5"))

METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1"
    "/instance/service-accounts/default/token"
)


def _get_gcs() -> storage.Client:
    global _gcs_client
    if _gcs_client is None:
        _gcs_client = storage.Client()
    return _gcs_client


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

def _run_curl(args: list[str], description: str, max_retries: int = 3) -> None:
    """Run a curl command with retries. Raises RuntimeError on failure (no token leak)."""
    for attempt in range(1, max_retries + 1):
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode == 0:
            return
        log.warning(
            "%s failed (attempt %d/%d) — curl exit %d\n  stdout: %s\n  stderr: %s",
            description, attempt, max_retries,
            result.returncode,
            result.stdout.strip()[:500],
            result.stderr.strip()[:500],
        )
        if attempt < max_retries:
            time.sleep(min(attempt, 3))
    raise RuntimeError(
        f"{description} failed after {max_retries} attempts (curl exit {result.returncode})"
    )


def _download_via_http(bucket: str, key: str, local_path: str, token: str) -> None:
    encoded_key = quote(key, safe="")
    url = f"https://storage.googleapis.com/download/storage/v1/b/{bucket}/o/{encoded_key}?alt=media"
    headers = {"Authorization": f"Bearer {token}"}
    last_exc: Exception | None = None

    for attempt in range(1, _REQ_RETRIES + 1):
        try:
            with requests.get(
                url,
                headers=headers,
                stream=True,
                timeout=(_REQ_CONNECT_TIMEOUT, _REQ_READ_TIMEOUT),
            ) as resp:
                resp.raise_for_status()
                with open(local_path, "wb") as out:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            out.write(chunk)
            return
        except Exception as exc:
            last_exc = exc
            log.warning(
                "GCS HTTP download failed (attempt %d/%d) gs://%s/%s: %s",
                attempt, _REQ_RETRIES, bucket, key, exc,
            )
            if attempt < _REQ_RETRIES:
                time.sleep(min(attempt, 3))

    raise RuntimeError(f"GCS HTTP download failed for gs://{bucket}/{key}: {last_exc}")


def _upload_via_http(local_path: str, bucket: str, key: str, token: str) -> None:
    encoded_key = quote(key, safe="")
    url = f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o?uploadType=media&name={encoded_key}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "image/tiff",
    }
    last_exc: Exception | None = None

    for attempt in range(1, _REQ_RETRIES + 1):
        try:
            with open(local_path, "rb") as fh:
                resp = requests.post(
                    url,
                    headers=headers,
                    data=fh,
                    timeout=(_REQ_CONNECT_TIMEOUT, _REQ_READ_TIMEOUT),
                )
            resp.raise_for_status()
            return
        except Exception as exc:
            last_exc = exc
            log.warning(
                "GCS HTTP upload failed (attempt %d/%d) gs://%s/%s: %s",
                attempt, _REQ_RETRIES, bucket, key, exc,
            )
            if attempt < _REQ_RETRIES:
                time.sleep(min(attempt, 3))

    raise RuntimeError(f"GCS HTTP upload failed for gs://{bucket}/{key}: {last_exc}")


# ── Download ─────────────────────────────────────────────────────────────────

def download_from_bucket(bucket: str, key: str, local_path: str) -> None:
    """Download a GCS object to a local file using HTTP token auth (fallback: curl, SDK)."""
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    token = _get_access_token()
    try:
        _download_via_http(bucket, key, local_path, token)
        size = os.path.getsize(local_path)
        if size == 0:
            raise RuntimeError(f"GCS HTTP download produced empty file: gs://{bucket}/{key}")
        log.info("Downloaded via HTTP gs://%s/%s -> %s (%d bytes)", bucket, key, local_path, size)
        return
    except Exception as exc:
        log.warning("GCS HTTP download failed for gs://%s/%s (fallback to curl): %s", bucket, key, exc)

    encoded_key = quote(key, safe="/")
    urls = [
        f"https://storage.googleapis.com/{bucket}/{encoded_key}",
        f"https://{bucket}.storage.googleapis.com/{encoded_key}",
        f"https://storage.cloud.google.com/{bucket}/{encoded_key}",
    ]
    try:
        last_exc: Exception | None = None
        for url in urls:
            try:
                _run_curl(
                    [
                        "curl", "-fsSL",
                        "--http1.1",
                        "--tlsv1.2",
                        "--connect-timeout", str(_CURL_CONNECT_TIMEOUT),
                        "--max-time", str(_CURL_DOWNLOAD_MAX_TIME),
                        "--retry", "0",
                        "--retry-all-errors",
                        "-H", f"Authorization: Bearer {token}",
                        "-o", local_path, url,
                    ],
                    f"GCS download gs://{bucket}/{key} via {url}",
                    max_retries=_CURL_RETRIES,
                )
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        size = os.path.getsize(local_path)
        if size == 0:
            raise RuntimeError(f"GCS curl download produced empty file: gs://{bucket}/{key}")
        log.info("Downloaded via curl gs://%s/%s → %s (%d bytes)", bucket, key, local_path, size)
        return
    except Exception as exc:
        log.warning(
            "GCS curl download failed for gs://%s/%s (fallback to SDK): %s",
            bucket, key, exc,
        )

    blob = _get_gcs().bucket(bucket).blob(key)
    blob.download_to_filename(local_path, retry=_GCS_DOWNLOAD_RETRY, timeout=180)
    size = os.path.getsize(local_path)
    if size == 0:
        raise RuntimeError(f"GCS SDK download produced empty file: gs://{bucket}/{key}")
    log.info("Downloaded via SDK gs://%s/%s → %s (%d bytes)", bucket, key, local_path, size)


# ── Upload ───────────────────────────────────────────────────────────────────

def upload_to_bucket(local_path: str, bucket: str, key: str) -> None:
    """Upload local file to GCS using HTTP token auth (fallback: curl, SDK)."""
    token = _get_access_token()
    try:
        _upload_via_http(local_path, bucket, key, token)
        log.info("Uploaded via HTTP gs://%s/%s", bucket, key)
        return
    except Exception as exc:
        log.warning("GCS HTTP upload failed for gs://%s/%s (fallback to curl): %s", bucket, key, exc)

    encoded_key = quote(key, safe="/")
    urls = [
        f"https://storage.googleapis.com/{bucket}/{encoded_key}",
        f"https://{bucket}.storage.googleapis.com/{encoded_key}",
    ]
    try:
        last_exc: Exception | None = None
        for url in urls:
            try:
                _run_curl(
                    [
                        "curl", "-fsSL",
                        "--http1.1",
                        "--tlsv1.2",
                        "--connect-timeout", str(_CURL_CONNECT_TIMEOUT),
                        "--max-time", str(_CURL_UPLOAD_MAX_TIME),
                        "--retry", "0",
                        "--retry-all-errors",
                        "-X", "PUT",
                        "-H", f"Authorization: Bearer {token}",
                        "-H", "Content-Type: image/tiff",
                        "--data-binary", f"@{local_path}", url,
                    ],
                    f"GCS upload gs://{bucket}/{key} via {url}",
                    max_retries=_CURL_RETRIES,
                )
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        log.info("Uploaded via curl gs://%s/%s", bucket, key)
        return
    except Exception as exc:
        log.warning(
            "GCS curl upload failed for gs://%s/%s (fallback to SDK): %s",
            bucket, key, exc,
        )

    blob = _get_gcs().bucket(bucket).blob(key)
    blob.upload_from_filename(
        local_path,
        content_type="image/tiff",
        retry=_GCS_UPLOAD_RETRY,
        timeout=240,
    )
    log.info("Uploaded via SDK gs://%s/%s", bucket, key)


# ── Public URL (permanent, no expiry) ────────────────────────────────────────

def get_cog_public_url(bucket: str, key: str) -> str:
    """
    Return the permanent public HTTPS URL for a COG in the processed bucket.

    The processed bucket has allUsers:objectViewer — GeoServer reads COGs via
    HTTP Range requests using this URL.  No expiry, no signed-URL renewal needed.
    """
    encoded_key = quote(key, safe="/")
    return f"https://storage.googleapis.com/{bucket}/{encoded_key}"
