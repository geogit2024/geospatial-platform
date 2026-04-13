import httpx
from typing import Optional
from config import get_settings

settings = get_settings()


class GeoServerClient:
    def __init__(self):
        self.base = settings.geoserver_url.rstrip("/") + "/rest"
        self.auth = (settings.geoserver_admin_user, settings.geoserver_admin_password)
        self.ws = settings.geoserver_workspace

    def ensure_workspace(self) -> None:
        r = httpx.get(f"{self.base}/workspaces/{self.ws}", auth=self.auth)
        if r.status_code == 404:
            httpx.post(
                f"{self.base}/workspaces",
                auth=self.auth,
                headers={"Content-Type": "application/json"},
                json={"workspace": {"name": self.ws}},
            ).raise_for_status()

    def publish_cog(
        self,
        image_id: str,
        cog_file_path: str,
        title: Optional[str] = None,
    ) -> dict:
        store_name = f"img_{image_id.replace('-', '_')}"
        layer_name = store_name
        # file_url uses file:// protocol pointing to path inside GeoServer container
        file_url = f"file:{cog_file_path}"

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
        httpx.put(
            f"{self.base}/workspaces/{self.ws}/coveragestores/{store_name}",
            auth=self.auth,
            headers={"Content-Type": "application/json"},
            json=store_payload,
            timeout=30,
        ).raise_for_status()

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
            headers={"Content-Type": "application/json"},
            json=coverage_payload,
            timeout=30,
        )

        gs = settings.geoserver_url.rstrip("/")
        return {
            "layer_name": f"{self.ws}:{layer_name}",
            "wms_url": f"{gs}/{self.ws}/wms",
            "wmts_url": f"{gs}/gwc/service/wmts",
            "wcs_url": f"{gs}/{self.ws}/wcs",
        }
