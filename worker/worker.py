"""
GDAL Worker — consumes Redis Streams, processes rasters, publishes to GeoServer.

Stream: image:uploaded  → process raster (reproject → overviews → COG)
Stream: image:processed → publish to GeoServer (register layer, expose OGC)
"""

import asyncio
import os
import tempfile
import logging
from pathlib import Path

import redis.asyncio as aioredis
from sqlalchemy import update

from config import get_settings
from db_client import AsyncSessionLocal
from storage_client import download_from_bucket, upload_to_bucket, get_cog_public_url
from geoserver_client import GeoServerClient
from pipeline import reproject, build_overviews, to_cog, get_raster_metadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("worker")

settings = get_settings()

# ─── Lazy imports to keep sys.path clean ───────────────────────────────────

def _import_image_model():
    import sys
    sys.path.insert(0, "/worker")
    from sqlalchemy import Column, String
    # We define a minimal mapped version inline to avoid circular deps
    # The actual table definition lives in api/models/image.py
    # Worker uses raw SQL via SQLAlchemy text() to update status columns
    pass


# ─── DB helpers ────────────────────────────────────────────────────────────

async def _update_image(image_id: str, **fields) -> None:
    from sqlalchemy import text
    async with AsyncSessionLocal() as session:
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        sql = text(f"UPDATE images SET {set_clause}, updated_at = NOW() WHERE id = :image_id")
        await session.execute(sql, {"image_id": image_id, **fields})
        await session.commit()


# ─── Processing pipeline ────────────────────────────────────────────────────

async def process_uploaded_image(image_id: str, raw_key: str, filename: str) -> None:
    log.info(f"[{image_id}] Starting GDAL pipeline for {filename}")

    await _update_image(image_id, status="processing")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = Path(filename).suffix or ".tif"
            raw_path = os.path.join(tmpdir, f"raw{ext}")
            reproj_path = os.path.join(tmpdir, "reprojected.tif")
            cog_path = os.path.join(tmpdir, "cog.tif")

            # 1. Download raw file from bucket
            log.info(f"[{image_id}] Downloading from bucket: {raw_key}")
            download_from_bucket(settings.storage_bucket_raw, raw_key, raw_path)

            # 2. Reproject
            log.info(f"[{image_id}] Reprojecting to {settings.target_crs}")
            reproject(raw_path, reproj_path, target_crs=settings.target_crs)

            # 3. Build overviews
            log.info(f"[{image_id}] Building overviews")
            build_overviews(reproj_path)

            # 4. Convert to COG
            log.info(f"[{image_id}] Converting to COG")
            to_cog(reproj_path, cog_path)

            # 5. Extract metadata
            metadata = get_raster_metadata(cog_path)
            log.info(f"[{image_id}] Metadata: {metadata}")

            # 6. Upload COG to processed bucket
            processed_key = f"{image_id}/cog.tif"
            log.info(f"[{image_id}] Uploading COG to processed bucket")
            upload_to_bucket(cog_path, settings.storage_bucket_processed, processed_key)

            # 7. Build permanent public URL for GeoServer to read the COG
            gs_data_path = get_cog_public_url(settings.storage_bucket_processed, processed_key)

        bbox = metadata.get("bbox") or {}
        await _update_image(
            image_id,
            status="processed",
            processed_key=processed_key,
            crs=metadata.get("crs"),
            bbox_minx=bbox.get("minx"),
            bbox_miny=bbox.get("miny"),
            bbox_maxx=bbox.get("maxx"),
            bbox_maxy=bbox.get("maxy"),
        )

        # 8. Publish event for publication pipeline
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.xadd(
            settings.redis_stream_processed,
            {
                "image_id": image_id,
                "processed_key": processed_key,
                "gs_data_path": gs_data_path,
                "filename": filename,
            },
        )
        await r.aclose()
        log.info(f"[{image_id}] Processing complete. COG at {processed_key}")

    except Exception as e:
        log.error(f"[{image_id}] Pipeline error: {e}", exc_info=True)
        await _update_image(image_id, status="error", error_message=str(e)[:1024])


# ─── GeoServer publication ─────────────────────────────────────────────────

async def publish_processed_image(
    image_id: str,
    gs_data_path: str,
    filename: str,
) -> None:
    log.info(f"[{image_id}] Publishing to GeoServer")
    await _update_image(image_id, status="publishing")

    try:
        client = GeoServerClient()
        result = client.publish_cog(
            image_id=image_id,
            cog_url=gs_data_path,   # now an HTTPS presigned URL
            title=filename,
        )
        await _update_image(
            image_id,
            status="published",
            layer_name=result["layer_name"],
            wms_url=result["wms_url"],
            wmts_url=result["wmts_url"],
            wcs_url=result["wcs_url"],
        )
        log.info(f"[{image_id}] Published. Layer: {result['layer_name']}")

    except Exception as e:
        log.error(f"[{image_id}] GeoServer error: {e}", exc_info=True)
        await _update_image(image_id, status="error", error_message=str(e)[:1024])


# ─── Stream consumers ───────────────────────────────────────────────────────

async def ensure_consumer_groups(r: aioredis.Redis) -> None:
    for stream in [settings.redis_stream_uploaded, settings.redis_stream_processed]:
        try:
            await r.xgroup_create(stream, settings.redis_consumer_group, id="0", mkstream=True)
        except Exception:
            pass  # Group already exists


async def consume_stream(r: aioredis.Redis, stream: str, consumer_name: str) -> None:
    while True:
        try:
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
                for msg_id, data in entries:
                    try:
                        if stream == settings.redis_stream_uploaded:
                            await process_uploaded_image(
                                image_id=data["image_id"],
                                raw_key=data["raw_key"],
                                filename=data["filename"],
                            )
                        elif stream == settings.redis_stream_processed:
                            await publish_processed_image(
                                image_id=data["image_id"],
                                gs_data_path=data["gs_data_path"],
                                filename=data["filename"],
                            )
                        await r.xack(stream, settings.redis_consumer_group, msg_id)
                    except Exception as e:
                        log.error(f"Error processing message {msg_id}: {e}", exc_info=True)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Consumer loop error on {stream}: {e}", exc_info=True)
            await asyncio.sleep(2)


async def main() -> None:
    log.info("GDAL Worker starting...")
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    await ensure_consumer_groups(r)

    consumer_name = f"worker-{os.getpid()}"
    log.info(f"Consumer name: {consumer_name}")
    log.info("Listening on streams: image:uploaded, image:processed")

    await asyncio.gather(
        consume_stream(r, settings.redis_stream_uploaded, consumer_name),
        consume_stream(r, settings.redis_stream_processed, f"{consumer_name}-pub"),
    )


if __name__ == "__main__":
    asyncio.run(main())
