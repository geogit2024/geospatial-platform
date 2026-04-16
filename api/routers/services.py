from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from models import Image, ProcessingStatus

router = APIRouter(prefix="/services", tags=["ogc-services"])
settings = get_settings()


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

    wms = image.wms_url
    wmts = image.wmts_url
    wcs = image.wcs_url

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


@router.get("/{image_id}/wms-proxy")
async def wms_proxy(
    image_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Proxy WMS GetMap/GetCapabilities via API HTTPS origin.

    Browser requests are same-origin (`/api/services/{id}/wms-proxy`), while the API
    fetches GeoServer over internal network (`GEOSERVER_URL`), avoiding mixed-content
    and invalid TLS issues on public :8080 endpoints.
    """
    image = await db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    if image.status != ProcessingStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail=f"Image not published: {image.status}")
    if not image.layer_name:
        raise HTTPException(status_code=409, detail="Published image has no layer_name")

    wms_endpoint = (
        f"{settings.geoserver_url.rstrip('/')}/{settings.geoserver_workspace}/wms"
    )

    params = dict(request.query_params)
    params.setdefault("service", "WMS")
    params.setdefault("request", "GetMap")
    params.setdefault("version", "1.1.1")
    params.setdefault("format", "image/png")
    params.setdefault("transparent", "true")
    request_name = str(params.get("request", "")).lower()
    if request_name != "getcapabilities":
        params["layers"] = image.layer_name

    auth = (settings.geoserver_admin_user, settings.geoserver_admin_password)
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            upstream = await client.get(wms_endpoint, params=params, auth=auth)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"WMS upstream error: {exc}") from exc

    headers: dict[str, str] = {}
    content_type = upstream.headers.get("content-type")
    cache_control = upstream.headers.get("cache-control")
    if content_type:
        headers["content-type"] = content_type
    if cache_control:
        headers["cache-control"] = cache_control

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=headers,
    )
