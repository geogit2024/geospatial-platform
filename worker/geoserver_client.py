"""
GeoServer REST API client — publishes COG files via HTTPS URL (MinIO presigned).
GeoServer 2.21+ reads COG from HTTPS using HTTP Range requests natively.

REST API flow:
  POST /workspaces/{ws}/coveragestores              → create store
  POST /workspaces/{ws}/coveragestores/{s}/coverages → create layer
"""

import httpx
import logging
from typing import Optional
from config import get_settings

settings = get_settings()
log = logging.getLogger("worker.geoserver")


class GeoServerClient:
    def __init__(self):
        self.base = settings.geoserver_url.rstrip("/") + "/rest"
        self.auth = (settings.geoserver_admin_user, settings.geoserver_admin_password)
        self.ws   = settings.geoserver_workspace

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

    # ── workspace ──────────────────────────────────────────────────────────

    def ensure_workspace(self) -> None:
        r = self._get(f"/workspaces/{self.ws}.json")
        if r.status_code == 404:
            log.info(f"Creating workspace: {self.ws}")
            self._post("/workspaces", {"workspace": {"name": self.ws}}).raise_for_status()
        elif r.status_code != 200:
            log.warning(f"Workspace check returned {r.status_code}")

    # ── coverage store ─────────────────────────────────────────────────────

    def _upsert_store(self, store_name: str, cog_url: str) -> None:
        """Create or update a GeoTIFF coverage store pointing to an HTTPS COG URL."""
        store_path = f"/workspaces/{self.ws}/coveragestores/{store_name}.json"
        payload = {
            "coverageStore": {
                "name": store_name,
                "type": "GeoTIFF",
                "enabled": True,
                "workspace": {"name": self.ws},
                "url": cog_url,
            }
        }

        exists = self._get(store_path).status_code == 200
        if exists:
            log.info(f"Updating existing coverageStore: {store_name}")
            r = self._put(f"/workspaces/{self.ws}/coveragestores/{store_name}.json", payload)
        else:
            log.info(f"Creating coverageStore: {store_name}")
            r = self._post(f"/workspaces/{self.ws}/coveragestores.json", payload)

        if r.status_code not in (200, 201):
            log.error(f"CoverageStore upsert failed {r.status_code}: {r.text[:300]}")
            r.raise_for_status()

    # ── coverage layer ─────────────────────────────────────────────────────

    def _upsert_coverage(self, store_name: str, layer_name: str,
                         title: str, crs: str) -> None:
        """Create or update a coverage (WMS layer) on an existing store."""
        cov_path = (f"/workspaces/{self.ws}/coveragestores/{store_name}"
                    f"/coverages/{layer_name}.json")
        payload = {
            "coverage": {
                "name": layer_name,
                "title": title,
                "enabled": True,
                "srs": crs,
                "store": {"name": store_name},
            }
        }

        exists = self._get(cov_path).status_code == 200
        if exists:
            log.info(f"Updating existing coverage: {layer_name}")
            r = self._put(cov_path, payload)
        else:
            log.info(f"Creating coverage: {layer_name}")
            r = self._post(
                f"/workspaces/{self.ws}/coveragestores/{store_name}/coverages.json",
                payload,
            )

        if r.status_code not in (200, 201):
            log.warning(f"Coverage upsert returned {r.status_code}: {r.text[:300]}")
            # Non-fatal: GeoServer sometimes auto-creates the layer

    # ── main publication ───────────────────────────────────────────────────

    def publish_cog(
        self,
        image_id: str,
        cog_url: str,
        title: Optional[str] = None,
        crs: str = "EPSG:4326",
    ) -> dict:
        store_name = f"img_{image_id.replace('-', '_')}"
        layer_name = store_name
        display    = title or layer_name

        self.ensure_workspace()
        self._upsert_store(store_name, cog_url)
        self._upsert_coverage(store_name, layer_name, display, crs)

        gs = settings.geoserver_url.rstrip("/")
        result = {
            "layer_name": f"{self.ws}:{layer_name}",
            "wms_url":    f"{gs}/{self.ws}/wms",
            "wmts_url":   f"{gs}/gwc/service/wmts",
            "wcs_url":    f"{gs}/{self.ws}/wcs",
        }
        log.info(f"[{image_id}] Published → {result['layer_name']}")
        return result
