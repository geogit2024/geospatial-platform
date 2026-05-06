import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from google.auth import exceptions as google_auth_exceptions
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from models import (
    Image,
    ProcessingStatus,
    TenantCostEstimateConfig,
    UploadCostEstimateSession,
)
from services.queue import publish_upload_event
from services.storage import generate_upload_url, generate_upload_url_for_bucket
from services.upload_cost_estimator import (
    build_quick_analysis,
    calculate_cost_estimate,
    default_cost_assumptions,
    dumps_json,
    is_cost_estimate_enabled,
    loads_json,
    resolve_cost_assumptions,
    resolve_tenant_pricing,
)
from services.processing_strategy import classify_processing_strategy
from services.worker_job_trigger import trigger_worker_job_best_effort

router = APIRouter(prefix="/upload", tags=["upload"])
settings = get_settings()

ALLOWED_EXTENSIONS = {
    ".tif",
    ".tiff",
    ".geotiff",
    ".jp2",
    ".img",
    ".jpg",
    ".jpeg",
    ".zip",
    ".kml",
    ".geojson",
    ".json",
}

# Normalize browser-supplied content-type to a predictable value per extension.
# GCS signed PUT URLs are scoped to the content-type used during signing.
_CONTENT_TYPE_MAP = {
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".geotiff": "image/tiff",
    ".jp2": "image/jp2",
    ".img": "application/octet-stream",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".zip": "application/zip",
    ".kml": "application/vnd.google-earth.kml+xml",
    ".geojson": "application/geo+json",
    ".json": "application/geo+json",
}


class UploadRequest(BaseModel):
    filename: str
    content_type: str = "image/tiff"
    size_bytes: int | None = None
    tenant_id: str | None = None


class UploadResponse(BaseModel):
    image_id: str
    upload_url: str
    raw_key: str
    content_type: str
    expires_in: int


class UploadConfirmRequest(BaseModel):
    image_id: str
    estimate_session_id: str | None = None


class CostEstimateConfigUpsertRequest(BaseModel):
    tenant_id: str | None = None
    is_enabled: bool = True
    expected_monthly_downloads: int = Field(default=100, ge=0, le=10_000_000)
    avg_download_size_ratio: float = Field(default=0.35, ge=0.01, le=2.0)
    processed_size_ratio_raster: float = Field(default=0.65, ge=0.05, le=3.0)
    processed_size_ratio_vector: float = Field(default=0.35, ge=0.05, le=3.0)
    processing_base_units: float = Field(default=1.0, ge=0.0, le=10_000.0)
    processing_units_per_gb_raster: float = Field(default=2.0, ge=0.01, le=10_000.0)
    processing_units_per_gb_vector: float = Field(default=1.2, ge=0.01, le=10_000.0)
    uncertainty_min_factor: float = Field(default=0.7, ge=0.1, le=1.0)
    uncertainty_max_factor: float = Field(default=1.4, ge=1.0, le=10.0)


class CostEstimateConfigResponse(BaseModel):
    tenant_id: str
    is_enabled: bool
    assumptions: dict[str, Any]
    source: str


class CostEstimateStartRequest(BaseModel):
    filename: str
    size_bytes: int = Field(gt=0)
    content_type: str = "application/octet-stream"
    tenant_id: str | None = None


class CostEstimateStartResponse(BaseModel):
    session_id: str
    tenant_id: str
    expires_at: datetime
    feature_enabled: bool
    analysis: dict[str, Any]
    estimate: dict[str, Any]
    temp_upload: dict[str, Any]


class CostEstimateCalculateRequest(BaseModel):
    session_id: str
    expected_monthly_downloads: int | None = Field(default=None, ge=0, le=10_000_000)
    avg_download_size_ratio: float | None = Field(default=None, ge=0.01, le=2.0)


class CostEstimateCalculateResponse(BaseModel):
    session_id: str
    tenant_id: str
    expires_at: datetime
    analysis: dict[str, Any]
    estimate: dict[str, Any]


class CostEstimateAcceptRequest(BaseModel):
    session_id: str
    expected_monthly_downloads: int | None = Field(default=None, ge=0, le=10_000_000)
    avg_download_size_ratio: float | None = Field(default=None, ge=0.01, le=2.0)


class CostEstimateAcceptResponse(BaseModel):
    session_id: str
    tenant_id: str
    status: str
    accepted_at: datetime
    expires_at: datetime
    analysis: dict[str, Any]
    estimate: dict[str, Any]


def _effective_tenant_id(tenant_id: str | None) -> str:
    return (tenant_id or settings.default_tenant_id).strip()


def _validate_upload_file_request(*, filename: str, size_bytes: int | None) -> tuple[str, str]:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == ".ecw":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Formato '.ecw' indisponivel neste ambiente de producao "
                "(driver GDAL ECW ausente). Converta para GeoTIFF (.tif) ou JP2."
            ),
        )
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type '{ext}' not supported. Allowed: {ALLOWED_EXTENSIONS}",
        )
    if size_bytes is not None:
        max_size = max(int(settings.upload_max_size_mb), 1) * 1024 * 1024
        if size_bytes > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"File too large ({size_bytes} bytes). "
                    f"Max allowed is {settings.upload_max_size_mb} MB."
                ),
            )
    return ext, _CONTENT_TYPE_MAP.get(ext, "application/octet-stream")


async def _get_active_cost_estimate_session(
    db: AsyncSession,
    *,
    session_id: str,
) -> UploadCostEstimateSession:
    session = await db.get(UploadCostEstimateSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost estimate session not found")
    if session.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Cost estimate session expired")
    return session


@router.post("/signed-url", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def get_signed_upload_url(
    request: UploadRequest,
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    ext, fallback_content_type = _validate_upload_file_request(
        filename=request.filename,
        size_bytes=request.size_bytes,
    )

    # Normalize content-type: browser may send application/octet-stream for .tif.
    content_type = _CONTENT_TYPE_MAP.get(ext, request.content_type or fallback_content_type)

    image_id = str(uuid.uuid4())
    raw_key = f"{image_id}/original{ext}"
    try:
        upload_url = generate_upload_url(raw_key, content_type)
    except google_auth_exceptions.GoogleAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Credenciais Google Cloud indisponiveis para gerar signed URL. "
                "No DEV, execute 'gcloud auth application-default login' no host "
                "e reinicie o container da API."
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Falha ao gerar signed URL no GCS: {exc}",
        ) from exc

    image = Image(
        id=image_id,
        tenant_id=request.tenant_id or settings.default_tenant_id,
        filename=request.filename,
        original_key=raw_key,
        status=ProcessingStatus.UPLOADING,
    )
    strategy = classify_processing_strategy(
        filename=request.filename,
        size_bytes=request.size_bytes,
        content_type=content_type,
    )
    for key, value in strategy.to_dict().items():
        setattr(image, key, value)
    db.add(image)
    await db.commit()

    return UploadResponse(
        image_id=image_id,
        upload_url=upload_url,
        raw_key=raw_key,
        content_type=content_type,
        expires_in=3600,
    )


@router.post("/confirm", status_code=status.HTTP_202_ACCEPTED)
async def confirm_upload(
    request: UploadConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    image = await db.get(Image, request.image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if image.status != ProcessingStatus.UPLOADING:
        raise HTTPException(status_code=400, detail=f"Image already in status: {image.status}")

    linked_estimate_session_id: str | None = None
    if request.estimate_session_id:
        estimate_session = await _get_active_cost_estimate_session(
            db,
            session_id=request.estimate_session_id,
        )
        if estimate_session.status != "accepted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Cost estimate session must be accepted before confirmation. "
                    f"Current status: {estimate_session.status}"
                ),
            )

        accepted_estimate = loads_json(estimate_session.accepted_estimate_json)
        if not accepted_estimate:
            accepted_estimate = loads_json(estimate_session.estimate_json)
            if not accepted_estimate:
                assumptions = await resolve_cost_assumptions(db, tenant_id=estimate_session.tenant_id)
                pricing = await resolve_tenant_pricing(db, tenant_id=estimate_session.tenant_id)
                analysis = loads_json(estimate_session.analysis_json) or build_quick_analysis(
                    filename=estimate_session.filename,
                    size_bytes=int(estimate_session.size_bytes),
                    content_type=estimate_session.content_type,
                )
                accepted_estimate = calculate_cost_estimate(
                    analysis=analysis,
                    pricing=pricing,
                    assumptions=assumptions,
                )

        accepted_at = estimate_session.accepted_at or datetime.utcnow()
        audit_input = loads_json(estimate_session.accepted_input_json)
        audit_input.update(
            {
                "confirmed_image_id": image.id,
                "confirmed_at": datetime.utcnow().isoformat(),
            }
        )
        estimate_session.accepted_at = accepted_at
        estimate_session.status = "consumed"
        estimate_session.accepted_estimate_json = dumps_json(accepted_estimate)
        estimate_session.accepted_input_json = dumps_json(audit_input)
        linked_estimate_session_id = estimate_session.id

    image.status = ProcessingStatus.UPLOADED
    await db.commit()

    await publish_upload_event(
        image_id=image.id,
        raw_key=image.original_key,
        filename=image.filename,
    )
    await trigger_worker_job_best_effort(f"upload confirmation image_id={image.id}")

    return {
        "image_id": image.id,
        "status": image.status,
        "message": "Processing queued",
        "estimate_session_id": linked_estimate_session_id,
    }


@router.get("/cost-estimate/config", response_model=CostEstimateConfigResponse)
async def get_cost_estimate_config(
    tenant_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> CostEstimateConfigResponse:
    effective_tenant = _effective_tenant_id(tenant_id)
    row = await db.execute(
        select(TenantCostEstimateConfig).where(TenantCostEstimateConfig.tenant_id == effective_tenant)
    )
    config = row.scalar_one_or_none()
    if config is None:
        enabled = await is_cost_estimate_enabled(db, tenant_id=effective_tenant)
        return CostEstimateConfigResponse(
            tenant_id=effective_tenant,
            is_enabled=enabled,
            assumptions=default_cost_assumptions(),
            source="default",
        )

    assumptions = await resolve_cost_assumptions(db, tenant_id=effective_tenant)
    return CostEstimateConfigResponse(
        tenant_id=effective_tenant,
        is_enabled=bool(config.is_enabled),
        assumptions=assumptions,
        source="tenant_override",
    )


@router.put("/cost-estimate/config", response_model=CostEstimateConfigResponse)
async def upsert_cost_estimate_config(
    request: CostEstimateConfigUpsertRequest,
    db: AsyncSession = Depends(get_db),
) -> CostEstimateConfigResponse:
    effective_tenant = _effective_tenant_id(request.tenant_id)
    row = await db.execute(
        select(TenantCostEstimateConfig).where(TenantCostEstimateConfig.tenant_id == effective_tenant)
    )
    config = row.scalar_one_or_none()
    if config is None:
        config = TenantCostEstimateConfig(tenant_id=effective_tenant)
        db.add(config)

    config.is_enabled = bool(request.is_enabled)
    config.expected_monthly_downloads = int(request.expected_monthly_downloads)
    config.avg_download_size_ratio = float(request.avg_download_size_ratio)
    config.processed_size_ratio_raster = float(request.processed_size_ratio_raster)
    config.processed_size_ratio_vector = float(request.processed_size_ratio_vector)
    config.processing_base_units = float(request.processing_base_units)
    config.processing_units_per_gb_raster = float(request.processing_units_per_gb_raster)
    config.processing_units_per_gb_vector = float(request.processing_units_per_gb_vector)
    config.uncertainty_min_factor = float(request.uncertainty_min_factor)
    config.uncertainty_max_factor = float(request.uncertainty_max_factor)
    await db.commit()

    assumptions = await resolve_cost_assumptions(db, tenant_id=effective_tenant)
    return CostEstimateConfigResponse(
        tenant_id=effective_tenant,
        is_enabled=bool(config.is_enabled),
        assumptions=assumptions,
        source="tenant_override",
    )


@router.post(
    "/cost-estimate/start",
    response_model=CostEstimateStartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_cost_estimate(
    request: CostEstimateStartRequest,
    db: AsyncSession = Depends(get_db),
) -> CostEstimateStartResponse:
    effective_tenant = _effective_tenant_id(request.tenant_id)
    feature_enabled = await is_cost_estimate_enabled(db, tenant_id=effective_tenant)
    if not feature_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Estimativa de custo pre-processamento desabilitada para este tenant. "
                "Ative em /api/upload/cost-estimate/config."
            ),
        )

    ext, normalized_content_type = _validate_upload_file_request(
        filename=request.filename,
        size_bytes=request.size_bytes,
    )
    analysis = build_quick_analysis(
        filename=request.filename,
        size_bytes=request.size_bytes,
        content_type=request.content_type,
    )
    pricing = await resolve_tenant_pricing(db, tenant_id=effective_tenant)
    assumptions = await resolve_cost_assumptions(db, tenant_id=effective_tenant)
    estimate = calculate_cost_estimate(
        analysis=analysis,
        pricing=pricing,
        assumptions=assumptions,
    )

    session_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(
        minutes=max(int(settings.upload_cost_estimate_session_ttl_minutes), 1)
    )

    temp_bucket = settings.upload_cost_estimate_temp_bucket.strip() or settings.storage_bucket_raw
    temp_prefix = settings.upload_cost_estimate_temp_prefix.strip().strip("/")
    suffix = ext or ".bin"
    temp_object_key = f"{temp_prefix}/{effective_tenant}/{session_id}/analysis{suffix}"
    temp_upload_url = generate_upload_url_for_bucket(
        bucket_name=temp_bucket,
        key=temp_object_key,
        content_type=_CONTENT_TYPE_MAP.get(ext, request.content_type or normalized_content_type),
        expires_in_seconds=settings.upload_cost_estimate_temp_signed_url_expiry_seconds,
    )

    db.add(
        UploadCostEstimateSession(
            id=session_id,
            tenant_id=effective_tenant,
            filename=request.filename,
            content_type=request.content_type or normalized_content_type,
            size_bytes=request.size_bytes,
            file_extension=analysis.get("extension"),
            asset_type=analysis.get("asset_type"),
            temp_bucket=temp_bucket,
            temp_object_key=temp_object_key,
            status="estimated",
            analysis_json=dumps_json(analysis),
            assumptions_json=dumps_json(assumptions),
            estimate_json=dumps_json(estimate),
            expires_at=expires_at,
        )
    )
    await db.commit()

    return CostEstimateStartResponse(
        session_id=session_id,
        tenant_id=effective_tenant,
        expires_at=expires_at,
        feature_enabled=feature_enabled,
        analysis=analysis,
        estimate=estimate,
        temp_upload={
            "bucket": temp_bucket,
            "object_key": temp_object_key,
            "upload_url": temp_upload_url,
            "expires_in": int(settings.upload_cost_estimate_temp_signed_url_expiry_seconds),
        },
    )


@router.post("/cost-estimate/accept", response_model=CostEstimateAcceptResponse)
async def accept_cost_estimate_for_session(
    request: CostEstimateAcceptRequest,
    db: AsyncSession = Depends(get_db),
) -> CostEstimateAcceptResponse:
    session = await _get_active_cost_estimate_session(db, session_id=request.session_id)
    if session.status == "consumed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cost estimate session already consumed by a processed upload",
        )

    analysis = loads_json(session.analysis_json)
    if not analysis:
        analysis = build_quick_analysis(
            filename=session.filename,
            size_bytes=int(session.size_bytes),
            content_type=session.content_type,
        )

    assumptions = await resolve_cost_assumptions(db, tenant_id=session.tenant_id)
    pricing = await resolve_tenant_pricing(db, tenant_id=session.tenant_id)
    estimate = calculate_cost_estimate(
        analysis=analysis,
        pricing=pricing,
        assumptions=assumptions,
        expected_monthly_downloads=request.expected_monthly_downloads,
        avg_download_size_ratio=request.avg_download_size_ratio,
    )

    accepted_at = session.accepted_at or datetime.utcnow()
    session.status = "accepted"
    session.analysis_json = dumps_json(analysis)
    session.assumptions_json = dumps_json(assumptions)
    session.estimate_json = dumps_json(estimate)
    session.accepted_estimate_json = dumps_json(estimate)
    session.accepted_input_json = dumps_json(
        {
            "expected_monthly_downloads": request.expected_monthly_downloads,
            "avg_download_size_ratio": request.avg_download_size_ratio,
        }
    )
    session.accepted_at = accepted_at
    await db.commit()

    return CostEstimateAcceptResponse(
        session_id=session.id,
        tenant_id=session.tenant_id,
        status=session.status,
        accepted_at=accepted_at,
        expires_at=session.expires_at,
        analysis=analysis,
        estimate=estimate,
    )


@router.post("/cost-estimate/calculate", response_model=CostEstimateCalculateResponse)
async def calculate_cost_estimate_for_session(
    request: CostEstimateCalculateRequest,
    db: AsyncSession = Depends(get_db),
) -> CostEstimateCalculateResponse:
    session = await _get_active_cost_estimate_session(db, session_id=request.session_id)
    if session.status in {"accepted", "consumed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cost estimate session already finalized. "
                "Create a new estimate session to change assumptions."
            ),
        )

    analysis = loads_json(session.analysis_json)
    if not analysis:
        analysis = build_quick_analysis(
            filename=session.filename,
            size_bytes=int(session.size_bytes),
            content_type=session.content_type,
        )

    assumptions = await resolve_cost_assumptions(db, tenant_id=session.tenant_id)
    pricing = await resolve_tenant_pricing(db, tenant_id=session.tenant_id)
    estimate = calculate_cost_estimate(
        analysis=analysis,
        pricing=pricing,
        assumptions=assumptions,
        expected_monthly_downloads=request.expected_monthly_downloads,
        avg_download_size_ratio=request.avg_download_size_ratio,
    )

    session.status = "estimated"
    session.analysis_json = dumps_json(analysis)
    session.assumptions_json = dumps_json(assumptions)
    session.estimate_json = dumps_json(estimate)
    await db.commit()

    return CostEstimateCalculateResponse(
        session_id=session.id,
        tenant_id=session.tenant_id,
        expires_at=session.expires_at,
        analysis=analysis,
        estimate=estimate,
    )
