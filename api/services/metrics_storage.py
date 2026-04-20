from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models import AssetAccessLog, Image
from services.storage import get_gcs

log = logging.getLogger("api.metrics.storage")
settings = get_settings()


def bytes_to_mb(value: int) -> float:
    return value / (1024 * 1024)


def bytes_to_gb(value: int) -> float:
    return value / (1024 * 1024 * 1024)


def normalize_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower().replace(".", "")
    if not ext:
        return "unknown"
    if ext in {"tif", "tiff", "geotiff"}:
        return "geotiff"
    return ext


def calculate_growth_percent(current_period_bytes: int, previous_period_bytes: int) -> float:
    if previous_period_bytes <= 0:
        return 100.0 if current_period_bytes > 0 else 0.0
    return ((current_period_bytes - previous_period_bytes) / previous_period_bytes) * 100.0


def _resolve_storage_target(image: Image) -> tuple[str, str] | None:
    if image.processed_key:
        return settings.storage_bucket_processed, image.processed_key
    if image.original_key:
        return settings.storage_bucket_raw, image.original_key
    return None


def _read_blob_size(bucket_name: str, key: str, cache: dict[tuple[str, str], int]) -> int:
    cache_key = (bucket_name, key)
    if cache_key in cache:
        return cache[cache_key]

    size_bytes = 0
    try:
        bucket = get_gcs().bucket(bucket_name)
        blob = bucket.get_blob(key)
        if blob is not None and blob.size is not None:
            size_bytes = int(blob.size)
    except Exception as exc:  # pragma: no cover - depends on storage availability
        log.warning("Unable to read blob size for %s/%s: %s", bucket_name, key, exc)

    cache[cache_key] = size_bytes
    return size_bytes


def _as_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.utcnow()
    return value


def _build_usage_timeseries(image_stats: list[dict[str, Any]], window_days: int) -> list[dict[str, Any]]:
    today = datetime.utcnow().date()
    start_day = today - timedelta(days=window_days - 1)

    added_by_day: dict[Any, int] = defaultdict(int)
    files_by_day: dict[Any, int] = defaultdict(int)

    for item in image_stats:
        day = _as_datetime(item["created_at"]).date()
        if day < start_day:
            continue
        added_by_day[day] += int(item["size_bytes"])
        files_by_day[day] += 1

    timeseries: list[dict[str, Any]] = []
    cumulative = 0
    for offset in range(window_days):
        day = start_day + timedelta(days=offset)
        added = added_by_day[day]
        cumulative += added
        timeseries.append(
            {
                "date": day.isoformat(),
                "files_added": files_by_day[day],
                "added_gb": round(bytes_to_gb(added), 4),
                "total_gb": round(bytes_to_gb(cumulative), 4),
            }
        )

    return timeseries


async def get_storage_metrics(
    db: AsyncSession,
    *,
    tenant_id: str,
    window_days: int,
    access_type: Literal["all", "download", "ogc"] = "all",
) -> dict[str, Any]:
    result = await db.execute(select(Image))
    images = list(result.scalars())

    blob_size_cache: dict[tuple[str, str], int] = {}
    image_stats: list[dict[str, Any]] = []

    for image in images:
        target = _resolve_storage_target(image)
        size_bytes = 0
        if target is not None:
            bucket_name, key = target
            size_bytes = _read_blob_size(bucket_name, key, blob_size_cache)

        image_stats.append(
            {
                "id": image.id,
                "filename": image.filename,
                "created_at": image.created_at,
                "size_bytes": size_bytes,
                "file_type": normalize_file_type(image.filename),
            }
        )

    total_files = len(image_stats)
    total_size_bytes = sum(item["size_bytes"] for item in image_stats)
    avg_size_mb = bytes_to_mb(total_size_bytes) / total_files if total_files else 0.0

    now = datetime.utcnow()
    recent_start = now - timedelta(days=window_days)
    previous_start = recent_start - timedelta(days=window_days)

    recent_size = sum(
        item["size_bytes"]
        for item in image_stats
        if _as_datetime(item["created_at"]) >= recent_start
    )
    previous_size = sum(
        item["size_bytes"]
        for item in image_stats
        if previous_start <= _as_datetime(item["created_at"]) < recent_start
    )
    growth_window_pct = round(calculate_growth_percent(recent_size, previous_size), 2)

    distribution_map: dict[str, dict[str, Any]] = {}
    for item in image_stats:
        file_type = item["file_type"]
        current = distribution_map.get(file_type)
        if current is None:
            current = {"type": file_type, "count": 0, "size_gb": 0.0}
            distribution_map[file_type] = current
        current["count"] += 1
        current["size_gb"] = round(current["size_gb"] + bytes_to_gb(item["size_bytes"]), 4)

    top_files = sorted(image_stats, key=lambda item: item["size_bytes"], reverse=True)[: settings.metrics_top_files_limit]

    access_stmt = (
        select(
            AssetAccessLog.image_id,
            func.count().label("total_access_count"),
            func.sum(case((AssetAccessLog.event_type == "download", 1), else_=0)).label("download_access_count"),
            func.sum(case((AssetAccessLog.event_type != "download", 1), else_=0)).label("ogc_access_count"),
            func.max(AssetAccessLog.created_at).label("last_access_at"),
        )
        .where(AssetAccessLog.tenant_id == tenant_id)
        .where(AssetAccessLog.created_at >= recent_start)
        .group_by(AssetAccessLog.image_id)
    )
    if access_type == "download":
        access_stmt = access_stmt.having(
            func.sum(case((AssetAccessLog.event_type == "download", 1), else_=0)) > 0
        ).order_by(
            func.sum(case((AssetAccessLog.event_type == "download", 1), else_=0)).desc(),
            func.max(AssetAccessLog.created_at).desc(),
        )
    elif access_type == "ogc":
        access_stmt = access_stmt.having(
            func.sum(case((AssetAccessLog.event_type != "download", 1), else_=0)) > 0
        ).order_by(
            func.sum(case((AssetAccessLog.event_type != "download", 1), else_=0)).desc(),
            func.max(AssetAccessLog.created_at).desc(),
        )
    else:
        access_stmt = access_stmt.order_by(
            func.count().desc(),
            func.max(AssetAccessLog.created_at).desc(),
        )
    access_stmt = access_stmt.limit(settings.metrics_top_files_limit)
    access_rows = await db.execute(access_stmt)
    access_data = list(access_rows.all())
    image_lookup = {item["id"]: item for item in image_stats}

    def _selected_access_count(row: Any) -> int:
        if access_type == "download":
            return int(row.download_access_count or 0)
        if access_type == "ogc":
            return int(row.ogc_access_count or 0)
        return int(row.total_access_count or 0)

    top_accessed = [
        {
            "id": row.image_id,
            "filename": image_lookup.get(row.image_id, {}).get("filename", "unknown"),
            "accesses": _selected_access_count(row),
            "download_accesses": int(row.download_access_count or 0),
            "ogc_accesses": int(row.ogc_access_count or 0),
        }
        for row in access_data
    ]

    return {
        "tenant_id": tenant_id,
        "window_days": window_days,
        "access_type": access_type,
        "total_files": total_files,
        "total_size_gb": round(bytes_to_gb(total_size_bytes), 4),
        "avg_size_mb": round(avg_size_mb, 2),
        "growth_window_pct": growth_window_pct,
        "growth_30_days": growth_window_pct if window_days == 30 else None,
        "distribution_by_type": sorted(distribution_map.values(), key=lambda item: item["count"], reverse=True),
        "top_files": [
            {
                "id": item["id"],
                "filename": item["filename"],
                "size_mb": round(bytes_to_mb(item["size_bytes"]), 2),
                "created_at": _as_datetime(item["created_at"]).isoformat(),
            }
            for item in top_files
        ],
        "top_accessed": top_accessed,
        "usage_timeseries": _build_usage_timeseries(image_stats, window_days),
    }
