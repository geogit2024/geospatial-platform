import asyncio
import logging
import uuid
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession

from config import get_settings
from services.queue import get_redis

log = logging.getLogger("api.worker_job_trigger")
settings = get_settings()


def _run_worker_job_sync(reason: str) -> dict[str, Any] | None:
    if not settings.worker_job_trigger_enabled:
        return None

    project_id = (settings.worker_job_project_id or settings.gcp_project_id).strip()
    region = settings.worker_job_region.strip()
    job_name = settings.worker_job_name.strip()
    if not project_id or not region or not job_name:
        log.warning(
            "Worker job trigger skipped: project_id=%r region=%r job_name=%r",
            project_id,
            region,
            job_name,
        )
        return None

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    url = f"https://run.googleapis.com/v2/projects/{project_id}/locations/{region}/jobs/{job_name}:run"
    response = session.post(url, json={}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    log.info(
        "Triggered worker job %s/%s/%s reason=%s operation=%s",
        project_id,
        region,
        job_name,
        reason,
        payload.get("name"),
    )
    return payload


async def _acquire_trigger_lock(reason: str) -> str | None:
    if not settings.worker_job_trigger_lock_enabled:
        return ""

    token = uuid.uuid4().hex
    ttl = max(int(settings.worker_job_trigger_lock_ttl_seconds), 10)
    redis = await get_redis()
    acquired = await redis.set(settings.worker_job_trigger_lock_key, token, ex=ttl, nx=True)
    if acquired:
        log.info(
            "Acquired worker job trigger lock key=%s ttl=%ss reason=%s",
            settings.worker_job_trigger_lock_key,
            ttl,
            reason,
        )
        return token

    log.info(
        "Worker job trigger skipped because another trigger is active key=%s reason=%s",
        settings.worker_job_trigger_lock_key,
        reason,
    )
    return None


async def _release_trigger_lock(token: str | None) -> None:
    if not token or not settings.worker_job_trigger_lock_enabled:
        return

    redis = await get_redis()
    current = await redis.get(settings.worker_job_trigger_lock_key)
    if current == token:
        await redis.delete(settings.worker_job_trigger_lock_key)


async def trigger_worker_job_best_effort(reason: str) -> bool:
    if not settings.worker_job_trigger_enabled:
        return False

    lock_token = await _acquire_trigger_lock(reason)
    if lock_token is None:
        return False

    try:
        await asyncio.to_thread(_run_worker_job_sync, reason)
        return True
    except Exception as exc:
        await _release_trigger_lock(lock_token)
        # Queue persistence is the source of truth. Retry/manual requeue can still
        # pick up the message if this on-demand trigger fails.
        log.error("Worker job trigger failed after %s: %s", reason, exc, exc_info=True)
        return False
