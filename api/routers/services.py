import asyncio
import httpx
import math
import logging
import random
import xml.etree.ElementTree as ET
from copy import deepcopy
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import AsyncSessionLocal, get_db
from models import AssetAccessLog, Image, ProcessingStatus

router = APIRouter(prefix="/services", tags=["ogc-services"])
settings = get_settings()
log = logging.getLogger("api.services")
_EVENT_TYPE_MAX_LENGTH = 32
_ACCESS_LOG_QUEUE_MAXSIZE = 50000
_HIGH_VOLUME_EVENT_TYPES = {"wms_getmap", "wms_getfeatureinfo", "wmts_gettile"}
_access_log_queue: asyncio.Queue[tuple[str, str, str]] = asyncio.Queue(maxsize=_ACCESS_LOG_QUEUE_MAXSIZE)
_access_log_worker_task: asyncio.Task[None] | None = None
_access_log_worker_lock = asyncio.Lock()


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
        "wfs": f"{base}/api/services/{image_id}/wfs-proxy",
        "wmts": f"{base}/api/services/{image_id}/wmts-proxy",
        "wcs": f"{base}/api/services/{image_id}/wcs-proxy",
    }


def _is_arcgis_request(request: Request) -> bool:
    origin = (request.headers.get("origin") or "").lower()
    referer = (request.headers.get("referer") or "").lower()
    marker = "arcgis.com"
    marker2 = "arcgisonline.com"
    return (
        marker in origin
        or marker2 in origin
        or marker in referer
        or marker2 in referer
    )


def _parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 4:
        return None
    try:
        minx, miny, maxx, maxy = (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
    except ValueError:
        return None
    if minx > maxx or miny > maxy:
        return None
    return (minx, miny, maxx, maxy)


def _parse_positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(str(value).strip())
    except ValueError:
        return None
    if parsed <= 0:
        return None
    return parsed


def _bbox_intersects(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def _is_likely_lonlat_bbox(bbox: tuple[float, float, float, float]) -> bool:
    minx, miny, maxx, maxy = bbox
    return (
        -180.0 <= minx <= 180.0
        and -180.0 <= maxx <= 180.0
        and -90.0 <= miny <= 90.0
        and -90.0 <= maxy <= 90.0
    )


def _lonlat_to_mercator_xy(lon: float, lat: float) -> tuple[float, float]:
    # Clamp latitude to WebMercator valid range.
    clamped_lat = max(min(lat, 85.05112878), -85.05112878)
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan((90.0 + clamped_lat) * math.pi / 360.0)) / (math.pi / 180.0)
    y = y * 20037508.34 / 180.0
    return (x, y)


def _bbox_4326_to_3857(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bbox
    x1, y1 = _lonlat_to_mercator_xy(minx, miny)
    x2, y2 = _lonlat_to_mercator_xy(maxx, maxy)
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _public_geoserver_service_url(raw_url: str | None, service_path: str) -> str:
    """
    Build a public HTTPS OGC endpoint for external consumers (ArcGIS/QGIS/etc).
    """
    if raw_url and raw_url.startswith("https://"):
        return raw_url

    public_base = settings.geoserver_public_url.rstrip("/")
    if public_base:
        if raw_url and "/geoserver/" in raw_url:
            suffix = raw_url.split("/geoserver/", 1)[1].lstrip("/")
            return f"{public_base}/{suffix}"
        return f"{public_base}/{service_path.lstrip('/')}"

    if raw_url:
        return raw_url
    return f"{settings.geoserver_url.rstrip('/')}/{service_path.lstrip('/')}"


def _get_header(response: httpx.Response, name: str) -> str | None:
    return response.headers.get(name)


def _build_proxy_response(upstream: httpx.Response) -> Response:
    headers: dict[str, str] = {}
    for h in ("content-type", "cache-control", "etag", "last-modified", "expires", "pragma"):
        v = _get_header(upstream, h)
        if v:
            headers[h] = v
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)


def _normalize_event_token(value: str | None, *, fallback: str) -> str:
    token = "".join(ch.lower() if ch.isalnum() else "_" for ch in (value or ""))
    token = token.strip("_")
    while "__" in token:
        token = token.replace("__", "_")
    return token or fallback


def _build_ogc_event_type(service: str, request_name: str | None, *, fallback_request: str) -> str:
    service_token = _normalize_event_token(service, fallback=service.lower())
    request_token = _normalize_event_token(request_name, fallback=fallback_request.lower())
    max_request_length = max(1, _EVENT_TYPE_MAX_LENGTH - len(service_token) - 1)
    return f"{service_token}_{request_token[:max_request_length]}"


def _should_sample_event(event_type: str) -> bool:
    normalized = (event_type or "").strip().lower()
    if normalized not in _HIGH_VOLUME_EVENT_TYPES:
        return True

    sample_rate = float(settings.ogc_access_log_sample_rate_high_volume)
    if sample_rate <= 0.0:
        return False
    if sample_rate >= 1.0:
        return True
    return random.random() < sample_rate


async def _flush_access_log_batch(batch: list[tuple[str, str, str]]) -> None:
    if not batch:
        return

    try:
        async with AsyncSessionLocal() as session:
            session.add_all(
                AssetAccessLog(
                    tenant_id=tenant_id,
                    image_id=image_id,
                    event_type=event_type,
                )
                for tenant_id, image_id, event_type in batch
            )
            await session.commit()
    except Exception as exc:
        log.warning("Failed to flush OGC access log batch (size=%d): %s", len(batch), exc)


async def _access_log_worker_loop() -> None:
    batch_size = max(int(settings.ogc_access_log_batch_size), 1)
    flush_interval = max(int(settings.ogc_access_log_flush_interval_seconds), 1)

    while True:
        first = await _access_log_queue.get()
        batch = [first]
        deadline = asyncio.get_running_loop().time() + flush_interval

        while len(batch) < batch_size:
            timeout = deadline - asyncio.get_running_loop().time()
            if timeout <= 0:
                break
            try:
                batch.append(await asyncio.wait_for(_access_log_queue.get(), timeout))
            except asyncio.TimeoutError:
                break

        await _flush_access_log_batch(batch)
        for _ in batch:
            _access_log_queue.task_done()


async def _ensure_access_log_worker() -> None:
    global _access_log_worker_task
    if _access_log_worker_task and not _access_log_worker_task.done():
        return

    async with _access_log_worker_lock:
        if _access_log_worker_task and not _access_log_worker_task.done():
            return
        _access_log_worker_task = asyncio.create_task(_access_log_worker_loop(), name="ogc-access-log-worker")


async def _register_access_log(db: AsyncSession, image: Image, event_type: str) -> None:
    _ = db  # The endpoint-level DB session is intentionally not used in this hot path.
    normalized_event = (event_type or "view")[:_EVENT_TYPE_MAX_LENGTH]
    if not _should_sample_event(normalized_event):
        return

    await _ensure_access_log_worker()
    try:
        _access_log_queue.put_nowait(
            (
                image.tenant_id or settings.default_tenant_id,
                image.id,
                normalized_event,
            )
        )
    except asyncio.QueueFull:
        log.warning(
            "OGC access log queue full (max=%d). Dropping event '%s' for image %s",
            _ACCESS_LOG_QUEUE_MAXSIZE,
            normalized_event,
            image.id,
        )


def _vector_default_style_name(geometry_type: str | None) -> str:
    """
    Pick a built-in GeoServer style for vector layers.
    """
    gt = (geometry_type or "").strip().upper()
    if "LINE" in gt:
        return "line"
    if "POINT" in gt:
        return "point"
    # For polygons, prefer outline-only rendering to avoid masking basemaps.
    # This also handles generic GEOMETRY columns commonly used by mixed
    # POLYGON/MULTIPOLYGON datasets.
    return "line"


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
    kept_layer: ET.Element | None = None
    for lyr in child_layers:
        name_el = lyr.find("w:Name", ns)
        if name_el is not None and name_el.text == target:
            kept += 1
            kept_layer = lyr
            continue
        capability_layer.remove(lyr)

    if kept == 0 or kept_layer is None:
        return xml_text

    # GeoServer keeps aggregate CRS/BBOX at parent layer level. For single-layer
    # capabilities (used by ArcGIS), keep parent metadata aligned with the target
    # child extent to avoid clients requesting tiles from unrelated extents.
    #
    # Important: keep existing parent CRS/SRS entries (often includes EPSG:3857),
    # otherwise ArcGIS can mark the service as incompatible with WebMercator
    # basemaps.
    parent_crs_values: set[tuple[str, str]] = set()
    for tag in ("w:CRS", "w:SRS"):
        for elem in capability_layer.findall(tag, ns):
            value = (elem.text or "").strip()
            if value:
                parent_crs_values.add((tag, value))

    for tag in ("w:CRS", "w:SRS"):
        for elem in kept_layer.findall(tag, ns):
            value = (elem.text or "").strip()
            key = (tag, value)
            if not value or key in parent_crs_values:
                continue
            capability_layer.insert(0, deepcopy(elem))
            parent_crs_values.add(key)

    # Replace only parent extent metadata with the target layer extents.
    for tag in (
        "w:EX_GeographicBoundingBox",
        "w:LatLonBoundingBox",
        "w:BoundingBox",
    ):
        for elem in capability_layer.findall(tag, ns):
            capability_layer.remove(elem)

    for tag in (
        "w:EX_GeographicBoundingBox",
        "w:LatLonBoundingBox",
        "w:BoundingBox",
    ):
        for elem in kept_layer.findall(tag, ns):
            capability_layer.insert(0, deepcopy(elem))

    return ET.tostring(root, encoding="unicode")


def _rewrite_wms_capabilities_xml(
    xml_text: str, image_id: str, request: Request, layer_name: str
) -> str:
    """
    Replace internal GeoServer xlink:href URLs in WMS capabilities with the
    public HTTPS proxy endpoint so external clients (ArcGIS Online) can use it.
    """
    geoserver_base = settings.geoserver_url.rstrip("/")
    geoserver_public_base = settings.geoserver_public_url.rstrip("/")
    public_wms = _public_ogc_urls(request, image_id)["wms"]
    filtered_xml = _filter_wms_capabilities_to_layer(xml_text, layer_name)

    try:
        root = ET.fromstring(filtered_xml)
    except ET.ParseError:
        return filtered_xml

    ET.register_namespace("", "http://www.opengis.net/wms")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")

    xlink_href = "{http://www.w3.org/1999/xlink}href"
    schema_loc = "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation"
    internal_schema = f"{geoserver_base}/schemas/wms/1.3.0/capabilities_1_3_0.xsd"
    public_schema = (
        f"{geoserver_public_base}/schemas/wms/1.3.0/capabilities_1_3_0.xsd"
        if geoserver_public_base
        else ""
    )
    ogc_schema = "https://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd"

    for elem in root.iter():
        href_value = elem.attrib.get(xlink_href) or elem.attrib.get("xlink:href")
        if href_value and (
            href_value.startswith(geoserver_base)
            or (geoserver_public_base and href_value.startswith(geoserver_public_base))
        ):
            query = href_value.split("?", 1)[1] if "?" in href_value else ""
            new_href = f"{public_wms}?{query}" if query else public_wms
            if xlink_href in elem.attrib:
                elem.attrib[xlink_href] = new_href
            if "xlink:href" in elem.attrib:
                elem.attrib["xlink:href"] = new_href

    schema_value = root.attrib.get(schema_loc)
    if schema_value:
        rewritten_schema = schema_value.replace(internal_schema, ogc_schema)
        if public_schema:
            rewritten_schema = rewritten_schema.replace(public_schema, ogc_schema)
        root.attrib[schema_loc] = rewritten_schema

    return ET.tostring(root, encoding="unicode")


@router.get("/{image_id}/ogc")
async def get_ogc_services(
    image_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    image = await _get_published_image(image_id, db)
    await _register_access_log(
        db,
        image,
        _build_ogc_event_type("ogc", "discovery", fallback_request="discovery"),
    )
    # WMS must be image-specific so clients (ArcGIS) see only this layer.
    wms = _public_ogc_urls(request, image.id)["wms"]
    wfs_proxy = _public_ogc_urls(request, image.id)["wfs"]
    workspace = image.workspace or settings.geoserver_workspace
    wfs = _public_geoserver_service_url(image.wfs_url, f"{workspace}/wfs")
    wmts = _public_geoserver_service_url(image.wmts_url, "gwc/service/wmts")
    wcs = _public_geoserver_service_url(
        image.wcs_url, f"{settings.geoserver_workspace}/wcs"
    )

    return {
        "image_id": image.id,
        "layer": image.layer_name,
        "asset_kind": image.asset_kind,
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
            "wfs": {
                "url": wfs,
                "getcapabilities": f"{wfs}?service=WFS&version=2.0.0&request=GetCapabilities",
                "getfeature_example": (
                    f"{wfs_proxy}?service=WFS&version=2.0.0&request=GetFeature"
                    f"&typenames={image.layer_name}&outputFormat=application/json"
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
    workspace = image.workspace or settings.geoserver_workspace

    wms_endpoint = (
        f"{settings.geoserver_url.rstrip('/')}/{workspace}/wms"
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
    await _register_access_log(
        db,
        image,
        _build_ogc_event_type("wms", request_name, fallback_request="getcapabilities"),
    )
    if request_name in ("getmap", "getfeatureinfo"):
        # This proxy endpoint is image-specific; always pin layer to avoid
        # client-side mismatches (e.g. ArcGIS using layer Title as Name).
        params["layers"] = image.layer_name
        is_vector = str(image.asset_kind or "").lower() == "vector"
        if is_vector and not str(params.get("styles", "")).strip():
            params["styles"] = _vector_default_style_name(image.geometry_type)
        if not is_vector and not str(params.get("styles", "")).strip():
            params["styles"] = "raster"

        # ArcGIS Online often requests overview tiles that are much larger than
        # tiny raster extents. In those cases fully-transparent responses are
        # common and AGOL appears to "not render". Keep normal transparent flow
        # for regular clients/zoom levels, and force visible fallback only on
        # ArcGIS-like or very-large overview requests that intersect the image.
        requested_crs = str(params.get("crs") or params.get("srs") or "").strip().upper()
        request_width = _parse_positive_int(params.get("width"))
        request_height = _parse_positive_int(params.get("height"))
        image_crs = str(image.crs or "").strip().upper()
        req_bbox = _parse_bbox(params.get("bbox"))
        if (
            request_name == "getmap"
            and req_bbox is not None
            and image.bbox_minx is not None
            and image.bbox_miny is not None
            and image.bbox_maxx is not None
            and image.bbox_maxy is not None
        ):
            raw_image_bbox = (
                float(image.bbox_minx),
                float(image.bbox_miny),
                float(image.bbox_maxx),
                float(image.bbox_maxy),
            )
            image_bbox = raw_image_bbox
            if requested_crs in ("EPSG:3857", "EPSG:900913") and _is_likely_lonlat_bbox(raw_image_bbox):
                image_bbox = _bbox_4326_to_3857(raw_image_bbox)
            if _bbox_intersects(req_bbox, image_bbox):
                crs_matches = bool(requested_crs and image_crs and requested_crs == image_crs)

                req_area = max((req_bbox[2] - req_bbox[0]) * (req_bbox[3] - req_bbox[1]), 0.0)
                img_area = max((image_bbox[2] - image_bbox[0]) * (image_bbox[3] - image_bbox[1]), 0.0)
                area_ratio = (req_area / img_area) if img_area > 0 else None

                user_agent = (request.headers.get("user-agent") or "").lower()
                has_arcgis_marker = _is_arcgis_request(request) or ("arcgis" in user_agent) or ("esri" in user_agent)
                is_large_overview_request = bool(
                    request_width is not None
                    and request_height is not None
                    and (request_width >= 4096 or request_height >= 4096)
                )

                # Keep explicit ArcGIS behavior for matching CRS, and add a safe
                # heuristic for header-less overview requests.
                apply_visibility_fallback = (
                    crs_matches
                    and (
                        has_arcgis_marker
                        or (
                            is_large_overview_request
                            and area_ratio is not None
                            and area_ratio >= 64.0
                        )
                    )
                )

                if apply_visibility_fallback:
                    requested_transparent = str(params.get("transparent", "")).strip().lower() in (
                        "true",
                        "1",
                        "yes",
                    )
                    requested_format = str(params.get("format", "")).strip().lower()
                    wants_transparent_png = requested_transparent and ("png" in requested_format)

                    # ArcGIS Online normalmente pede PNG transparente.
                    # Se for esse caso, preservar transparência evita o "bloco branco"
                    # e mantém a camada sobre o basemap corretamente.
                    if wants_transparent_png:
                        params["format"] = "image/png"
                        params["transparent"] = "true"
                    else:
                        params["format"] = "image/jpeg"
                        params["transparent"] = "false"
                        params.setdefault("bgcolor", "0xFFFFFF")
    elif request_name == "getlegendgraphic":
        params["layer"] = image.layer_name
        is_vector = str(image.asset_kind or "").lower() == "vector"
        if is_vector and not str(params.get("style", "")).strip():
            params["style"] = _vector_default_style_name(image.geometry_type)
        if not is_vector and not str(params.get("style", "")).strip():
            params["style"] = "raster"
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
    image = await _get_published_image(image_id, db)
    wmts_endpoint = f"{settings.geoserver_url.rstrip('/')}/gwc/service/wmts"
    params = dict(request.query_params)
    params.setdefault("REQUEST", "GetCapabilities")
    await _register_access_log(
        db,
        image,
        _build_ogc_event_type(
            "wmts",
            params.get("REQUEST") or params.get("request"),
            fallback_request="getcapabilities",
        ),
    )
    return await _proxy_get(wmts_endpoint, params)


@router.get("/{image_id}/wfs-proxy")
async def wfs_proxy(
    image_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    image = await _get_published_image(image_id, db)
    workspace = image.workspace or settings.geoserver_workspace
    wfs_endpoint = f"{settings.geoserver_url.rstrip('/')}/{workspace}/wfs"
    params = {k.lower(): v for k, v in request.query_params.items()}
    params.setdefault("service", "WFS")
    params.setdefault("version", "2.0.0")
    params.setdefault("request", "GetCapabilities")
    request_name = str(params.get("request", "")).lower()
    await _register_access_log(
        db,
        image,
        _build_ogc_event_type("wfs", request_name, fallback_request="getcapabilities"),
    )
    if request_name == "getfeature":
        params.setdefault("typenames", image.layer_name)
    return await _proxy_get(wfs_endpoint, params)


@router.get("/{image_id}/wcs-proxy")
async def wcs_proxy(
    image_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    image = await _get_published_image(image_id, db)
    wcs_endpoint = (
        f"{settings.geoserver_url.rstrip('/')}/{settings.geoserver_workspace}/wcs"
    )
    params = dict(request.query_params)
    params.setdefault("service", "WCS")
    params.setdefault("version", "2.0.1")
    params.setdefault("request", "GetCapabilities")
    await _register_access_log(
        db,
        image,
        _build_ogc_event_type(
            "wcs",
            params.get("request") or params.get("REQUEST"),
            fallback_request="getcapabilities",
        ),
    )
    return await _proxy_get(wcs_endpoint, params)
