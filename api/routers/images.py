from typing import Optional
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import get_settings
from database import get_db
from models import Image

router = APIRouter(prefix="/images", tags=["images"])
log = logging.getLogger("api.images")
settings = get_settings()


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
        return cls(
            id=img.id,
            filename=img.filename,
            status=img.status,
            crs=img.crs,
            bbox=bbox,
            layer_name=img.layer_name,
            wms_url=img.wms_url,
            wmts_url=img.wmts_url,
            wcs_url=img.wcs_url,
            error_message=img.error_message,
            created_at=img.created_at.isoformat(),
            updated_at=img.updated_at.isoformat(),
        )


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
async def get_image(image_id: str, db: AsyncSession = Depends(get_db)) -> ImageResponse:
    image = await db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    return ImageResponse.from_orm(image)


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
