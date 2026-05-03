import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models import PlanFeature, TenantCostEstimateConfig, TenantPricing, TenantSubscription

settings = get_settings()

_RASTER_EXTENSIONS = {".tif", ".tiff", ".geotiff", ".jp2", ".img", ".jpg", ".jpeg"}
_VECTOR_EXTENSIONS = {".zip", ".kml", ".geojson", ".json"}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def normalize_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].strip().lower()


def classify_asset_type(*, extension: str, content_type: str) -> str:
    if extension in _VECTOR_EXTENSIONS:
        return "vector"
    if extension in _RASTER_EXTENSIONS:
        return "raster"

    normalized_type = (content_type or "").strip().lower()
    if "geo+json" in normalized_type or "json" in normalized_type:
        return "vector"
    return "raster"


def build_quick_analysis(*, filename: str, size_bytes: int, content_type: str) -> dict[str, Any]:
    extension = normalize_extension(filename)
    asset_type = classify_asset_type(extension=extension, content_type=content_type)
    size_gb = max(float(size_bytes), 0.0) / (1024.0 * 1024.0 * 1024.0)

    complexity_factor = 1.0
    if extension == ".jp2":
        complexity_factor = 1.25
    elif extension == ".zip":
        complexity_factor = 1.15

    return {
        "filename": filename,
        "extension": extension,
        "asset_type": asset_type,
        "size_bytes": int(max(size_bytes, 0)),
        "size_gb": round(size_gb, 6),
        "complexity_factor": complexity_factor,
        "analysis_mode": "quick",
    }


async def is_cost_estimate_enabled(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> bool:
    if settings.upload_cost_estimate_force_enabled:
        return True

    cfg_row = await db.execute(
        select(TenantCostEstimateConfig).where(TenantCostEstimateConfig.tenant_id == tenant_id)
    )
    cfg = cfg_row.scalar_one_or_none()
    if cfg is not None:
        return bool(cfg.is_enabled)

    feature_row = await db.execute(
        select(PlanFeature.is_enabled)
        .join(TenantSubscription, TenantSubscription.plan_id == PlanFeature.plan_id)
        .where(TenantSubscription.tenant_id == tenant_id)
        .where(PlanFeature.feature_key == settings.upload_cost_estimate_feature_key)
        .limit(1)
    )
    plan_feature_enabled = feature_row.scalar_one_or_none()
    if plan_feature_enabled is not None:
        return bool(plan_feature_enabled)

    return bool(settings.upload_cost_estimate_enabled_default)


async def resolve_tenant_pricing(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> dict[str, Any]:
    row = await db.execute(select(TenantPricing).where(TenantPricing.tenant_id == tenant_id))
    pricing = row.scalar_one_or_none()
    if pricing is None:
        return {
            "cost_per_gb_month": float(settings.cost_per_gb_month),
            "cost_per_process": float(settings.cost_per_process),
            "cost_per_download": float(settings.cost_per_download),
            "currency": settings.billing_currency,
        }
    return {
        "cost_per_gb_month": float(pricing.cost_per_gb_month),
        "cost_per_process": float(pricing.cost_per_process),
        "cost_per_download": float(pricing.cost_per_download),
        "currency": pricing.currency,
    }


def default_cost_assumptions() -> dict[str, Any]:
    return {
        "expected_monthly_downloads": int(settings.upload_cost_estimate_default_monthly_downloads),
        "avg_download_size_ratio": float(settings.upload_cost_estimate_default_avg_download_size_ratio),
        "processed_size_ratio_raster": float(settings.upload_cost_estimate_default_processed_size_ratio_raster),
        "processed_size_ratio_vector": float(settings.upload_cost_estimate_default_processed_size_ratio_vector),
        "processing_base_units": float(settings.upload_cost_estimate_default_processing_base_units),
        "processing_units_per_gb_raster": float(
            settings.upload_cost_estimate_default_processing_units_per_gb_raster
        ),
        "processing_units_per_gb_vector": float(
            settings.upload_cost_estimate_default_processing_units_per_gb_vector
        ),
        "uncertainty_min_factor": float(settings.upload_cost_estimate_default_uncertainty_min_factor),
        "uncertainty_max_factor": float(settings.upload_cost_estimate_default_uncertainty_max_factor),
    }


async def resolve_cost_assumptions(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> dict[str, Any]:
    row = await db.execute(
        select(TenantCostEstimateConfig).where(TenantCostEstimateConfig.tenant_id == tenant_id)
    )
    config = row.scalar_one_or_none()
    if config is None:
        return default_cost_assumptions()

    return {
        "expected_monthly_downloads": int(config.expected_monthly_downloads),
        "avg_download_size_ratio": float(config.avg_download_size_ratio),
        "processed_size_ratio_raster": float(config.processed_size_ratio_raster),
        "processed_size_ratio_vector": float(config.processed_size_ratio_vector),
        "processing_base_units": float(config.processing_base_units),
        "processing_units_per_gb_raster": float(config.processing_units_per_gb_raster),
        "processing_units_per_gb_vector": float(config.processing_units_per_gb_vector),
        "uncertainty_min_factor": float(config.uncertainty_min_factor),
        "uncertainty_max_factor": float(config.uncertainty_max_factor),
    }


def calculate_cost_estimate(
    *,
    analysis: dict[str, Any],
    pricing: dict[str, Any],
    assumptions: dict[str, Any],
    expected_monthly_downloads: int | None = None,
    avg_download_size_ratio: float | None = None,
) -> dict[str, Any]:
    size_gb = max(float(analysis.get("size_gb", 0.0)), 0.0)
    asset_type = str(analysis.get("asset_type") or "raster").lower()
    complexity = max(float(analysis.get("complexity_factor", 1.0)), 0.1)

    if asset_type == "vector":
        processed_ratio = float(assumptions["processed_size_ratio_vector"])
        units_per_gb = float(assumptions["processing_units_per_gb_vector"])
    else:
        processed_ratio = float(assumptions["processed_size_ratio_raster"])
        units_per_gb = float(assumptions["processing_units_per_gb_raster"])

    downloads = int(
        expected_monthly_downloads
        if expected_monthly_downloads is not None
        else assumptions["expected_monthly_downloads"]
    )
    downloads = max(downloads, 0)

    dl_ratio = float(
        avg_download_size_ratio
        if avg_download_size_ratio is not None
        else assumptions["avg_download_size_ratio"]
    )
    dl_ratio = _clamp(dl_ratio, 0.01, 2.0)

    processed_ratio = _clamp(processed_ratio, 0.05, 3.0)
    raw_gb = size_gb
    processed_gb = size_gb * processed_ratio
    total_storage_gb = raw_gb + processed_gb

    base_units = max(float(assumptions["processing_base_units"]), 0.0)
    processing_units = base_units + (size_gb * units_per_gb * complexity)

    storage_monthly = total_storage_gb * float(pricing["cost_per_gb_month"])
    processing_one_time = processing_units * float(pricing["cost_per_process"])
    publication_monthly = downloads * float(pricing["cost_per_download"])

    recurring_monthly_total = storage_monthly + publication_monthly
    first_month_total = processing_one_time + recurring_monthly_total

    min_factor = _clamp(float(assumptions["uncertainty_min_factor"]), 0.1, 1.0)
    max_factor = max(float(assumptions["uncertainty_max_factor"]), 1.0)
    first_month_range = {
        "minimum": round(first_month_total * min_factor, 2),
        "likely": round(first_month_total, 2),
        "maximum": round(first_month_total * max_factor, 2),
    }

    return {
        "currency": str(pricing["currency"]),
        "analysis_snapshot": {
            "asset_type": asset_type,
            "size_gb": round(size_gb, 6),
            "complexity_factor": round(complexity, 3),
        },
        "assumptions_used": {
            "expected_monthly_downloads": downloads,
            "avg_download_size_ratio": round(dl_ratio, 4),
            "processed_size_ratio": round(processed_ratio, 4),
        },
        "breakdown": {
            "processing_one_time": round(processing_one_time, 2),
            "storage_monthly": round(storage_monthly, 2),
            "publication_monthly": round(publication_monthly, 2),
            "recurring_monthly_total": round(recurring_monthly_total, 2),
            "first_month_total": round(first_month_total, 2),
            "first_month_range": first_month_range,
        },
        "resource_projection": {
            "raw_storage_gb": round(raw_gb, 6),
            "processed_storage_gb": round(processed_gb, 6),
            "total_storage_gb": round(total_storage_gb, 6),
            "processing_units": round(processing_units, 6),
        },
    }


def dumps_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"))


def loads_json(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    return json.loads(payload)
