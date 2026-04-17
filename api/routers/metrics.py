from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from services.gcp_billing import BillingExportConfigError
from services.metrics_costs import get_cost_metrics, simulate_costs
from services.metrics_storage import get_storage_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])
settings = get_settings()


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


class UsageSeriesItem(BaseModel):
    date: str
    files_added: int
    added_gb: float
    total_gb: float


class StorageMetricsResponse(BaseModel):
    tenant_id: str
    window_days: int
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


@router.get("/storage", response_model=StorageMetricsResponse)
async def read_storage_metrics(
    tenant_id: str | None = Query(default=None, description="Tenant external id"),
    window_days: int = Query(
        default=settings.metrics_default_window_days,
        ge=1,
        le=settings.metrics_max_window_days,
        description="Window size in days for usage and growth metrics",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    effective_tenant = (tenant_id or settings.default_tenant_id).strip()
    return await get_storage_metrics(db, tenant_id=effective_tenant, window_days=window_days)


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
        return await get_cost_metrics(db, tenant_id=effective_tenant, window_days=window_days)
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
        current = await get_cost_metrics(db, tenant_id=effective_tenant, window_days=payload.window_days)
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
