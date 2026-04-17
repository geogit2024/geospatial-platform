"""
GDAL Worker — consumes Redis Streams, processes rasters, publishes to GeoServer.

Stream: image:uploaded  → audit + normalize raster → store COG → publish event
Stream: image:processed → publish to GeoServer → validate WMS → update DB
"""

import asyncio
import json
import logging
import os
import socket
import tempfile
import threading
import time
from contextlib import suppress
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
import redis.asyncio as aioredis
from sqlalchemy import update

from config import get_settings
from db_client import AsyncSessionLocal
from geoserver_client import GeoServerClient
from pipeline import (
    audit_raster,
    normalize_raster,
    get_raster_metadata,
    # backward-compat shims kept in pipeline.py
    reproject,
    build_overviews,
    to_cog,
)
from storage_client import download_from_bucket, get_cog_public_url, upload_to_bucket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("worker")

settings = get_settings()


def _build_redis_client() -> aioredis.Redis:
    return aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=30,
        retry_on_timeout=True,
        health_check_interval=30,
    )


# ─── DB helpers ────────────────────────────────────────────────────────────────

async def _update_image(image_id: str, **fields) -> None:
    from sqlalchemy import text
    async with AsyncSessionLocal() as session:
        if fields:
            set_clause = ", ".join(f"{k} = :{k}" for k in fields)
            sql = text(
                f"UPDATE images SET {set_clause}, updated_at = NOW() WHERE id = :image_id"
            )
        else:
            sql = text("UPDATE images SET updated_at = NOW() WHERE id = :image_id")
        await session.execute(sql, {"image_id": image_id, **fields})
        await session.commit()


async def _touch_image(image_id: str) -> None:
    await _update_image(image_id)


async def _get_image_runtime_state(image_id: str) -> Optional[dict]:
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        row = await session.execute(
            text(
                """
                SELECT status, updated_at, original_key, processed_key, filename
                FROM images
                WHERE id = :image_id
                """
            ),
            {"image_id": image_id},
        )
        record = row.first()

    if not record:
        return None

    return {
        "status": record[0],
        "updated_at": record[1],
        "original_key": record[2],
        "processed_key": record[3],
        "filename": record[4],
    }


def _is_recent_heartbeat(updated_at: Optional[datetime]) -> bool:
    if not isinstance(updated_at, datetime):
        return False

    if updated_at.tzinfo is not None:
        updated_at = updated_at.replace(tzinfo=None)

    grace_seconds = max(int(settings.worker_heartbeat_seconds) * 3, 60)
    return updated_at >= (datetime.utcnow() - timedelta(seconds=grace_seconds))


async def _blocking_call(func, *args):
    return await asyncio.to_thread(func, *args)


async def _progress_heartbeat(image_id: str, label: str) -> None:
    interval = max(int(settings.worker_heartbeat_seconds), 5)
    while True:
        await asyncio.sleep(interval)
        try:
            await _touch_image(image_id)
            log.info("[%s] Heartbeat: %s", image_id, label)
        except Exception as exc:
            log.warning("[%s] Heartbeat update failed: %s", image_id, exc)


# ─── WMS Validation ────────────────────────────────────────────────────────────

async def validate_wms_layer(
    image_id: str,
    layer_name: str,
    native_bbox: dict,
    crs: str = "EPSG:3857",
) -> bool:
    """
    Make a test WMS 1.3.0 GetMap request against the internal GeoServer URL.
    Returns True if GeoServer returns a valid image/png response.

    Uses the internal GeoServer URL so validation happens server-side without
    depending on the public HTTPS URL being reachable from inside the container.
    """
    gs_internal = settings.geoserver_url.rstrip("/")
    ws = settings.geoserver_workspace

    # WMS 1.3.0 BBOX for EPSG:3857 is: minx,miny,maxx,maxy (easting/northing order)
    bbox_str = (
        f"{native_bbox['minx']},{native_bbox['miny']},"
        f"{native_bbox['maxx']},{native_bbox['maxy']}"
    )

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "LAYERS":  layer_name,
        "BBOX":    bbox_str,
        "CRS":     crs,
        "WIDTH":   "256",
        "HEIGHT":  "256",
        "FORMAT":  "image/png",
        "STYLES":  "",
    }

    try:
        auth = (settings.geoserver_admin_user, settings.geoserver_admin_password)
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{gs_internal}/{ws}/wms", params=params, auth=auth)

        content_type = r.headers.get("content-type", "")
        if r.status_code == 200 and "image" in content_type:
            log.info("[%s] WMS validation OK — %d bytes", image_id, len(r.content))
            return True

        log.warning(
            "[%s] WMS validation failed — HTTP %d  content-type=%s",
            image_id, r.status_code, content_type,
        )
        if "xml" in content_type or "text" in content_type:
            log.warning("[%s] WMS error body: %s", image_id, r.text[:600])
        return False

    except Exception as exc:
        log.warning("[%s] WMS validation error: %s", image_id, exc)
        return False


# ─── Processing pipeline ────────────────────────────────────────────────────────

async def process_uploaded_image(image_id: str, raw_key: str, filename: str) -> None:
    """
    Stage 1 - GDAL pipeline:
      1. Download raw file from object storage
      2. Audit (CRS, bbox, NoData)
      3. Normalize -> reproject to EPSG:3857 -> NoData -> COG
      4. Extract metadata (native + WGS84 bbox)
      5. Upload COG to processed bucket
      6. Push event for GeoServer publication stage
    """
    log.info("[%s] Starting pipeline for %s", image_id, filename)
    await _update_image(image_id, status="processing", error_message=None)

    heartbeat_task = asyncio.create_task(_progress_heartbeat(image_id, "processing"))

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = Path(filename).suffix or ".tif"
            raw_path = os.path.join(tmpdir, f"raw{ext}")
            cog_path = os.path.join(tmpdir, "cog.tif")

            # 1. Download
            log.info("[%s] Downloading %s", image_id, raw_key)
            await _blocking_call(download_from_bucket, settings.storage_bucket_raw, raw_key, raw_path)

            # 2. Audit
            audit = await _blocking_call(audit_raster, raw_path)
            if audit["issues"]:
                log.warning("[%s] Raster issues detected: %s", image_id, audit["issues"])

            # 3. Normalize (assign CRS -> EPSG:3857 -> NoData -> COG)
            log.info("[%s] Normalizing raster", image_id)
            await _blocking_call(normalize_raster, raw_path, cog_path, "EPSG:4326")

            # 4. Extract metadata from normalized COG
            metadata = await _blocking_call(get_raster_metadata, cog_path)
            log.info(
                "[%s] Metadata: crs=%s  native_bbox=%s  wgs84_bbox=%s",
                image_id,
                metadata["crs"],
                metadata["bbox"],
                metadata["bbox_wgs84"],
            )

            # 5. Upload COG
            processed_key = f"{image_id}/cog.tif"
            log.info("[%s] Uploading COG -> %s", image_id, processed_key)
            await _blocking_call(upload_to_bucket, cog_path, settings.storage_bucket_processed, processed_key)

            # 6. Build public URL for GeoServer to read the COG
            gs_data_path = get_cog_public_url(settings.storage_bucket_processed, processed_key)

        # Store WGS84 bbox in DB (human-readable degrees for the dashboard)
        wgs84 = metadata["bbox_wgs84"]
        await _update_image(
            image_id,
            status="processed",
            processed_key=processed_key,
            crs=metadata["crs"],
            bbox_minx=wgs84["minx"],
            bbox_miny=wgs84["miny"],
            bbox_maxx=wgs84["maxx"],
            bbox_maxy=wgs84["maxy"],
        )

        # Publish event for GeoServer publication - include native bbox + crs
        native = metadata["bbox"]
        r = _build_redis_client()
        await r.xadd(
            settings.redis_stream_processed,
            {
                "image_id": image_id,
                "processed_key": processed_key,
                "gs_data_path": gs_data_path,
                "filename": filename,
                "native_crs": metadata["crs"],
                "native_bbox": json.dumps(native),
            },
        )
        await r.aclose()
        log.info("[%s] Processing complete. COG at %s", image_id, processed_key)

    except Exception as exc:
        log.error("[%s] Pipeline error: %s", image_id, exc, exc_info=True)
        await _update_image(image_id, status="error", error_message=str(exc)[:1024])
    finally:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task

async def publish_processed_image(
    image_id: str,
    gs_data_path: str,
    filename: str,
    native_crs: str = "EPSG:3857",
    native_bbox: Optional[dict] = None,
) -> None:
    """
    Stage 2 - GeoServer:
      1. Create / update coverageStore + coverage layer
      2. Configure GWC tile caching (EPSG:3857 + EPSG:4326 gridsets)
      3. Validate WMS GetMap -> if failed, rollback to error status
    """
    log.info("[%s] Publishing to GeoServer", image_id)
    await _update_image(image_id, status="publishing", error_message=None)

    heartbeat_task = asyncio.create_task(_progress_heartbeat(image_id, "publishing"))

    try:
        # GeoServerClient uses synchronous httpx - run in thread executor to avoid
        # blocking the asyncio event loop during REST calls (up to 60s each).
        loop = asyncio.get_event_loop()
        client = GeoServerClient()
        result = await loop.run_in_executor(
            None,
            lambda: client.publish_cog(
                image_id=image_id,
                cog_url=gs_data_path,
                title=filename,
                crs=native_crs,
                native_bbox=native_bbox,
            ),
        )

        await _update_image(
            image_id,
            status="published",
            layer_name=result["layer_name"],
            wms_url=result["wms_url"],
            wmts_url=result["wmts_url"],
            wcs_url=result["wcs_url"],
        )
        log.info("[%s] Published. Layer: %s", image_id, result["layer_name"])

        # WMS validation - give GeoServer time to complete COG indexing.
        # Retry up to 3 times (5s apart) to avoid false failures on large files.
        await asyncio.sleep(5)
        if native_bbox:
            validated = False
            for attempt in range(1, 4):
                ok = await validate_wms_layer(
                    image_id, result["layer_name"], native_bbox, native_crs
                )
                if ok:
                    validated = True
                    break
                if attempt < 3:
                    log.warning("[%s] WMS attempt %d/3 failed - retrying in 5s", image_id, attempt)
                    await asyncio.sleep(5)

            if not validated:
                log.error("[%s] WMS validation failed after 3 attempts - rolling back", image_id)
                store_name = f"img_{image_id.replace('-', '_')}"
                try:
                    await loop.run_in_executor(
                        None,
                        lambda: client._delete(
                            f"/workspaces/{client.ws}/coveragestores/{store_name}.json",
                            params={"recurse": "true"},
                        ),
                    )
                except Exception as del_exc:
                    log.warning("[%s] Rollback GeoServer delete failed: %s", image_id, del_exc)

                await _update_image(
                    image_id,
                    status="error",
                    error_message="WMS GetMap validation failed after publication",
                )
        else:
            log.info("[%s] Skipping WMS validation - native_bbox not available", image_id)

    except Exception as exc:
        log.error("[%s] GeoServer error: %s", image_id, exc, exc_info=True)
        await _update_image(image_id, status="error", error_message=str(exc)[:1024])
    finally:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task

# ─── Stream consumers ───────────────────────────────────────────────────────────

async def ensure_consumer_groups(r: aioredis.Redis) -> None:
    for stream in [settings.redis_stream_uploaded, settings.redis_stream_processed]:
        try:
            await r.xgroup_create(stream, settings.redis_consumer_group, id="0", mkstream=True)
        except Exception:
            pass  # Group already exists


async def _queue_upload_event(r: aioredis.Redis, *, image_id: str, raw_key: str, filename: str) -> None:
    await r.xadd(
        settings.redis_stream_uploaded,
        {
            "image_id": image_id,
            "raw_key": raw_key,
            "filename": filename,
        },
    )


async def _queue_publish_event(
    r: aioredis.Redis,
    *,
    image_id: str,
    processed_key: str,
    filename: str,
    native_crs: str,
) -> None:
    await r.xadd(
        settings.redis_stream_processed,
        {
            "image_id": image_id,
            "processed_key": processed_key,
            "gs_data_path": get_cog_public_url(settings.storage_bucket_processed, processed_key),
            "filename": filename,
            "native_crs": native_crs,
        },
    )


async def recover_stalled_images(r: aioredis.Redis) -> None:
    """Recover orphaned records left in processing/publishing after abrupt container exits."""
    if not settings.worker_enable_stalled_recovery:
        return

    from sqlalchemy import text

    now = datetime.utcnow()
    processing_cutoff = now - timedelta(minutes=max(int(settings.worker_recover_processing_minutes), 5))
    publishing_cutoff = now - timedelta(minutes=max(int(settings.worker_recover_publishing_minutes), 5))

    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            text(
                """
                SELECT id, filename, status, original_key, processed_key, crs, updated_at
                FROM images
                WHERE (status = 'processing' AND updated_at < :processing_cutoff)
                   OR (status = 'publishing' AND updated_at < :publishing_cutoff)
                ORDER BY updated_at ASC
                """
            ),
            {
                "processing_cutoff": processing_cutoff,
                "publishing_cutoff": publishing_cutoff,
            },
        )
        stalled = rows.fetchall()

    if not stalled:
        return

    recovered = 0
    for row in stalled:
        image_id = row[0]
        filename = row[1]
        status = row[2]
        original_key = row[3]
        processed_key = row[4]
        crs = row[5] or "EPSG:3857"
        updated_at = row[6]

        if status == "processing":
            if not original_key:
                await _update_image(
                    image_id,
                    status="error",
                    error_message="Recovery failed: missing original_key for stalled processing item",
                )
                log.error("[%s] Stalled processing recovery failed: missing original_key", image_id)
                continue

            await _update_image(image_id, status="uploaded", error_message=None)
            await _queue_upload_event(r, image_id=image_id, raw_key=original_key, filename=filename)
            recovered += 1
            log.warning(
                "[%s] Recovered stalled processing item (last update: %s) and re-queued upload stage",
                image_id,
                updated_at,
            )
            continue

        if status == "publishing":
            if not processed_key:
                await _update_image(
                    image_id,
                    status="error",
                    error_message="Recovery failed: missing processed_key for stalled publishing item",
                )
                log.error("[%s] Stalled publishing recovery failed: missing processed_key", image_id)
                continue

            await _update_image(image_id, status="processed", error_message=None)
            await _queue_publish_event(
                r,
                image_id=image_id,
                processed_key=processed_key,
                filename=filename,
                native_crs=crs,
            )
            recovered += 1
            log.warning(
                "[%s] Recovered stalled publishing item (last update: %s) and re-queued publish stage",
                image_id,
                updated_at,
            )

    if recovered:
        log.warning("Recovered %d stalled image(s) on startup", recovered)


async def _handle_stream_message(stream: str, data: dict) -> None:
    image_id = data.get("image_id")
    if not image_id:
        log.warning("Skipping malformed stream message without image_id: %s", data)
        return

    state = await _get_image_runtime_state(image_id)
    if not state:
        log.warning("[%s] Skipping stream message: image no longer exists in DB", image_id)
        return

    status = str(state.get("status") or "").lower()
    has_recent_heartbeat = _is_recent_heartbeat(state.get("updated_at"))

    if stream == settings.redis_stream_uploaded:
        if status in {"processed", "publishing", "published"}:
            log.info(
                "[%s] Skip upload event: current status is '%s' (already advanced)",
                image_id,
                status,
            )
            return

        if status == "processing" and has_recent_heartbeat:
            log.info("[%s] Skip upload event: already processing with active heartbeat", image_id)
            return

        if status == "processing" and not has_recent_heartbeat:
            log.warning("[%s] Upload event recovering stale processing without heartbeat", image_id)

        await process_uploaded_image(
            image_id=image_id,
            raw_key=data["raw_key"],
            filename=data["filename"],
        )
        return

    if stream == settings.redis_stream_processed:
        if status == "published":
            log.info("[%s] Skip publish event: already published", image_id)
            return

        if status == "publishing" and has_recent_heartbeat:
            log.info("[%s] Skip publish event: already publishing with active heartbeat", image_id)
            return

        if status in {"uploaded", "processing"}:
            log.info("[%s] Skip publish event: status '%s' not ready for publication", image_id, status)
            return

        native_bbox_raw = data.get("native_bbox")
        native_bbox = None
        if native_bbox_raw:
            try:
                native_bbox = json.loads(native_bbox_raw)
            except Exception as exc:
                log.warning("[%s] Invalid native_bbox payload: %s", image_id, exc)

        await publish_processed_image(
            image_id=image_id,
            gs_data_path=data["gs_data_path"],
            filename=data["filename"],
            native_crs=data.get("native_crs", "EPSG:3857"),
            native_bbox=native_bbox,
        )


async def _process_stream_entries(
    r: aioredis.Redis,
    stream: str,
    entries: list[tuple[str, dict]],
) -> None:
    for msg_id, data in entries:
        try:
            await _handle_stream_message(stream, data)
        except Exception as exc:
            # Keep message pending for reclaim/retry by another worker instance.
            log.error("Error processing message %s (%s): %s", msg_id, stream, exc, exc_info=True)
            continue

        await r.xack(stream, settings.redis_consumer_group, msg_id)
        log.info("Acked message %s on %s", msg_id, stream)


async def _claim_stale_messages(r: aioredis.Redis, stream: str, consumer_name: str) -> int:
    """Reclaim pending messages from dead consumers (e.g., OOM/restart)."""
    start_id = "0-0"
    reclaimed_total = 0

    while True:
        result = await r.xautoclaim(
            stream,
            settings.redis_consumer_group,
            consumer_name,
            min_idle_time=max(int(settings.redis_claim_min_idle_ms), 1000),
            start_id=start_id,
            count=max(int(settings.redis_claim_batch), 1),
        )

        if not result or len(result) < 2:
            break

        next_start_id = result[0]
        entries = result[1] or []
        if not entries:
            break

        reclaimed_total += len(entries)
        log.warning("Reclaimed %d stale pending message(s) from %s", len(entries), stream)
        await _process_stream_entries(r, stream, entries)

        if not next_start_id or next_start_id == "0-0" or next_start_id == start_id:
            break
        start_id = next_start_id

    return reclaimed_total


async def consume_stream(r: aioredis.Redis, stream: str, consumer_name: str) -> None:
    claim_interval = max(int(settings.redis_claim_interval_seconds), 5)
    last_claim = 0.0

    while True:
        try:
            now = time.monotonic()
            if now - last_claim >= claim_interval:
                await _claim_stale_messages(r, stream, consumer_name)
                last_claim = now

            messages = await r.xreadgroup(
                groupname=settings.redis_consumer_group,
                consumername=consumer_name,
                streams={stream: ">"},
                count=1,
                block=5000,
            )
            if not messages:
                continue

            for _stream, entries in messages:
                await _process_stream_entries(r, stream, entries)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.error("Consumer loop error on %s: %s", stream, exc, exc_info=True)
            await asyncio.sleep(2)

# ─── Startup sync ───────────────────────────────────────────────────────────────

async def sync_geoserver_on_startup() -> None:
    """
    Re-publish all 'published' images after a GeoServer restart.

    GeoServer loses all layer configuration when the container restarts
    (no persistent volume on Railway).  On every worker startup we query
    the DB and upsert every published layer so the service recovers
    automatically without manual intervention.
    """
    from sqlalchemy import text

    log.info("GeoServer startup sync starting...")
    try:
        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                text(
                    "SELECT id, processed_key, layer_name, crs, "
                    "bbox_minx, bbox_miny, bbox_maxx, bbox_maxy "
                    "FROM images WHERE status = 'published'"
                )
            )
            images = rows.fetchall()

        if not images:
            log.info("No published images to sync.")
            return

        gs = GeoServerClient()
        gs.ensure_workspace()

        for row in images:
            img_id, processed_key, layer_name, crs, bminx, bminy, bmaxx, bmaxy = row
            if not processed_key or not layer_name:
                continue

            store_name = f"img_{img_id.replace('-', '_')}"
            cog_url    = get_cog_public_url(
                settings.storage_bucket_processed, processed_key
            )

            # DB stores WGS84 degrees (bbox_minx/miny/maxx/maxy).
            # We must NOT pass these as native_bbox when crs=EPSG:3857 — they
            # are degree values, not metres.  Pass None so GeoServer auto-detects
            # the extent from the COG file itself via HTTP Range requests.
            native_bbox = None

            log.info("[sync] Upserting layer: %s", layer_name)
            try:
                gs._upsert_store(store_name, cog_url)
                gs._upsert_coverage(
                    store_name, store_name, layer_name,
                    crs or "EPSG:3857", native_bbox,
                )
                gs._configure_gwc_layer(f"{gs.ws}:{store_name}")
            except Exception as exc:
                log.error("[sync] Failed to upsert %s: %s", layer_name, exc)

        log.info("GeoServer startup sync complete.")

    except Exception as exc:
        log.error("GeoServer startup sync failed: %s", exc, exc_info=True)


# ─── Health server (Cloud Run requires HTTP on PORT) ────────────────────────────

def _start_health_server() -> None:
    port = int(os.environ.get("PORT", 8080))

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):  # suppress per-request access logs
            pass

    HTTPServer(("0.0.0.0", port), _Handler).serve_forever()


# ─── Main ───────────────────────────────────────────────────────────────────────

def _diag_gcs_connectivity() -> None:
    """
    Run at startup: probe TLS connectivity to storage.googleapis.com.
    Tests two paths:
      1. Root URL (CDN) — verifies basic TLS works
      2. Simple object URL — verifies the XML API path works (auth not needed for this probe)
    """
    import subprocess

    for label, probe_url in [
        ("root", "https://storage.googleapis.com/"),
        ("xml-api", "https://storage.googleapis.com/storage/v1/b/raw-images-geopublish/o"),
    ]:
        result = subprocess.run(
            [
                "curl", "-sS",
                "--http1.1",
                "--connect-timeout", "10",
                "--max-time", "15",
                "-o", "/dev/null",
                "-w", "HTTP:%{http_code}  SSL-verify:%{ssl_verify_result}  err:%{errormsg}  time:%{time_total}s",
                probe_url,
            ],
            capture_output=True, text=True,
        )
        level = logging.INFO if result.returncode == 0 else logging.ERROR
        log.log(
            level,
            "[diag] GCS TLS probe [%s]  exit=%d  %s  stderr=%s",
            label,
            result.returncode,
            result.stdout.strip() or "(no stdout)",
            result.stderr.strip()[:400] or "(none)",
        )


def _diag_redis_connectivity() -> None:
    """Best-effort startup probe for Redis TCP connectivity."""
    try:
        parsed = urlparse(settings.redis_url)
        host = parsed.hostname or "(missing-host)"
        port = parsed.port or 6379
        with socket.create_connection((host, port), timeout=5):
            log.info("[diag] Redis TCP probe OK  host=%s port=%s", host, port)
    except Exception as exc:
        log.error("[diag] Redis TCP probe FAILED  url=%s  error=%s", settings.redis_url, exc)


async def _wait_for_redis_ready(r: aioredis.Redis) -> None:
    """Retry Redis ping indefinitely so transient VPC startup delays don't kill worker boot."""
    attempt = 0
    while True:
        attempt += 1
        try:
            await r.ping()
            log.info("Redis ping OK (attempt %d)", attempt)
            return
        except Exception as exc:
            log.error("Redis ping failed (attempt %d): %s", attempt, exc)
            await asyncio.sleep(5)


async def main() -> None:
    threading.Thread(target=_start_health_server, daemon=True).start()
    log.info("GDAL Worker starting...")
    _diag_gcs_connectivity()
    _diag_redis_connectivity()
    r = _build_redis_client()
    await _wait_for_redis_ready(r)
    await ensure_consumer_groups(r)
    await recover_stalled_images(r)

    consumer_name = f"worker-{socket.gethostname()}-{os.getpid()}"
    log.info(
        "Consumer: %s  |  streams: %s, %s  |  heartbeat=%ss  reclaim_idle_ms=%s",
        consumer_name,
        settings.redis_stream_uploaded,
        settings.redis_stream_processed,
        settings.worker_heartbeat_seconds,
        settings.redis_claim_min_idle_ms,
    )

    await sync_geoserver_on_startup()

    await asyncio.gather(
        consume_stream(r, settings.redis_stream_uploaded,  consumer_name),
        consume_stream(r, settings.redis_stream_processed, f"{consumer_name}-pub"),
    )


if __name__ == "__main__":
    asyncio.run(main())
