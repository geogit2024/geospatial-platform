from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models import AssetAccessLog, Image, TenantPricing
from services.gcp_billing import get_billing_cost_metrics_from_export
from services.metrics_storage import get_storage_metrics

settings = get_settings()


def calculate_storage_cost(total_size_gb: float, cost_per_gb_month: float) -> float:
    return total_size_gb * cost_per_gb_month


def calculate_processing_cost(process_count: int, cost_per_process: float) -> float:
    return process_count * cost_per_process


def calculate_download_cost(download_count: int, cost_per_download: float) -> float:
    return download_count * cost_per_download


def calculate_projection_30_days(cost_timeseries: list[dict[str, Any]], fallback_total: float) -> float:
    if not cost_timeseries:
        return fallback_total

    daily_values = [float(item.get("value", 0.0)) for item in cost_timeseries]
    avg_daily = mean(daily_values) if daily_values else 0.0
    return avg_daily * 30


async def _resolve_pricing(db: AsyncSession, tenant_id: str) -> dict[str, Any]:
    row = await db.execute(select(TenantPricing).where(TenantPricing.tenant_id == tenant_id))
    pricing = row.scalar_one_or_none()

    if pricing is None:
        return {
            "cost_per_gb_month": settings.cost_per_gb_month,
            "cost_per_process": settings.cost_per_process,
            "cost_per_download": settings.cost_per_download,
            "currency": settings.billing_currency,
        }

    return {
        "cost_per_gb_month": float(pricing.cost_per_gb_month),
        "cost_per_process": float(pricing.cost_per_process),
        "cost_per_download": float(pricing.cost_per_download),
        "currency": pricing.currency,
    }


async def _downloads_by_day(db: AsyncSession, tenant_id: str, start: datetime) -> dict[date, int]:
    stmt = (
        select(func.date(AssetAccessLog.created_at).label("day"), func.count().label("total"))
        .where(AssetAccessLog.tenant_id == tenant_id)
        .where(AssetAccessLog.event_type == "download")
        .where(AssetAccessLog.created_at >= start)
        .group_by(func.date(AssetAccessLog.created_at))
    )
    result = await db.execute(stmt)
    return {row.day: int(row.total) for row in result.all()}


async def _processes_by_day(db: AsyncSession, start: datetime) -> dict[date, int]:
    # NOTE: images table is still global (no tenant_id yet).
    stmt = (
        select(func.date(Image.created_at).label("day"), func.count().label("total"))
        .where(Image.created_at >= start)
        .group_by(func.date(Image.created_at))
    )
    result = await db.execute(stmt)
    return {row.day: int(row.total) for row in result.all()}


async def _window_counts(db: AsyncSession, tenant_id: str, start: datetime) -> tuple[int, int]:
    downloads_stmt = (
        select(func.count())
        .select_from(AssetAccessLog)
        .where(AssetAccessLog.tenant_id == tenant_id)
        .where(AssetAccessLog.event_type == "download")
        .where(AssetAccessLog.created_at >= start)
    )
    downloads = int((await db.execute(downloads_stmt)).scalar() or 0)

    # NOTE: images table is still global (no tenant_id yet).
    process_stmt = select(func.count()).select_from(Image).where(Image.created_at >= start)
    processes = int((await db.execute(process_stmt)).scalar() or 0)

    return processes, downloads


async def get_cost_metrics(
    db: AsyncSession,
    *,
    tenant_id: str,
    window_days: int,
) -> dict[str, Any]:
    storage = await get_storage_metrics(db, tenant_id=tenant_id, window_days=window_days)
    total_size_gb = float(storage["total_size_gb"])
    now = datetime.utcnow()
    start = now - timedelta(days=window_days)

    process_count, download_count = await _window_counts(db, tenant_id, start)
    source = settings.billing_cost_source.strip().lower()
    source_is_real = source == "gcp_billing_export"
    source_table: str | None = None

    if source == "gcp_billing_export":
        billing = await get_billing_cost_metrics_from_export(
            window_days=window_days,
            project_id=settings.gcp_project_id.strip(),
        )
        source_table = str(billing.get("table_id") or "")

        storage_cost_month = float(billing["month_storage"])
        processing_cost = float(billing["window_processing"])
        download_cost = float(billing["window_downloads"])
        estimated_total = float(billing["month_total"])
        projection_30_days = float(billing["projection_30_days"])
        cost_timeseries = billing["cost_timeseries"]
        currency = str(billing["currency"])

        cost_per_gb_month = (storage_cost_month / total_size_gb) if total_size_gb > 0 else 0.0
        cost_per_process = (processing_cost / process_count) if process_count > 0 else 0.0
        cost_per_download = (download_cost / download_count) if download_count > 0 else 0.0
    else:
        pricing = await _resolve_pricing(db, tenant_id)

        storage_cost_month = calculate_storage_cost(total_size_gb, pricing["cost_per_gb_month"])
        processing_cost = calculate_processing_cost(process_count, pricing["cost_per_process"])
        download_cost = calculate_download_cost(download_count, pricing["cost_per_download"])
        estimated_total = storage_cost_month + processing_cost + download_cost

        downloads_by_day = await _downloads_by_day(db, tenant_id, start)
        processes_by_day = await _processes_by_day(db, start)

        usage_timeseries = storage["usage_timeseries"]
        cost_timeseries: list[dict[str, Any]] = []
        for point in usage_timeseries:
            day = date.fromisoformat(point["date"])
            storage_daily = (float(point["total_gb"]) * pricing["cost_per_gb_month"]) / 30
            process_daily = processes_by_day.get(day, 0) * pricing["cost_per_process"]
            download_daily = downloads_by_day.get(day, 0) * pricing["cost_per_download"]
            total_daily = storage_daily + process_daily + download_daily

            cost_timeseries.append(
                {
                    "date": point["date"],
                    "value": round(total_daily, 4),
                    "storage": round(storage_daily, 4),
                    "processing": round(process_daily, 4),
                    "downloads": round(download_daily, 4),
                }
            )

        projection_30_days = calculate_projection_30_days(cost_timeseries, estimated_total)
        currency = str(pricing["currency"])
        cost_per_gb_month = float(pricing["cost_per_gb_month"])
        cost_per_process = float(pricing["cost_per_process"])
        cost_per_download = float(pricing["cost_per_download"])

    return {
        "tenant_id": tenant_id,
        "window_days": window_days,
        "cost_source": source,
        "cost_source_is_real": source_is_real,
        "cost_source_table": source_table,
        "currency": currency,
        "cost_per_gb": round(cost_per_gb_month, 4),
        "cost_per_process": round(cost_per_process, 4),
        "cost_per_download": round(cost_per_download, 4),
        "storage_cost_month": round(storage_cost_month, 2),
        "processing_cost": round(processing_cost, 6),
        "download_cost": round(download_cost, 6),
        "estimated_total": round(estimated_total, 2),
        "projection_30_days": round(projection_30_days, 2),
        "cost_timeseries": cost_timeseries,
    }


def simulate_costs(
    *,
    current_total: float,
    cost_per_gb: float,
    cost_per_process: float,
    cost_per_download: float,
    extra_gb: float,
    extra_processes: int,
    extra_downloads: int,
) -> dict[str, Any]:
    extra_storage = calculate_storage_cost(extra_gb, cost_per_gb)
    extra_processing = calculate_processing_cost(extra_processes, cost_per_process)
    extra_download = calculate_download_cost(extra_downloads, cost_per_download)
    extra_total = extra_storage + extra_processing + extra_download

    return {
        "extra_storage_cost": round(extra_storage, 2),
        "extra_processing_cost": round(extra_processing, 2),
        "extra_download_cost": round(extra_download, 2),
        "extra_total": round(extra_total, 2),
        "new_estimated_total": round(current_total + extra_total, 2),
    }
