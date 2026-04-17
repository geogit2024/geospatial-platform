from typing import Literal, Optional
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import get_settings
from database import get_db
from models import AssetAccessLog, Image
from services.storage import generate_download_url
from services.queue import publish_upload_event

router = APIRouter(prefix="/images", tags=["images"])
log = logging.getLogger("api.images")
settings = get_settings()


def _normalize_geoserver_url(raw_url: Optional[str], service_path: str) -> Optional[str]:
    """
    Return public HTTPS GeoServer URL when GEOSERVER_PUBLIC_URL is configured.
    Falls back to the URL stored in DB.
    """
    if raw_url and raw_url.startswith("https://"):
        return raw_url

    public_base = settings.geoserver_public_url.rstrip("/")
    if not public_base:
        return raw_url

    if raw_url and "/geoserver/" in raw_url:
        suffix = raw_url.split("/geoserver/", 1)[1].lstrip("/")
        return f"{public_base}/{suffix}"

    return f"{public_base}/{service_path.lstrip('/')}"


class ImageResponse(BaseModel):
    id: str
    filename: str
    status: str
    crs: Optional[str] = None
    bbox: Optional[dict] = None
    layer_name: Optional[str] = None
    wms_url: Optional[str] = None
    wmts_url: Optional[str] = None
    wcs_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str

    @classmethod
    def from_orm(cls, img: Image) -> "ImageResponse":
        bbox = None
        if img.bbox_minx is not None:
            bbox = {
                "minx": img.bbox_minx,
                "miny": img.bbox_miny,
                "maxx": img.bbox_maxx,
                "maxy": img.bbox_maxy,
            }
        wms_url = _normalize_geoserver_url(img.wms_url, f"{settings.geoserver_workspace}/wms")
        wmts_url = _normalize_geoserver_url(img.wmts_url, "gwc/service/wmts")
        wcs_url = _normalize_geoserver_url(img.wcs_url, f"{settings.geoserver_workspace}/wcs")
        return cls(
            id=img.id,
            filename=img.filename,
            status=img.status,
            crs=img.crs,
            bbox=bbox,
            layer_name=img.layer_name,
            wms_url=wms_url,
            wmts_url=wmts_url,
            wcs_url=wcs_url,
            error_message=img.error_message,
            created_at=img.created_at.isoformat(),
            updated_at=img.updated_at.isoformat(),
        )


class ImageDownloadResponse(BaseModel):
    image_id: str
    source: Literal["raw", "processed"]
    bucket: str
    object_key: str
    download_url: str
    expires_in_seconds: int


@router.get("/", response_model=list[ImageResponse])
async def list_images(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[ImageResponse]:
    q = select(Image).order_by(Image.created_at.desc()).limit(limit).offset(offset)
    if status:
        q = q.where(Image.status == status)
    result = await db.execute(q)
    return [ImageResponse.from_orm(img) for img in result.scalars()]


@router.get("/{image_id}", response_model=ImageResponse)
async def get_image(
    image_id: str,
    db: AsyncSession = Depends(get_db),
) -> ImageResponse:
    image = await db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    return ImageResponse.from_orm(image)


@router.get("/{image_id}/download-url", response_model=ImageDownloadResponse)
async def get_image_download_url(
    image_id: str,
    source: Literal["raw", "processed"] = Query(default="raw"),
    db: AsyncSession = Depends(get_db),
) -> ImageDownloadResponse:
    image = await db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if source == "raw":
        object_key = image.original_key
        bucket = settings.storage_bucket_raw
    else:
        object_key = image.processed_key
        bucket = settings.storage_bucket_processed

    if not object_key:
        raise HTTPException(
            status_code=400,
            detail=f"Image has no {source} object key available for download",
        )

    download_url = generate_download_url(bucket=bucket, key=object_key)

    try:
        db.add(
            AssetAccessLog(
                tenant_id=settings.default_tenant_id,
                image_id=image.id,
                event_type="download",
            )
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        log.warning("Failed to register download access log for image %s: %s", image.id, exc)

    return ImageDownloadResponse(
        image_id=image.id,
        source=source,
        bucket=bucket,
        object_key=object_key,
        download_url=download_url,
        expires_in_seconds=settings.signed_url_expiry_seconds,
    )


async def _delete_geoserver_store(store_name: str) -> None:
    """Remove coverageStore (and its coverages) from GeoServer. Non-fatal on failure."""
    gs_base = settings.geoserver_url.rstrip("/")
    ws = settings.geoserver_workspace
    url = f"{gs_base}/rest/workspaces/{ws}/coveragestores/{store_name}.json?recurse=true"
    auth = (settings.geoserver_admin_user, settings.geoserver_admin_password)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.delete(url, auth=auth)
            if r.status_code not in (200, 404):
                log.warning(f"GeoServer DELETE store {store_name}: HTTP {r.status_code}")
    except Exception as e:
        log.warning(f"GeoServer store cleanup failed for {store_name}: {e}")


@router.post("/{image_id}/retry", status_code=202)
async def retry_image(image_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Re-queue a failed image for processing. Only valid for images in 'error' status."""
    image = await db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    if image.status not in ("error", "processing"):
        raise HTTPException(status_code=400, detail=f"Cannot retry image in status '{image.status}'")
    if not image.original_key:
        raise HTTPException(status_code=400, detail="Image has no original_key — cannot retry")

    image.status = "uploaded"
    image.error_message = None
    await db.commit()

    await publish_upload_event(
        image_id=image.id,
        raw_key=image.original_key,
        filename=image.filename,
    )
    return {"image_id": image.id, "status": "uploaded", "message": "Re-queued for processing"}


@router.delete("/{image_id}", status_code=204)
async def delete_image(image_id: str, db: AsyncSession = Depends(get_db)) -> None:
    image = await db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Remove GeoServer coverageStore if layer was published
    if image.layer_name:
        store_name = f"img_{image_id.replace('-', '_')}"
        await _delete_geoserver_store(store_name)

    await db.delete(image)
    await db.commit()
