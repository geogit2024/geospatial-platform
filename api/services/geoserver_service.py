import re
from urllib.parse import unquote, urlparse

import httpx

from config import get_settings

settings = get_settings()
_SAFE_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _safe_identifier(raw: str, prefix: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", (raw or "").strip()).strip("_").lower()
    if not value:
        value = prefix
    if value[0].isdigit():
        value = f"{prefix}_{value}"
    value = value[:63]
    if not _SAFE_IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid identifier: {raw!r}")
    return value


def _db_connection_params() -> dict[str, str]:
    parsed = urlparse(settings.database_url.replace("+asyncpg", ""))
    return {
        "dbtype": "postgis",
        "host": parsed.hostname or "postgres",
        "port": str(parsed.port or 5432),
        "database": ((parsed.path or "/").lstrip("/") or "geodb"),
        "schema": settings.postgis_schema or "public",
        "user": unquote(parsed.username or ""),
        "passwd": unquote(parsed.password or ""),
        "Expose primary keys": "true",
        "preparedStatements": "false",
    }


class GeoServerService:
    def __init__(self) -> None:
        self.base = settings.geoserver_url.rstrip("/") + "/rest"
        self.public_base = (settings.geoserver_public_url or settings.geoserver_url).rstrip("/")
        self.auth = (settings.geoserver_admin_user, settings.geoserver_admin_password)

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        return httpx.request(
            method=method,
            url=f"{self.base}{path}",
            auth=self.auth,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json=payload,
            params=params,
            timeout=30,
        )

    def create_workspace(self, workspace: str) -> None:
        ws = _safe_identifier(workspace, "ws")
        current = self._request("GET", f"/workspaces/{ws}.json")
        if current.status_code == 200:
            return
        if current.status_code != 404:
            current.raise_for_status()
        created = self._request("POST", "/workspaces", payload={"workspace": {"name": ws}})
        if created.status_code not in (200, 201):
            created.raise_for_status()

    def create_datastore(self, workspace: str, db_config: dict | None = None, datastore: str | None = None) -> str:
        ws = _safe_identifier(workspace, "ws")
        store = _safe_identifier(datastore or settings.vector_default_datastore, "store")
        params = db_config or _db_connection_params()
        payload = {
            "dataStore": {
                "name": store,
                "enabled": True,
                "type": "PostGIS",
                "connectionParameters": {
                    "entry": [{"@key": key, "$": value} for key, value in params.items()]
                },
            }
        }
        check = self._request("GET", f"/workspaces/{ws}/datastores/{store}.json")
        if check.status_code == 200:
            updated = self._request("PUT", f"/workspaces/{ws}/datastores/{store}.json", payload=payload)
            if updated.status_code not in (200, 201):
                updated.raise_for_status()
            return store
        if check.status_code != 404:
            check.raise_for_status()
        created = self._request("POST", f"/workspaces/{ws}/datastores", payload=payload)
        if created.status_code not in (200, 201):
            created.raise_for_status()
        return store

    def publish_layer(self, workspace: str, datastore: str, table_name: str) -> dict[str, str]:
        ws = _safe_identifier(workspace, "ws")
        store = _safe_identifier(datastore, "store")
        table = _safe_identifier(table_name, "layer")
        payload = {
            "featureType": {
                "name": table,
                "nativeName": table,
                "title": table,
                "srs": "EPSG:4326",
                "enabled": True,
            }
        }
        check = self._request("GET", f"/workspaces/{ws}/datastores/{store}/featuretypes/{table}.json")
        if check.status_code == 200:
            updated = self._request(
                "PUT",
                f"/workspaces/{ws}/datastores/{store}/featuretypes/{table}.json",
                payload=payload,
            )
            if updated.status_code not in (200, 201):
                updated.raise_for_status()
        elif check.status_code == 404:
            created = self._request(
                "POST",
                f"/workspaces/{ws}/datastores/{store}/featuretypes",
                payload=payload,
            )
            if created.status_code not in (200, 201):
                created.raise_for_status()
        else:
            check.raise_for_status()
        return {
            "layer_name": f"{ws}:{table}",
            "wms_url": f"{self.public_base}/{ws}/wms",
            "wfs_url": f"{self.public_base}/{ws}/wfs",
        }
