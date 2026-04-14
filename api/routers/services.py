from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Image, ProcessingStatus

router = APIRouter(prefix="/services", tags=["ogc-services"])


def _https(url: str) -> str:
    """Ensure URL uses HTTPS — ArcGIS Online and most GIS clients require it."""
    if url and url.startswith("http://"):
        return "https://" + url[7:]
    return url


@router.get("/{image_id}/ogc")
async def get_ogc_services(image_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    image = await db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if image.status != ProcessingStatus.PUBLISHED:
        raise HTTPException(
            status_code=409,
            detail=f"Image not yet published. Current status: {image.status}",
        )

    wms  = _https(image.wms_url)
    wmts = _https(image.wmts_url)
    wcs  = _https(image.wcs_url)

    return {
        "image_id": image.id,
        "layer": image.layer_name,
        "services": {
            "wms": {
                "url": wms,
                "getcapabilities": f"{wms}?service=WMS&version=1.3.0&request=GetCapabilities",
                "getmap_example": (
                    f"{wms}?service=WMS&version=1.3.0&request=GetMap"
                    f"&layers={image.layer_name}&bbox=-180,-90,180,90"
                    f"&width=800&height=400&crs=EPSG:4326&format=image/png"
                ),
            },
            "wmts": {
                "url": wmts,
                "getcapabilities": f"{wmts}?REQUEST=GetCapabilities",
            },
            "wcs": {
                "url": wcs,
                "getcapabilities": f"{wcs}?service=WCS&version=2.0.1&request=GetCapabilities",
            },
        },
        "bbox": {
            "minx": image.bbox_minx,
            "miny": image.bbox_miny,
            "maxx": image.bbox_maxx,
            "maxy": image.bbox_maxy,
        } if image.bbox_minx is not None else None,
    }
