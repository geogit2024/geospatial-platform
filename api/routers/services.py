from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Image, ProcessingStatus

router = APIRouter(prefix="/services", tags=["ogc-services"])


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

    return {
        "image_id": image.id,
        "layer": image.layer_name,
        "services": {
            "wms": {
                "url": image.wms_url,
                "getcapabilities": f"{image.wms_url}?service=WMS&version=1.3.0&request=GetCapabilities",
                "getmap_example": (
                    f"{image.wms_url}?service=WMS&version=1.3.0&request=GetMap"
                    f"&layers={image.layer_name}&bbox=-180,-90,180,90"
                    f"&width=800&height=400&crs=EPSG:4326&format=image/png"
                ),
            },
            "wmts": {
                "url": image.wmts_url,
                "getcapabilities": f"{image.wmts_url}?REQUEST=GetCapabilities",
            },
            "wcs": {
                "url": image.wcs_url,
                "getcapabilities": f"{image.wcs_url}?service=WCS&version=2.0.1&request=GetCapabilities",
            },
        },
        "bbox": {
            "minx": image.bbox_minx,
            "miny": image.bbox_miny,
            "maxx": image.bbox_maxx,
            "maxy": image.bbox_maxy,
        } if image.bbox_minx is not None else None,
    }
