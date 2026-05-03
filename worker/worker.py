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
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
import redis.asyncio as aioredis

from config import get_settings
from db_client import AsyncSessionLocal
from geoserver_client import GeoServerClient
from pipeline import (
    audit_raster,
    normalize_raster,
    get_raster_metadata,
    inspect_raster_optimization,
    # backward-compat shims kept in pipeline.py
    reproject,
    build_overviews,
    to_cog,
)
from storage_client import download_from_bucket, get_cog_public_url, upload_to_bucket
from services.geoserver_service import GeoServerVectorService, build_workspace_name
from services.vector_processor import (
    build_postgis_table_name,
    detect_vector_type,
    process_vector_file,
)
from services.processing_strategy import classify_processing_strategy

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


async def _ensure_layers_metadata_table() -> None:
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS layers_metadata (
                    id VARCHAR(36) PRIMARY KEY,
                    image_id VARCHAR(36) NOT NULL UNIQUE,
                    nome VARCHAR(512) NOT NULL,
                    tipo VARCHAR(64) NOT NULL,
                    geometry_type VARCHAR(64),
                    tabela_postgis VARCHAR(128),
                    workspace VARCHAR(128),
                    datastore VARCHAR(128),
                    wms_url TEXT,
                    wfs_url TEXT,
                    bbox TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )
        )
        await session.commit()


async def _ensure_image_extended_columns() -> None:
    from sqlalchemy import text

    statements = [
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS wfs_url TEXT;",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS asset_kind VARCHAR(32);",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS source_format VARCHAR(64);",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS workspace VARCHAR(128);",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS datastore VARCHAR(128);",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS postgis_table VARCHAR(128);",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS geometry_type VARCHAR(64);",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS processing_strategy VARCHAR(64);",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS worker_type VARCHAR(64);",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS processing_queue VARCHAR(128);",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS requires_gdal BOOLEAN;",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS requires_postgis BOOLEAN;",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS requires_geoserver BOOLEAN;",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP;",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS processing_finished_at TIMESTAMP;",
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS processing_duration_seconds FLOAT;",
    ]

    async with AsyncSessionLocal() as session:
        for statement in statements:
            try:
                await session.execute(text(statement))
            except Exception as exc:
                log.warning("Schema compatibility update skipped for statement '%s': %s", statement, exc)
        await session.commit()


async def _upsert_layer_metadata(
    *,
    image_id: str,
    nome: str,
    tipo: str,
    geometry_type: Optional[str],
    tabela_postgis: Optional[str],
    workspace: Optional[str],
    datastore: Optional[str],
    wms_url: Optional[str],
    wfs_url: Optional[str],
    bbox: Optional[dict],
) -> None:
    from sqlalchemy import text

    await _ensure_layers_metadata_table()
    payload = {
        "id": image_id,
        "image_id": image_id,
        "nome": nome,
        "tipo": tipo,
        "geometry_type": geometry_type,
        "tabela_postgis": tabela_postgis,
        "workspace": workspace,
        "datastore": datastore,
        "wms_url": wms_url,
        "wfs_url": wfs_url,
        "bbox": json.dumps(bbox) if bbox else None,
    }

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO layers_metadata (
                    id, image_id, nome, tipo, geometry_type, tabela_postgis,
                    workspace, datastore, wms_url, wfs_url, bbox
                ) VALUES (
                    :id, :image_id, :nome, :tipo, :geometry_type, :tabela_postgis,
                    :workspace, :datastore, :wms_url, :wfs_url, :bbox
                )
                ON CONFLICT (image_id) DO UPDATE SET
                    nome = EXCLUDED.nome,
                    tipo = EXCLUDED.tipo,
                    geometry_type = EXCLUDED.geometry_type,
                    tabela_postgis = EXCLUDED.tabela_postgis,
                    workspace = EXCLUDED.workspace,
                    datastore = EXCLUDED.datastore,
                    wms_url = EXCLUDED.wms_url,
                    wfs_url = EXCLUDED.wfs_url,
                    bbox = EXCLUDED.bbox,
                    updated_at = NOW();
                """
            ),
            payload,
        )
        await session.commit()


async def _get_image_runtime_state(image_id: str) -> Optional[dict]:
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        row = await session.execute(
            text(
                """
                SELECT status, updated_at, original_key, processed_key, filename,
                       asset_kind, source_format, workspace, datastore, postgis_table,
                       processing_strategy, worker_type, processing_queue
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
        "asset_kind": record[5],
        "source_format": record[6],
        "workspace": record[7],
        "datastore": record[8],
        "postgis_table": record[9],
        "processing_strategy": record[10],
        "worker_type": record[11],
        "processing_queue": record[12],
    }


async def _get_image_tenant_id(image_id: str) -> str:
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        row = await session.execute(
            text("SELECT tenant_id FROM images WHERE id = :image_id"),
            {"image_id": image_id},
        )
        record = row.first()

    tenant_id = str(record[0] or "").strip() if record else ""
    return tenant_id or "default"


def _is_recent_heartbeat(updated_at: Optional[datetime]) -> bool:
    if not isinstance(updated_at, datetime):
        return False

    if updated_at.tzinfo is not None:
        updated_at = updated_at.replace(tzinfo=None)

    grace_seconds = max(int(settings.worker_heartbeat_seconds) * 3, 60)
    return updated_at >= (datetime.utcnow() - timedelta(seconds=grace_seconds))


async def _blocking_call(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


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
    workspace: Optional[str] = None,
) -> bool:
    """
    Make a test WMS 1.3.0 GetMap request against the internal GeoServer URL.
    Returns True if GeoServer returns a valid image/png response.

    Uses the internal GeoServer URL so validation happens server-side without
    depending on the public HTTPS URL being reachable from inside the container.
    """
    gs_internal = settings.geoserver_url.rstrip("/")
    ws = (workspace or settings.geoserver_workspace or "").strip()
    if not ws:
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
    Stage 1:
      - raster: normalize to COG and emit publish event
      - vector: normalize and persist in PostGIS, then emit publish event
    """
    log.info("[%s] Starting pipeline for %s", image_id, filename)
    started_monotonic = time.monotonic()
    strategy = classify_processing_strategy(filename=filename)
    await _update_image(
        image_id,
        status="processing",
        error_message=None,
        processing_strategy=strategy.processing_strategy,
        worker_type=strategy.worker_type,
        processing_queue=strategy.processing_queue,
        requires_gdal=strategy.requires_gdal,
        requires_postgis=strategy.requires_postgis,
        requires_geoserver=strategy.requires_geoserver,
        processing_started_at=datetime.utcnow(),
    )

    heartbeat_task = asyncio.create_task(_progress_heartbeat(image_id, "processing"))
    vector_type = detect_vector_type(filename)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = Path(filename).suffix or ".tif"
            raw_path = os.path.join(tmpdir, f"raw{ext}")

            # 1. Download source object
            log.info("[%s] Downloading %s", image_id, raw_key)
            await _blocking_call(download_from_bucket, settings.storage_bucket_raw, raw_key, raw_path)

            if vector_type:
                table_name = build_postgis_table_name(image_id)
                tenant_id = await _get_image_tenant_id(image_id)
                workspace = build_workspace_name(tenant_id)
                datastore = settings.vector_default_datastore

                vector_result = await asyncio.wait_for(
                    _blocking_call(process_vector_file, raw_path, vector_type, table_name),
                    timeout=max(int(settings.vector_processing_timeout_seconds), 60),
                )
                bbox = vector_result["bbox_wgs84"]
                await _update_image(
                    image_id,
                    status="processed",
                    processed_key=None,
                    crs=vector_result["crs"],
                    bbox_minx=bbox["minx"],
                    bbox_miny=bbox["miny"],
                    bbox_maxx=bbox["maxx"],
                    bbox_maxy=bbox["maxy"],
                    asset_kind="vector",
                    source_format=vector_type,
                    workspace=workspace,
                    datastore=datastore,
                    postgis_table=table_name,
                    geometry_type=vector_result["geometry_type"],
                )

                r = _build_redis_client()
                await r.xadd(
                    settings.redis_stream_processed,
                    {
                        "image_id": image_id,
                        "filename": filename,
                        "vector": "1",
                        "workspace": workspace,
                        "datastore": datastore,
                        "table_name": table_name,
                        "geometry_type": vector_result["geometry_type"],
                        "native_crs": "EPSG:4326",
                        "native_bbox": json.dumps(bbox),
                    },
                )
                await r.aclose()
                log.info(
                    "[%s] Vector processing complete. table=%s workspace=%s",
                    image_id,
                    table_name,
                    workspace,
                )
                return

            cog_path = os.path.join(tmpdir, "cog.tif")

            # 2. Raster audit
            audit = await _blocking_call(audit_raster, raw_path)
            if audit["issues"]:
                log.warning("[%s] Raster issues detected: %s", image_id, audit["issues"])

            # 3. Raster normalize (assign CRS -> EPSG:3857 -> NoData -> COG)
            raster_plan = await _blocking_call(inspect_raster_optimization, raw_path)
            can_passthrough_cog = (
                bool(settings.raster_skip_cog_if_already_cog)
                and raster_plan.get("is_cog") is True
                and raster_plan.get("epsg") == settings.raster_target_crs
            )
            if can_passthrough_cog:
                log.info(
                    "[%s] Raster already optimized as COG in %s; skipping GDAL normalization",
                    image_id,
                    settings.raster_target_crs,
                )
                cog_path = raw_path
            else:
                log.info("[%s] Normalizing raster", image_id)
                await _blocking_call(
                    normalize_raster,
                    raw_path,
                    cog_path,
                    "EPSG:4326",
                    target_crs=settings.raster_target_crs,
                    skip_reproject_if_same_crs=bool(settings.raster_skip_reproject_if_same_crs),
                )

            # 4. Raster metadata from normalized COG
            metadata = await _blocking_call(get_raster_metadata, cog_path)
            log.info(
                "[%s] Metadata: crs=%s native_bbox=%s wgs84_bbox=%s",
                image_id,
                metadata["crs"],
                metadata["bbox"],
                metadata["bbox_wgs84"],
            )

            # 5. Upload COG
            processed_key = f"{image_id}/cog.tif"
            log.info("[%s] Uploading COG -> %s", image_id, processed_key)
            await _blocking_call(upload_to_bucket, cog_path, settings.storage_bucket_processed, processed_key)

            # 6. Build public URL for GeoServer COG coverage store
            gs_data_path = get_cog_public_url(settings.storage_bucket_processed, processed_key)

        # Store WGS84 bbox in DB for dashboard/queries
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
            asset_kind="raster",
            source_format=(Path(filename).suffix or ".tif").lower().lstrip("."),
            workspace=settings.geoserver_workspace,
            datastore=None,
            postgis_table=None,
            geometry_type="RASTER",
        )

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
                "vector": "0",
            },
        )
        await r.aclose()
        log.info("[%s] Raster processing complete. COG at %s", image_id, processed_key)

    except Exception as exc:
        log.error("[%s] Pipeline error: %s", image_id, exc, exc_info=True)
        await _update_image(image_id, status="error", error_message=str(exc)[:1024])
    finally:
        duration = max(time.monotonic() - started_monotonic, 0.0)
        with suppress(Exception):
            await _update_image(
                image_id,
                processing_finished_at=datetime.utcnow(),
                processing_duration_seconds=round(duration, 3),
            )
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task

async def publish_processed_image(
    image_id: str,
    gs_data_path: Optional[str],
    filename: str,
    native_crs: str = "EPSG:3857",
    native_bbox: Optional[dict] = None,
    *,
    is_vector: bool = False,
    workspace: Optional[str] = None,
    datastore: Optional[str] = None,
    table_name: Optional[str] = None,
    geometry_type: Optional[str] = None,
) -> None:
    """
    Stage 2 - GeoServer publication.
    """
    log.info("[%s] Publishing to GeoServer (vector=%s)", image_id, is_vector)
    await _update_image(image_id, status="publishing", error_message=None)

    heartbeat_task = asyncio.create_task(_progress_heartbeat(image_id, "publishing"))

    try:
        loop = asyncio.get_event_loop()
        if is_vector:
            vector_client = GeoServerVectorService()
            workspace_name = workspace or build_workspace_name(await _get_image_tenant_id(image_id))
            datastore_name = datastore or settings.vector_default_datastore
            table = table_name or build_postgis_table_name(image_id)
            published_workspace = workspace_name
            published_datastore = datastore_name
            published_table = table

            def _publish_vector():
                vector_client.create_workspace(workspace_name)
                datastore_created = vector_client.create_datastore(workspace_name, datastore_name)
                return vector_client.publish_layer(
                    workspace_name,
                    datastore_created,
                    table,
                    title=filename,
                )

            result = await loop.run_in_executor(None, _publish_vector)

            await _update_image(
                image_id,
                status="published",
                layer_name=result["layer_name"],
                wms_url=result["wms_url"],
                wfs_url=result["wfs_url"],
                wmts_url=None,
                wcs_url=None,
                workspace=workspace_name,
                datastore=datastore_name,
                postgis_table=table,
                asset_kind="vector",
            )
            await _upsert_layer_metadata(
                image_id=image_id,
                nome=filename,
                tipo="vector",
                geometry_type=geometry_type,
                tabela_postgis=table,
                workspace=workspace_name,
                datastore=datastore_name,
                wms_url=result["wms_url"],
                wfs_url=result["wfs_url"],
                bbox=native_bbox,
            )
            log.info("[%s] Vector layer published: %s", image_id, result["layer_name"])
        else:
            if not gs_data_path:
                raise RuntimeError("Missing gs_data_path for raster publication")
            published_workspace = settings.geoserver_workspace
            published_datastore = None
            published_table = None

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
                wfs_url=None,
                workspace=settings.geoserver_workspace,
                datastore=None,
                postgis_table=None,
                asset_kind="raster",
            )
            await _upsert_layer_metadata(
                image_id=image_id,
                nome=filename,
                tipo="raster",
                geometry_type="RASTER",
                tabela_postgis=None,
                workspace=settings.geoserver_workspace,
                datastore=None,
                wms_url=result["wms_url"],
                wfs_url=None,
                bbox=native_bbox,
            )
            log.info("[%s] Raster layer published: %s", image_id, result["layer_name"])

        # Validation retries (WMS) for both raster and vector layers.
        await asyncio.sleep(5)
        if native_bbox:
            validated = False
            for attempt in range(1, 4):
                ok = await validate_wms_layer(
                    image_id,
                    result["layer_name"],
                    native_bbox,
                    native_crs,
                    workspace=published_workspace,
                )
                if ok:
                    validated = True
                    break
                if attempt < 3:
                    log.warning("[%s] WMS attempt %d/3 failed - retrying in 5s", image_id, attempt)
                    await asyncio.sleep(5)

            if not validated:
                log.error("[%s] WMS validation failed after publication - rolling back", image_id)
                if is_vector:
                    try:
                        await loop.run_in_executor(
                            None,
                            lambda: GeoServerVectorService().delete_layer(
                                published_workspace,
                                published_datastore or settings.vector_default_datastore,
                                published_table or build_postgis_table_name(image_id),
                            ),
                        )
                    except Exception as del_exc:
                        log.warning("[%s] Vector rollback failed: %s", image_id, del_exc)
                else:
                    store_name = f"img_{image_id.replace('-', '_')}"
                    try:
                        await loop.run_in_executor(
                            None,
                            lambda: GeoServerClient()._delete(
                                f"/workspaces/{settings.geoserver_workspace}/coveragestores/{store_name}.json",
                                params={"recurse": "true"},
                            ),
                        )
                    except Exception as del_exc:
                        log.warning("[%s] Raster rollback failed: %s", image_id, del_exc)

                await _update_image(
                    image_id,
                    status="error",
                    error_message="WMS GetMap validation failed after publication",
                )
        else:
            log.info("[%s] Skipping WMS validation - bbox not available", image_id)

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


async def _queue_publish_event_vector(
    r: aioredis.Redis,
    *,
    image_id: str,
    filename: str,
    workspace: str,
    datastore: str,
    table_name: str,
    native_crs: str,
    native_bbox: Optional[dict] = None,
    geometry_type: Optional[str] = None,
) -> None:
    payload = {
        "image_id": image_id,
        "filename": filename,
        "vector": "1",
        "workspace": workspace,
        "datastore": datastore,
        "table_name": table_name,
        "native_crs": native_crs,
    }
    if geometry_type:
        payload["geometry_type"] = geometry_type
    if native_bbox:
        payload["native_bbox"] = json.dumps(native_bbox)
    await r.xadd(settings.redis_stream_processed, payload)


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
                SELECT id, filename, status, original_key, processed_key, crs, updated_at,
                       asset_kind, workspace, datastore, postgis_table, geometry_type,
                       bbox_minx, bbox_miny, bbox_maxx, bbox_maxy
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
        asset_kind = str(row[7] or "").lower()
        workspace = row[8]
        datastore = row[9]
        postgis_table = row[10]
        geometry_type = row[11]
        bbox_minx = row[12]
        bbox_miny = row[13]
        bbox_maxx = row[14]
        bbox_maxy = row[15]

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
            bbox = None
            if (
                bbox_minx is not None
                and bbox_miny is not None
                and bbox_maxx is not None
                and bbox_maxy is not None
            ):
                bbox = {
                    "minx": float(bbox_minx),
                    "miny": float(bbox_miny),
                    "maxx": float(bbox_maxx),
                    "maxy": float(bbox_maxy),
                }

            if asset_kind == "vector":
                if not workspace or not datastore or not postgis_table:
                    await _update_image(
                        image_id,
                        status="error",
                        error_message=(
                            "Recovery failed: missing workspace/datastore/postgis_table "
                            "for stalled vector publishing item"
                        ),
                    )
                    log.error("[%s] Stalled vector publishing recovery failed: missing metadata", image_id)
                    continue

                await _update_image(image_id, status="processed", error_message=None)
                await _queue_publish_event_vector(
                    r,
                    image_id=image_id,
                    filename=filename,
                    workspace=workspace,
                    datastore=datastore,
                    table_name=postgis_table,
                    native_crs=crs or "EPSG:4326",
                    native_bbox=bbox,
                    geometry_type=geometry_type,
                )
                recovered += 1
                log.warning(
                    "[%s] Recovered stalled vector publishing item (last update: %s) and re-queued publish stage",
                    image_id,
                    updated_at,
                )
                continue

            if not processed_key:
                await _update_image(
                    image_id,
                    status="error",
                    error_message="Recovery failed: missing processed_key for stalled publishing item",
                )
                log.error("[%s] Stalled raster publishing recovery failed: missing processed_key", image_id)
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
                "[%s] Recovered stalled raster publishing item (last update: %s) and re-queued publish stage",
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
            gs_data_path=data.get("gs_data_path"),
            filename=data["filename"],
            native_crs=data.get("native_crs", "EPSG:3857"),
            native_bbox=native_bbox,
            is_vector=str(data.get("vector", "0")) == "1",
            workspace=data.get("workspace"),
            datastore=data.get("datastore"),
            table_name=data.get("table_name"),
            geometry_type=data.get("geometry_type"),
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


async def _consume_job_batch(r: aioredis.Redis, consumer_name: str) -> int:
    """
    Process one bounded batch across both streams and return message count handled.
    Designed for Cloud Run Job mode (periodic execution + clean exit).
    """
    handled = 0

    for stream in [settings.redis_stream_uploaded, settings.redis_stream_processed]:
        handled += await _claim_stale_messages(r, stream, consumer_name)

    messages = await r.xreadgroup(
        groupname=settings.redis_consumer_group,
        consumername=consumer_name,
        streams={
            settings.redis_stream_uploaded: ">",
            settings.redis_stream_processed: ">",
        },
        count=max(int(settings.worker_job_batch_count), 1),
        block=max(int(settings.worker_job_block_ms), 1000),
    )
    if not messages:
        return handled

    for stream, entries in messages:
        handled += len(entries)
        await _process_stream_entries(r, stream, entries)

    return handled


async def run_job_mode(r: aioredis.Redis, consumer_name: str) -> None:
    idle_exit_seconds = max(int(settings.worker_job_idle_exit_seconds), 10)
    max_runtime_seconds = max(int(settings.worker_job_max_runtime_seconds), 60)
    started_at = time.monotonic()
    last_activity = started_at
    total_handled = 0

    log.info(
        "Job mode active | idle_exit=%ss max_runtime=%ss block_ms=%s batch_count=%s",
        idle_exit_seconds,
        max_runtime_seconds,
        settings.worker_job_block_ms,
        settings.worker_job_batch_count,
    )

    while True:
        now = time.monotonic()
        runtime = now - started_at
        if runtime >= max_runtime_seconds:
            log.info(
                "Job mode exiting by max runtime (%ss). total_handled=%s",
                max_runtime_seconds,
                total_handled,
            )
            return

        handled = await _consume_job_batch(r, consumer_name)
        if handled > 0:
            total_handled += handled
            last_activity = time.monotonic()
            log.info("Job mode handled batch=%s total=%s", handled, total_handled)
            continue

        idle_for = time.monotonic() - last_activity
        if idle_for >= idle_exit_seconds:
            log.info(
                "Job mode exiting by idle (%0.1fs). total_handled=%s",
                idle_for,
                total_handled,
            )
            return

# ─── Startup sync ───────────────────────────────────────────────────────────────

async def sync_geoserver_on_startup() -> None:
    """
    Re-publish all published images after a GeoServer restart.

    GeoServer can lose in-memory catalog entries after restart.
    On worker startup we upsert published raster and vector layers.
    """
    from sqlalchemy import text

    log.info("GeoServer startup sync starting...")
    try:
        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                text(
                    "SELECT id, filename, asset_kind, processed_key, layer_name, crs, "
                    "workspace, datastore, postgis_table "
                    "FROM images WHERE status = 'published'"
                )
            )
            images = rows.fetchall()

        if not images:
            log.info("No published images to sync.")
            return

        gs_raster = GeoServerClient()
        gs_raster.ensure_workspace()
        gs_vector = GeoServerVectorService()

        for row in images:
            (
                img_id,
                filename,
                asset_kind,
                processed_key,
                layer_name,
                crs,
                workspace,
                datastore,
                postgis_table,
            ) = row

            if str(asset_kind or "").lower() == "vector":
                if not workspace or not datastore or not postgis_table:
                    log.warning("[sync] Skipping vector image %s: missing workspace/datastore/table", img_id)
                    continue

                try:
                    gs_vector.create_workspace(workspace)
                    gs_vector.create_datastore(workspace, datastore)
                    gs_vector.publish_layer(
                        workspace=workspace,
                        datastore=datastore,
                        table_name=postgis_table,
                        title=filename or postgis_table,
                    )
                    log.info("[sync] Re-published vector layer %s:%s", workspace, postgis_table)
                except Exception as exc:
                    log.error("[sync] Failed to re-publish vector %s: %s", img_id, exc)
                continue

            if not processed_key or not layer_name:
                continue

            store_name = f"img_{img_id.replace('-', '_')}"
            cog_url = get_cog_public_url(settings.storage_bucket_processed, processed_key)
            native_bbox = None

            log.info("[sync] Re-publishing raster layer: %s", layer_name)
            try:
                gs_raster._upsert_store(store_name, cog_url)
                gs_raster._upsert_coverage(
                    store_name,
                    store_name,
                    layer_name,
                    crs or "EPSG:3857",
                    native_bbox,
                )
                gs_raster._configure_gwc_layer(f"{gs_raster.ws}:{store_name}")
            except Exception as exc:
                log.error("[sync] Failed to re-publish raster %s: %s", layer_name, exc)

        log.info("GeoServer startup sync complete.")

    except Exception as exc:
        log.error("GeoServer startup sync failed: %s", exc, exc_info=True)


# Health server (Cloud Run requires HTTP on PORT)
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
    worker_mode = str(settings.worker_mode or "service").strip().lower()
    if worker_mode not in {"service", "job"}:
        log.warning("Unknown worker_mode=%s. Falling back to 'service'.", worker_mode)
        worker_mode = "service"

    if settings.worker_enable_health_server and worker_mode == "service":
        threading.Thread(target=_start_health_server, daemon=True).start()

    log.info("GDAL Worker starting...")
    _diag_gcs_connectivity()
    _diag_redis_connectivity()
    r = _build_redis_client()
    try:
        await _wait_for_redis_ready(r)
        await _ensure_image_extended_columns()
        await _ensure_layers_metadata_table()
        await ensure_consumer_groups(r)
        await recover_stalled_images(r)

        instance_token = os.environ.get("K_REVISION", "local")
        consumer_name = f"worker-{instance_token}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        log.info(
            "Mode=%s | Consumer=%s | streams=%s,%s | heartbeat=%ss | reclaim_idle_ms=%s",
            worker_mode,
            consumer_name,
            settings.redis_stream_uploaded,
            settings.redis_stream_processed,
            settings.worker_heartbeat_seconds,
            settings.redis_claim_min_idle_ms,
        )

        if settings.worker_enable_startup_sync:
            await sync_geoserver_on_startup()
        else:
            log.info("GeoServer startup sync disabled by configuration")

        if worker_mode == "job":
            await run_job_mode(r, consumer_name)
            return

        await asyncio.gather(
            consume_stream(r, settings.redis_stream_uploaded, consumer_name),
            consume_stream(r, settings.redis_stream_processed, f"{consumer_name}-pub"),
        )
    finally:
        await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
