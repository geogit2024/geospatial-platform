import asyncio
import time
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from services.gcp_billing import BillingExportConfigError
from services.metrics_costs import get_cost_metrics, simulate_costs
from services.metrics_upload_cost_estimates import (
    cleanup_expired_upload_cost_estimate_sessions,
    get_upload_cost_estimate_audit,
)
from services.metrics_storage import get_storage_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])
settings = get_settings()
_storage_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cost_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_upload_cost_estimate_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_storage_cache_lock = asyncio.Lock()
_cost_cache_lock = asyncio.Lock()
_upload_cost_estimate_cache_lock = asyncio.Lock()


class DistributionItem(BaseModel):
    type: str
    count: int
    size_gb: float


class TopFileItem(BaseModel):
    id: str
    filename: str
    size_mb: float
    created_at: str


class TopAccessedItem(BaseModel):
    id: str
    filename: str
    accesses: int
    download_accesses: int
    ogc_accesses: int


class UsageSeriesItem(BaseModel):
    date: str
    files_added: int
    added_gb: float
    total_gb: float


class StorageMetricsResponse(BaseModel):
    tenant_id: str
    window_days: int
    access_type: Literal["all", "download", "ogc"] = "all"
    total_files: int
    total_size_gb: float
    avg_size_mb: float
    growth_window_pct: float
    growth_30_days: Optional[float] = None
    distribution_by_type: list[DistributionItem]
    top_files: list[TopFileItem]
    top_accessed: list[TopAccessedItem]
    usage_timeseries: list[UsageSeriesItem]


class CostSeriesItem(BaseModel):
    date: str
    value: float
    storage: float
    processing: float
    downloads: float


class CostMetricsResponse(BaseModel):
    tenant_id: str
    window_days: int
    cost_source: str
    cost_source_is_real: bool
    cost_source_table: Optional[str] = None
    currency: str
    cost_per_gb: float
    cost_per_process: float
    cost_per_download: float
    storage_cost_month: float
    processing_cost: float
    download_cost: float
    estimated_total: float
    projection_30_days: float
    cost_timeseries: list[CostSeriesItem]


class CostSimulationRequest(BaseModel):
    tenant_id: Optional[str] = None
    window_days: int = Field(default=settings.metrics_default_window_days, ge=1, le=settings.metrics_max_window_days)
    extra_gb: float = Field(default=0.0, ge=0.0)
    extra_processes: int = Field(default=0, ge=0)
    extra_downloads: int = Field(default=0, ge=0)


class CostSimulationResponse(BaseModel):
    tenant_id: str
    currency: str
    current_estimated_total: float
    extra_storage_cost: float
    extra_processing_cost: float
    extra_download_cost: float
    extra_total: float
    new_estimated_total: float


class UploadCostEstimateStatusItem(BaseModel):
    status: str
    count: int


class UploadCostEstimateSessionItem(BaseModel):
    session_id: str
    status: str
    filename: str
    asset_type: str
    size_gb: float
    expected_monthly_downloads: int
    first_month_total: float
    recurring_monthly_total: float
    currency: str
    created_at: str | None = None
    accepted_at: str | None = None
    expires_at: str | None = None


class UploadCostEstimateAuditResponse(BaseModel):
    tenant_id: str
    window_days: int
    totals: dict[str, int]
    rates: dict[str, float]
    accepted_averages: dict[str, Any]
    status_breakdown: list[UploadCostEstimateStatusItem]
    recent_sessions: list[UploadCostEstimateSessionItem]


class UploadCostEstimateCleanupRequest(BaseModel):
    tenant_id: str | None = None
    limit: int = Field(default=500, ge=1, le=2000)


class UploadCostEstimateCleanupResponse(BaseModel):
    tenant_id: str
    deleted_count: int
    limit: int
    executed_at: str
    oldest_expires_at: str | None = None
    newest_expires_at: str | None = None


def _cache_deadline(ttl_seconds: int) -> float:
    ttl = max(int(ttl_seconds), 1)
    return time.monotonic() + ttl


def _storage_cache_key(*, tenant_id: str, access_type: str, window_days: int) -> str:
    return f"{tenant_id}|{access_type}|{window_days}"


def _cost_cache_key(*, tenant_id: str, window_days: int) -> str:
    return f"{tenant_id}|{window_days}"


def _upload_cost_estimate_cache_key(*, tenant_id: str, window_days: int, limit: int) -> str:
    return f"{tenant_id}|{window_days}|{limit}"


async def _get_cached_storage_metrics(
    db: AsyncSession,
    *,
    tenant_id: str,
    access_type: Literal["all", "download", "ogc"],
    window_days: int,
) -> dict[str, Any]:
    key = _storage_cache_key(tenant_id=tenant_id, access_type=access_type, window_days=window_days)
    now = time.monotonic()
    entry = _storage_cache.get(key)
    if entry and entry[0] > now:
        return entry[1]

    async with _storage_cache_lock:
        entry = _storage_cache.get(key)
        if entry and entry[0] > time.monotonic():
            return entry[1]

        payload = await get_storage_metrics(
            db,
            tenant_id=tenant_id,
            window_days=window_days,
            access_type=access_type,
        )
        _storage_cache[key] = (
            _cache_deadline(settings.metrics_storage_cache_ttl_seconds),
            payload,
        )
        return payload


async def _get_cached_cost_metrics(
    db: AsyncSession,
    *,
    tenant_id: str,
    window_days: int,
) -> dict[str, Any]:
    key = _cost_cache_key(tenant_id=tenant_id, window_days=window_days)
    now = time.monotonic()
    entry = _cost_cache.get(key)
    if entry and entry[0] > now:
        return entry[1]

    async with _cost_cache_lock:
        entry = _cost_cache.get(key)
        if entry and entry[0] > time.monotonic():
            return entry[1]

        payload = await get_cost_metrics(db, tenant_id=tenant_id, window_days=window_days)
        _cost_cache[key] = (
            _cache_deadline(settings.metrics_cost_cache_ttl_seconds),
            payload,
        )
        return payload


async def _get_cached_upload_cost_estimate_audit(
    db: AsyncSession,
    *,
    tenant_id: str,
    window_days: int,
    limit: int,
) -> dict[str, Any]:
    key = _upload_cost_estimate_cache_key(tenant_id=tenant_id, window_days=window_days, limit=limit)
    now = time.monotonic()
    entry = _upload_cost_estimate_cache.get(key)
    if entry and entry[0] > now:
        return entry[1]

    async with _upload_cost_estimate_cache_lock:
        entry = _upload_cost_estimate_cache.get(key)
        if entry and entry[0] > time.monotonic():
            return entry[1]

        payload = await get_upload_cost_estimate_audit(
            db,
            tenant_id=tenant_id,
            window_days=window_days,
            limit=limit,
        )
        _upload_cost_estimate_cache[key] = (
            _cache_deadline(settings.metrics_storage_cache_ttl_seconds),
            payload,
        )
        return payload


@router.get("/storage", response_model=StorageMetricsResponse)
async def read_storage_metrics(
    tenant_id: str | None = Query(default=None, description="Tenant external id"),
    access_type: Literal["all", "download", "ogc"] = Query(
        default="all",
        description="Filter ranking by access type: all, download, or ogc service calls",
    ),
    window_days: int = Query(
        default=settings.metrics_default_window_days,
        ge=1,
        le=settings.metrics_max_window_days,
        description="Window size in days for usage and growth metrics",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    effective_tenant = (tenant_id or settings.default_tenant_id).strip()
    return await _get_cached_storage_metrics(
        db,
        tenant_id=effective_tenant,
        window_days=window_days,
        access_type=access_type,
    )


@router.get("/costs", response_model=CostMetricsResponse)
async def read_cost_metrics(
    tenant_id: str | None = Query(default=None, description="Tenant external id"),
    window_days: int = Query(
        default=settings.metrics_default_window_days,
        ge=1,
        le=settings.metrics_max_window_days,
        description="Window size in days for cost aggregation",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    effective_tenant = (tenant_id or settings.default_tenant_id).strip()
    try:
        return await _get_cached_cost_metrics(
            db,
            tenant_id=effective_tenant,
            window_days=window_days,
        )
    except BillingExportConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/costs/simulate", response_model=CostSimulationResponse)
async def simulate_cost_metrics(
    payload: CostSimulationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    effective_tenant = (payload.tenant_id or settings.default_tenant_id).strip()
    try:
        current = await _get_cached_cost_metrics(
            db,
            tenant_id=effective_tenant,
            window_days=payload.window_days,
        )
    except BillingExportConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    simulation = simulate_costs(
        current_total=float(current["estimated_total"]),
        cost_per_gb=float(current["cost_per_gb"]),
        cost_per_process=float(current["cost_per_process"]),
        cost_per_download=float(current["cost_per_download"]),
        extra_gb=payload.extra_gb,
        extra_processes=payload.extra_processes,
        extra_downloads=payload.extra_downloads,
    )

    return {
        "tenant_id": effective_tenant,
        "currency": current["currency"],
        "current_estimated_total": float(current["estimated_total"]),
        **simulation,
    }


@router.get("/upload-cost-estimates", response_model=UploadCostEstimateAuditResponse)
async def read_upload_cost_estimate_audit(
    tenant_id: str | None = Query(default=None, description="Tenant external id"),
    window_days: int = Query(
        default=settings.metrics_default_window_days,
        ge=1,
        le=settings.metrics_max_window_days,
        description="Window size in days for estimate audit aggregation",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of recent sessions in response",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    effective_tenant = (tenant_id or settings.default_tenant_id).strip()
    return await _get_cached_upload_cost_estimate_audit(
        db,
        tenant_id=effective_tenant,
        window_days=window_days,
        limit=limit,
    )


@router.post("/upload-cost-estimates/cleanup", response_model=UploadCostEstimateCleanupResponse)
async def cleanup_upload_cost_estimates(
    payload: UploadCostEstimateCleanupRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    effective_tenant = (payload.tenant_id or settings.default_tenant_id).strip()
    response = await cleanup_expired_upload_cost_estimate_sessions(
        db,
        tenant_id=effective_tenant,
        limit=payload.limit,
    )

    # Keep dashboard metrics coherent immediately after cleanup.
    async with _upload_cost_estimate_cache_lock:
        keys = [key for key in _upload_cost_estimate_cache if key.startswith(f"{effective_tenant}|")]
        for key in keys:
            _upload_cost_estimate_cache.pop(key, None)

    return response
