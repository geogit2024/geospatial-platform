# Skill: GeoServer Publication via REST API

## Purpose
Automate registration of processed COG rasters into GeoServer as OGC layers
(WMS / WMTS / WCS) using the GeoServer REST API.

## Concepts
- **Workspace**: logical namespace (e.g., `geoimages`)
- **Coverage Store**: pointer to a raster data source (GeoTIFF path or URL)
- **Coverage (Layer)**: published layer from a store
- **Style**: SLD style applied to layer

## REST API Sequence

```
1. Ensure workspace exists   → PUT /workspaces/{ws}
2. Create Coverage Store     → PUT /workspaces/{ws}/coveragestores/{store}
3. Configure Coverage Layer  → PUT /workspaces/{ws}/coveragestores/{store}/coverages/{coverage}
4. (Optional) Assign Style   → PUT /layers/{ws}:{coverage}
```

## Python Implementation Pattern

```python
import httpx
from typing import Optional

class GeoServerClient:
    def __init__(self, base_url: str, user: str, password: str, workspace: str):
        self.base = base_url.rstrip("/") + "/rest"
        self.auth = (user, password)
        self.ws = workspace
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def ensure_workspace(self) -> None:
        r = httpx.get(f"{self.base}/workspaces/{self.ws}", auth=self.auth)
        if r.status_code == 404:
            httpx.post(
                f"{self.base}/workspaces",
                auth=self.auth,
                headers=self.headers,
                json={"workspace": {"name": self.ws}}
            ).raise_for_status()

    def publish_geotiff(self, store_name: str, file_url: str, layer_name: Optional[str] = None) -> dict:
        layer_name = layer_name or store_name
        self.ensure_workspace()

        # Create coverage store pointing to file
        store_payload = {
            "coverageStore": {
                "name": store_name,
                "type": "GeoTIFF",
                "enabled": True,
                "workspace": {"name": self.ws},
                "url": file_url  # file:// path or http:// URL
            }
        }
        httpx.put(
            f"{self.base}/workspaces/{self.ws}/coveragestores/{store_name}",
            auth=self.auth, headers=self.headers, json=store_payload
        ).raise_for_status()

        # Auto-configure coverage from store
        httpx.put(
            f"{self.base}/workspaces/{self.ws}/coveragestores/{store_name}/coverages/{layer_name}",
            auth=self.auth, headers=self.headers,
            json={"coverage": {"name": layer_name, "enabled": True}}
        )

        return {
            "wms": f"{self.base.replace('/rest','')}/{self.ws}/wms?service=WMS&version=1.1.1&request=GetCapabilities",
            "wmts": f"{self.base.replace('/rest','')}/gwc/service/wmts?REQUEST=GetCapabilities",
            "wcs": f"{self.base.replace('/rest','')}/{self.ws}/wcs?service=WCS&version=2.0.1&request=GetCapabilities",
            "layer": f"{self.ws}:{layer_name}"
        }
```

## Key Notes
- GeoServer must have read access to the file path used in `url`
- For bucket-hosted files: mount bucket via FUSE (gcsfuse) or use HTTP URL (COG supports range requests)
- After POSTing a new store, GET the coverage list to verify auto-detection
- WMTS requires GeoWebCache (GWC) seeding for best performance; initial request will seed on demand
