"""
GeoServer REST API client — publishes COG files via HTTPS URL (MinIO public URL).
GeoServer 2.21+ reads COG from HTTPS using HTTP Range requests natively.

REST API flow:
  POST /workspaces/{ws}/coveragestores              → create store
  POST /workspaces/{ws}/coveragestores/{s}/coverages → create coverage (layer)
  PUT  /gwc/rest/layers/{ws}:{layer}                → configure GWC tile caching
"""

import logging
import math
from typing import Optional

import httpx

from config import get_settings

settings = get_settings()
log = logging.getLogger("worker.geoserver")

# SRS exposed in WMS/WMTS GetCapabilities — covers ArcGIS Online, Leaflet, QGIS
_SUPPORTED_SRS = ["EPSG:4326", "EPSG:3857"]

# EPSG:3857 extent in metres
_M = 20037508.342789244


def _transform_bbox_to_wgs84(bbox: dict, src_crs: str) -> dict:
    """
    Transform bbox from src_crs to WGS84 (lon/lat).
    Uses osgeo.osr when available; falls back to math for EPSG:3857.
    """
    # Fast math path for the common case (EPSG:3857 → WGS84)
    if "3857" in src_crs or "900913" in src_crs:
        def _x2lon(x): return x * 180.0 / _M
        def _y2lat(y):
            return math.degrees(2.0 * math.atan(math.exp(y * math.pi / _M)) - math.pi / 2.0)
        return {
            "minx": _x2lon(bbox["minx"]),
            "miny": _y2lat(bbox["miny"]),
            "maxx": _x2lon(bbox["maxx"]),
            "maxy": _y2lat(bbox["maxy"]),
        }

    # General path via OSR
    try:
        from osgeo import osr
        src = osr.SpatialReference()
        src.SetFromUserInput(src_crs)
        src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        dst = osr.SpatialReference()
        dst.ImportFromEPSG(4326)
        dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        ct = osr.CoordinateTransformation(src, dst)
        lon1, lat1, _ = ct.TransformPoint(bbox["minx"], bbox["miny"])
        lon2, lat2, _ = ct.TransformPoint(bbox["maxx"], bbox["maxy"])
        return {
            "minx": min(lon1, lon2),
            "miny": min(lat1, lat2),
            "maxx": max(lon1, lon2),
            "maxy": max(lat1, lat2),
        }
    except Exception as exc:
        log.warning("OSR bbox transform failed (%s), returning native bbox", exc)
        return bbox


class GeoServerClient:
    def __init__(self) -> None:
        self.base       = settings.geoserver_url.rstrip("/") + "/rest"    # internal REST calls
        self.gwc_base   = settings.geoserver_url.rstrip("/") + "/gwc/rest" # GeoWebCache REST
        self.public_url = settings.geoserver_public_url.rstrip("/")        # public HTTPS OGC URLs
        self.auth       = (settings.geoserver_admin_user, settings.geoserver_admin_password)
        self.ws         = settings.geoserver_workspace

    # ── HTTP helpers ────────────────────────────────────────────────────────────

    def _json_headers(self) -> dict:
        return {"Content-Type": "application/json", "Accept": "application/json"}

    def _get(self, path: str) -> httpx.Response:
        return httpx.get(f"{self.base}{path}", auth=self.auth, timeout=30)

    def _post(self, path: str, body: dict) -> httpx.Response:
        return httpx.post(
            f"{self.base}{path}", auth=self.auth,
            headers=self._json_headers(), json=body, timeout=60,
        )

    def _put(self, path: str, body: dict) -> httpx.Response:
        return httpx.put(
            f"{self.base}{path}", auth=self.auth,
            headers=self._json_headers(), json=body, timeout=60,
        )

    def _delete(self, path: str, **kw) -> httpx.Response:
        return httpx.delete(f"{self.base}{path}", auth=self.auth, timeout=30, **kw)

    # ── Workspace ───────────────────────────────────────────────────────────────

    def ensure_workspace(self) -> None:
        r = self._get(f"/workspaces/{self.ws}.json")
        if r.status_code == 404:
            log.info("Creating workspace: %s", self.ws)
            self._post("/workspaces", {"workspace": {"name": self.ws}}).raise_for_status()
        elif r.status_code != 200:
            log.warning("Workspace check returned %d", r.status_code)

    # ── CoverageStore ───────────────────────────────────────────────────────────

    def _upsert_store(self, store_name: str, cog_url: str) -> None:
        """Create or update a GeoTIFF coverage store pointing to an HTTPS COG URL."""
        store_path = f"/workspaces/{self.ws}/coveragestores/{store_name}.json"
        payload = {
            "coverageStore": {
                "name":      store_name,
                "type":      "GeoTIFF",
                "enabled":   True,
                "workspace": {"name": self.ws},
                "url":       cog_url,
            }
        }

        if self._get(store_path).status_code == 200:
            log.info("Updating coverageStore: %s", store_name)
            r = self._put(f"/workspaces/{self.ws}/coveragestores/{store_name}.json", payload)
        else:
            log.info("Creating coverageStore: %s", store_name)
            r = self._post(f"/workspaces/{self.ws}/coveragestores.json", payload)

        if r.status_code not in (200, 201):
            log.error("CoverageStore upsert failed %d: %s", r.status_code, r.text[:300])
            r.raise_for_status()

    # ── Coverage (layer) ────────────────────────────────────────────────────────

    def _upsert_coverage(
        self,
        store_name: str,
        layer_name: str,
        title: str,
        crs: str,
        native_bbox: Optional[dict] = None,
    ) -> None:
        """
        Create or update a coverage layer on an existing store.

        Sets:
          • requestSRS / responseSRS  — advertise EPSG:4326 + EPSG:3857
          • projectionPolicy          — REPROJECT_TO_DECLARED (safe default)
          • nativeBoundingBox         — exact extent in native CRS
          • latLonBoundingBox         — same extent in WGS84 (required by ArcGIS Online)
        """
        cov_path = (
            f"/workspaces/{self.ws}/coveragestores/{store_name}"
            f"/coverages/{layer_name}.json"
        )

        # Always expose native CRS + 4326 + 3857 so all clients work
        srs_list = list(dict.fromkeys([crs] + _SUPPORTED_SRS))

        payload: dict = {
            "coverage": {
                "name":             layer_name,
                "title":            title,
                "enabled":          True,
                "srs":              crs,
                "projectionPolicy": "REPROJECT_TO_DECLARED",
                "requestSRS":       {"string": srs_list},
                "responseSRS":      {"string": srs_list},
                "store":            {"name": store_name},
            }
        }

        if native_bbox:
            payload["coverage"]["nativeBoundingBox"] = {
                "minx": native_bbox["minx"],
                "maxx": native_bbox["maxx"],
                "miny": native_bbox["miny"],
                "maxy": native_bbox["maxy"],
                "crs":  crs,
            }
            # Compute WGS84 bbox for LatLon envelope (mandatory for ArcGIS Online)
            try:
                wgs84 = _transform_bbox_to_wgs84(native_bbox, crs)
                payload["coverage"]["latLonBoundingBox"] = {
                    "minx": wgs84["minx"],
                    "maxx": wgs84["maxx"],
                    "miny": wgs84["miny"],
                    "maxy": wgs84["maxy"],
                    "crs":  "EPSG:4326",
                }
            except Exception as exc:
                log.warning("Could not compute latLonBoundingBox: %s", exc)

        if self._get(cov_path).status_code == 200:
            log.info("Updating coverage: %s", layer_name)
            r = self._put(cov_path, payload)
        else:
            log.info("Creating coverage: %s", layer_name)
            r = self._post(
                f"/workspaces/{self.ws}/coveragestores/{store_name}/coverages.json",
                payload,
            )

        if r.status_code not in (200, 201):
            log.warning("Coverage upsert returned %d: %s", r.status_code, r.text[:300])
            # Non-fatal: GeoServer sometimes auto-creates the layer from store metadata

    # ── GeoWebCache tile layer ──────────────────────────────────────────────────

    def _configure_gwc_layer(self, full_layer_name: str) -> None:
        """
        Explicitly configure GWC tile layer to include EPSG:3857 and EPSG:4326
        gridsets with PNG + JPEG mime formats.

        GeoServer auto-creates a GWC layer on publish, but the default gridsets
        may not include EPSG:3857 depending on the installation.  This call is
        non-fatal: a failure here does NOT break WMS — only WMTS tile caching.
        """
        url = f"{self.gwc_base}/layers/{full_layer_name}.json"
        payload = {
            "GeoServerLayer": {
                "enabled":       True,
                "inMemoryCached": True,
                "name":          full_layer_name,
                "mimeFormats":   ["image/png", "image/jpeg"],
                "gridSubsets": [
                    {"gridSetName": "EPSG:4326"},
                    {"gridSetName": "EPSG:3857"},
                    {"gridSetName": "GoogleMapsCompatible"},
                ],
                "metaWidthHeight": [4, 4],
                "expireCache":   0,
                "expireClients": 0,
                "parameterFilters": [],
            }
        }
        try:
            r = httpx.put(
                url,
                auth=self.auth,
                headers=self._json_headers(),
                json=payload,
                timeout=30,
            )
            if r.status_code in (200, 201):
                log.info("GWC tile layer configured: %s", full_layer_name)
            else:
                log.warning("GWC configure returned %d: %s", r.status_code, r.text[:200])
        except Exception as exc:
            log.warning("GWC configuration failed (non-fatal): %s", exc)

    # ── Main publication entry point ────────────────────────────────────────────

    def publish_cog(
        self,
        image_id: str,
        cog_url: str,
        title: Optional[str] = None,
        crs: str = "EPSG:3857",
        native_bbox: Optional[dict] = None,
    ) -> dict:
        """
        Publish a COG to GeoServer and configure OGC services.

        Parameters
        ----------
        image_id    : image UUID — used to derive store / layer names
        cog_url     : public HTTPS URL of the COG in object storage
        title       : human-readable layer title (defaults to layer_name)
        crs         : native CRS of the COG (default EPSG:3857)
        native_bbox : native bounding box dict {minx, miny, maxx, maxy}

        Returns
        -------
        dict with layer_name, wms_url, wmts_url, wcs_url
        """
        store_name = f"img_{image_id.replace('-', '_')}"
        layer_name = store_name
        display    = title or layer_name
        full_name  = f"{self.ws}:{layer_name}"

        self.ensure_workspace()
        self._upsert_store(store_name, cog_url)
        self._upsert_coverage(store_name, layer_name, display, crs, native_bbox)
        self._configure_gwc_layer(full_name)

        gs = self.public_url
        result = {
            "layer_name": full_name,
            "wms_url":    f"{gs}/{self.ws}/wms",
            "wmts_url":   f"{gs}/gwc/service/wmts",
            "wcs_url":    f"{gs}/{self.ws}/wcs",
        }
        log.info("[%s] Published → %s", image_id, full_name)
        return result
