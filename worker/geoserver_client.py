"""
GeoServer REST API client — publishes COG files via HTTPS URL (MinIO presigned).

Publication flow:
  1. ensure_workspace()       — create workspace if missing
  2. create_coverage_store()  — register the COG HTTPS URL as a GeoTIFF store
  3. create_coverage()        — expose the coverage as a WMS/WMTS/WCS layer
"""

import httpx
import logging
from typing import Optional
from config import get_settings

settings = get_settings()
log = logging.getLogger("worker.geoserver")

# How long (seconds) the MinIO presigned download URL should live.
# GeoServer reads the file when layers are rendered, so it needs a long TTL.
COG_URL_TTL = 60 * 60 * 24 * 365  # 1 year


class GeoServerClient:
    def __init__(self):
        self.base = settings.geoserver_url.rstrip("/") + "/rest"
        self.auth = (settings.geoserver_admin_user, settings.geoserver_admin_password)
        self.ws   = settings.geoserver_workspace

    # ── helpers ────────────────────────────────────────────────────────────

    def _get(self, path: str, **kw) -> httpx.Response:
        return httpx.get(f"{self.base}{path}", auth=self.auth, timeout=30, **kw)

    def _put(self, path: str, **kw) -> httpx.Response:
        return httpx.put(f"{self.base}{path}", auth=self.auth, timeout=60, **kw)

    def _post(self, path: str, **kw) -> httpx.Response:
        return httpx.post(f"{self.base}{path}", auth=self.auth, timeout=30, **kw)

    def _delete(self, path: str, **kw) -> httpx.Response:
        return httpx.delete(f"{self.base}{path}", auth=self.auth, timeout=30, **kw)

    # ── workspace ──────────────────────────────────────────────────────────

    def ensure_workspace(self) -> None:
        r = self._get(f"/workspaces/{self.ws}")
        if r.status_code == 404:
            log.info(f"Creating GeoServer workspace: {self.ws}")
            self._post(
                "/workspaces",
                headers={"Content-Type": "application/json"},
                json={"workspace": {"name": self.ws}},
            ).raise_for_status()

    # ── main publication ───────────────────────────────────────────────────

    def publish_cog(
        self,
        image_id: str,
        cog_url: str,          # HTTPS presigned URL — GeoServer fetches the COG from here
        title: Optional[str] = None,
        crs: str = "EPSG:4326",
    ) -> dict:
        """
        Register a COG accessible at `cog_url` as a GeoServer WMS/WMTS/WCS layer.

        GeoServer supports reading GeoTIFF (including COG) from an HTTPS URL.
        The presigned URL must have a TTL long enough for GeoServer to serve tiles.
        """
        store_name = f"img_{image_id.replace('-', '_')}"
        layer_name = store_name

        self.ensure_workspace()

        # 1. Create / update coverage store pointing to the HTTPS COG URL
        log.info(f"[{image_id}] Registering CoverageStore with URL: {cog_url[:60]}...")
        store_payload = {
            "coverageStore": {
                "name": store_name,
                "type": "GeoTIFF",
                "enabled": True,
                "workspace": {"name": self.ws},
                "url": cog_url,             # GeoServer reads COG from this HTTPS URL
            }
        }
        r = self._put(
            f"/workspaces/{self.ws}/coveragestores/{store_name}",
            headers={"Content-Type": "application/json"},
            json=store_payload,
        )
        if r.status_code not in (200, 201):
            log.warning(f"CoverageStore PUT returned {r.status_code}: {r.text[:200]}")
            r.raise_for_status()

        # 2. Create / update coverage (layer)
        log.info(f"[{image_id}] Creating coverage layer: {layer_name}")
        coverage_payload = {
            "coverage": {
                "name": layer_name,
                "title": title or layer_name,
                "enabled": True,
                "srs": crs,
                "store": {"name": store_name},
            }
        }
        r = self._put(
            f"/workspaces/{self.ws}/coveragestores/{store_name}/coverages/{layer_name}",
            headers={"Content-Type": "application/json"},
            json=coverage_payload,
        )
        # 201 = created, 200 = updated, some GeoServer versions return 500 on PUT but still work
        if r.status_code not in (200, 201, 500):
            log.warning(f"Coverage PUT returned {r.status_code}: {r.text[:200]}")

        # 3. Build public OGC URLs
        gs = settings.geoserver_url.rstrip("/")
        return {
            "layer_name": f"{self.ws}:{layer_name}",
            "wms_url":  f"{gs}/{self.ws}/wms",
            "wmts_url": f"{gs}/gwc/service/wmts",
            "wcs_url":  f"{gs}/{self.ws}/wcs",
        }
