import httpx
from typing import Optional
from config import get_settings

settings = get_settings()


class GeoServerClient:
    def __init__(self):
        self.base = settings.geoserver_url.rstrip("/") + "/rest"
        self.auth = (settings.geoserver_admin_user, settings.geoserver_admin_password)
        self.ws = settings.geoserver_workspace
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _geoserver_base(self) -> str:
        return settings.geoserver_url.rstrip("/")

    def ensure_workspace(self) -> None:
        r = httpx.get(f"{self.base}/workspaces/{self.ws}", auth=self.auth)
        if r.status_code == 404:
            httpx.post(
                f"{self.base}/workspaces",
                auth=self.auth,
                headers=self.headers,
                json={"workspace": {"name": self.ws}},
            ).raise_for_status()

    def publish_geotiff(
        self,
        store_name: str,
        file_url: str,
        layer_name: Optional[str] = None,
        title: Optional[str] = None,
    ) -> dict:
        layer_name = layer_name or store_name
        self.ensure_workspace()

        store_payload = {
            "coverageStore": {
                "name": store_name,
                "type": "GeoTIFF",
                "enabled": True,
                "workspace": {"name": self.ws},
                "url": file_url,
            }
        }
        r = httpx.put(
            f"{self.base}/workspaces/{self.ws}/coveragestores/{store_name}",
            auth=self.auth,
            headers=self.headers,
            json=store_payload,
            timeout=30,
        )
        r.raise_for_status()

        coverage_payload = {
            "coverage": {
                "name": layer_name,
                "title": title or layer_name,
                "enabled": True,
                "srs": "EPSG:4326",
            }
        }
        httpx.put(
            f"{self.base}/workspaces/{self.ws}/coveragestores/{store_name}/coverages/{layer_name}",
            auth=self.auth,
            headers=self.headers,
            json=coverage_payload,
            timeout=30,
        )

        gs = self._geoserver_base()
        return {
            "layer": f"{self.ws}:{layer_name}",
            "wms_url": f"{gs}/{self.ws}/wms",
            "wmts_url": f"{gs}/gwc/service/wmts",
            "wcs_url": f"{gs}/{self.ws}/wcs",
            "wms_getcap": (
                f"{gs}/{self.ws}/wms?service=WMS&version=1.3.0&request=GetCapabilities"
            ),
            "wmts_getcap": (
                f"{gs}/gwc/service/wmts?REQUEST=GetCapabilities"
            ),
        }

    def delete_store(self, store_name: str) -> None:
        httpx.delete(
            f"{self.base}/workspaces/{self.ws}/coveragestores/{store_name}",
            auth=self.auth,
            params={"recurse": "true"},
            timeout=30,
        )


_client: GeoServerClient | None = None


def get_geoserver_client() -> GeoServerClient:
    global _client
    if _client is None:
        _client = GeoServerClient()
    return _client
