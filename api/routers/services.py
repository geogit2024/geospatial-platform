import httpx
import re
import xml.etree.ElementTree as ET
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from models import Image, ProcessingStatus

router = APIRouter(prefix="/services", tags=["ogc-services"])
settings = get_settings()


def _header_first_value(request: Request, header_name: str) -> str | None:
    value = request.headers.get(header_name)
    if not value:
        return None
    return value.split(",")[0].strip()


def _public_api_base(request: Request) -> str:
    forwarded_proto = _header_first_value(request, "x-forwarded-proto")
    forwarded_host = _header_first_value(request, "x-forwarded-host")
    host = forwarded_host or request.headers.get("host") or request.url.netloc
    scheme = forwarded_proto or request.url.scheme or "http"

    if host.endswith(".run.app"):
        scheme = "https"
    elif scheme not in ("http", "https"):
        scheme = "https" if "https" in scheme else "http"

    return f"{scheme}://{host}".rstrip("/")


def _public_ogc_urls(request: Request, image_id: str) -> dict[str, str]:
    base = _public_api_base(request)
    return {
        "wms": f"{base}/api/services/{image_id}/wms-proxy",
        "wmts": f"{base}/api/services/{image_id}/wmts-proxy",
        "wcs": f"{base}/api/services/{image_id}/wcs-proxy",
    }


def _get_header(response: httpx.Response, name: str) -> str | None:
    return response.headers.get(name)


def _build_proxy_response(upstream: httpx.Response) -> Response:
    headers: dict[str, str] = {}
    for h in ("content-type", "cache-control", "etag", "last-modified", "expires", "pragma"):
        v = _get_header(upstream, h)
        if v:
            headers[h] = v
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)


async def _get_published_image(image_id: str, db: AsyncSession) -> Image:
    image = await db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    if image.status != ProcessingStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail=f"Image not published: {image.status}")
    if not image.layer_name:
        raise HTTPException(status_code=409, detail="Published image has no layer_name")
    return image


async def _proxy_get(url: str, params: dict[str, str]) -> Response:
    auth = (settings.geoserver_admin_user, settings.geoserver_admin_password)
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            upstream = await client.get(url, params=params, auth=auth)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"GeoServer upstream error: {exc}") from exc
    return _build_proxy_response(upstream)


def _filter_wms_capabilities_to_layer(xml_text: str, layer_name: str) -> str:
    """
    Keep only the target layer in GetCapabilities so clients like ArcGIS
    do not pick a different layer from the same workspace.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return xml_text

    ns = {"w": "http://www.opengis.net/wms"}
    capability_layer = root.find(".//w:Capability/w:Layer", ns)
    if capability_layer is None:
        return xml_text

    target = layer_name.split(":")[-1]
    child_layers = capability_layer.findall("w:Layer", ns)
    kept = 0
    for lyr in child_layers:
        name_el = lyr.find("w:Name", ns)
        if name_el is not None and name_el.text == target:
            kept += 1
            continue
        capability_layer.remove(lyr)

    if kept == 0:
        return xml_text
    return ET.tostring(root, encoding="unicode")


def _rewrite_wms_capabilities_xml(
    xml_text: str, image_id: str, request: Request, layer_name: str
) -> str:
    """
    Replace internal GeoServer xlink:href URLs in WMS capabilities with the
    public HTTPS proxy endpoint so external clients (ArcGIS Online) can use it.
    """
    geoserver_base = settings.geoserver_url.rstrip("/")
    public_wms = _public_ogc_urls(request, image_id)["wms"]
    href_pattern = re.compile(r'(xlink:href=")([^"]+)(")')

    def _rewrite_href(match: re.Match[str]) -> str:
        href = match.group(2)
        if not href.startswith(geoserver_base):
            return match.group(0)

        query = ""
        if "?" in href:
            query = href.split("?", 1)[1]

        rewritten = f"{public_wms}?{query}" if query else public_wms
        return f'{match.group(1)}{rewritten}{match.group(3)}'

    filtered_xml = _filter_wms_capabilities_to_layer(xml_text, layer_name)
    rewritten_xml = href_pattern.sub(_rewrite_href, filtered_xml)

    internal_schema = f"{geoserver_base}/schemas/wms/1.3.0/capabilities_1_3_0.xsd"
    ogc_schema = "https://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd"
    return rewritten_xml.replace(internal_schema, ogc_schema)


@router.get("/{image_id}/ogc")
async def get_ogc_services(
    image_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    image = await _get_published_image(image_id, db)
    urls = _public_ogc_urls(request, image.id)
    wms = urls["wms"]
    wmts = urls["wmts"]
    wcs = urls["wcs"]

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
    image = await _get_published_image(image_id, db)

    wms_endpoint = (
        f"{settings.geoserver_url.rstrip('/')}/{settings.geoserver_workspace}/wms"
    )

    # Normalize WMS params to lowercase keys because some clients (ArcGIS)
    # send uppercase QUERY keys (REQUEST, LAYERS, CRS, ...).
    params = {k.lower(): v for k, v in request.query_params.items()}
    params.setdefault("service", "WMS")
    params.setdefault("request", "GetCapabilities")
    params.setdefault("version", "1.3.0")
    params.setdefault("format", "image/png")
    params.setdefault("transparent", "true")
    request_name = str(params.get("request", "")).lower()
    if request_name in ("getmap", "getfeatureinfo"):
        params.setdefault("layers", image.layer_name)
    elif request_name == "getlegendgraphic":
        params.setdefault("layer", image.layer_name)
    proxied = await _proxy_get(wms_endpoint, params)
    if request_name != "getcapabilities":
        return proxied

    content_type = proxied.headers.get("content-type", "")
    if "xml" not in content_type.lower():
        return proxied

    try:
        text = proxied.body.decode("utf-8")
    except UnicodeDecodeError:
        text = proxied.body.decode("latin-1")

    rewritten = _rewrite_wms_capabilities_xml(text, image.id, request, image.layer_name)
    headers: dict[str, str] = {}
    cache_control = proxied.headers.get("cache-control")
    if cache_control:
        headers["cache-control"] = cache_control
    headers["content-type"] = content_type or "text/xml; charset=UTF-8"
    return Response(content=rewritten, status_code=proxied.status_code, headers=headers)


@router.get("/{image_id}/wmts-proxy")
async def wmts_proxy(
    image_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _get_published_image(image_id, db)
    wmts_endpoint = f"{settings.geoserver_url.rstrip('/')}/gwc/service/wmts"
    params = dict(request.query_params)
    params.setdefault("REQUEST", "GetCapabilities")
    return await _proxy_get(wmts_endpoint, params)


@router.get("/{image_id}/wcs-proxy")
async def wcs_proxy(
    image_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _get_published_image(image_id, db)
    wcs_endpoint = (
        f"{settings.geoserver_url.rstrip('/')}/{settings.geoserver_workspace}/wcs"
    )
    params = dict(request.query_params)
    params.setdefault("service", "WCS")
    params.setdefault("version", "2.0.1")
    params.setdefault("request", "GetCapabilities")
    return await _proxy_get(wcs_endpoint, params)
