import logging
import re
from urllib.parse import unquote, urlparse

import httpx

from config import get_settings

settings = get_settings()
log = logging.getLogger("worker.geoserver_vector")
_SAFE_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _sanitize_identifier(raw: str, *, prefix: str = "item") -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", (raw or "").strip()).strip("_").lower()
    if not value:
        value = prefix
    if value[0].isdigit():
        value = f"{prefix}_{value}"
    value = value[:63]
    if not _SAFE_IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid identifier derived from: {raw!r}")
    return value


def build_workspace_name(user_id: str) -> str:
    safe_user = _sanitize_identifier(user_id, prefix="user")
    workspace = f"{settings.vector_workspace_prefix}_{safe_user}"[:63]
    if not _SAFE_IDENTIFIER_RE.match(workspace):
        raise ValueError(f"Invalid workspace name: {workspace!r}")
    return workspace


def _database_connection_config() -> dict[str, str]:
    parsed = urlparse(settings.database_url.replace("+asyncpg", ""))
    db_name = (parsed.path or "/").lstrip("/") or "geodb"
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    host = parsed.hostname or "postgres"
    port = str(parsed.port or 5432)
    schema = settings.postgis_schema or "public"

    return {
        "dbtype": "postgis",
        "host": host,
        "port": port,
        "database": db_name,
        "schema": schema,
        "user": user,
        "passwd": password,
        "Expose primary keys": "true",
        "encode functions": "true",
        "preparedStatements": "false",
    }


class GeoServerVectorService:
    def __init__(self) -> None:
        self.base = settings.geoserver_url.rstrip("/") + "/rest"
        self.public_base = (settings.geoserver_public_url or settings.geoserver_url).rstrip("/")
        self.auth = (settings.geoserver_admin_user, settings.geoserver_admin_password)
        self.timeout = max(int(settings.vector_publish_timeout_seconds), 30)

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "Accept": "application/json"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = f"{self.base}{path}"
        response = httpx.request(
            method=method.upper(),
            url=url,
            auth=self.auth,
            headers=self._headers(),
            json=json_payload,
            params=params,
            timeout=self.timeout,
        )
        return response

    def create_workspace(self, workspace: str) -> None:
        workspace = _sanitize_identifier(workspace, prefix="ws")
        check = self._request("GET", f"/workspaces/{workspace}.json")
        if check.status_code == 200:
            return
        if check.status_code != 404:
            check.raise_for_status()

        payload = {"workspace": {"name": workspace}}
        created = self._request("POST", "/workspaces", json_payload=payload)
        if created.status_code not in (200, 201):
            created.raise_for_status()

    def create_datastore(self, workspace: str, datastore: str | None = None) -> str:
        workspace = _sanitize_identifier(workspace, prefix="ws")
        datastore_name = _sanitize_identifier(datastore or settings.vector_default_datastore, prefix="store")

        check = self._request(
            "GET",
            f"/workspaces/{workspace}/datastores/{datastore_name}.json",
        )
        payload = {
            "dataStore": {
                "name": datastore_name,
                "enabled": True,
                "type": "PostGIS",
                "connectionParameters": {
                    "entry": [
                        {"@key": key, "$": value}
                        for key, value in _database_connection_config().items()
                    ]
                },
            }
        }

        if check.status_code == 200:
            updated = self._request(
                "PUT",
                f"/workspaces/{workspace}/datastores/{datastore_name}.json",
                json_payload=payload,
            )
            if updated.status_code not in (200, 201):
                updated.raise_for_status()
            return datastore_name

        if check.status_code != 404:
            check.raise_for_status()

        created = self._request(
            "POST",
            f"/workspaces/{workspace}/datastores",
            json_payload=payload,
        )
        if created.status_code not in (200, 201):
            created.raise_for_status()
        return datastore_name

    def publish_layer(
        self,
        workspace: str,
        datastore: str,
        table_name: str,
        *,
        title: str | None = None,
    ) -> dict[str, str]:
        workspace = _sanitize_identifier(workspace, prefix="ws")
        datastore = _sanitize_identifier(datastore, prefix="store")
        table_name = _sanitize_identifier(table_name, prefix="layer")

        payload = {
            "featureType": {
                "name": table_name,
                "nativeName": table_name,
                "title": title or table_name,
                "srs": "EPSG:4326",
                "enabled": True,
            }
        }

        check = self._request(
            "GET",
            f"/workspaces/{workspace}/datastores/{datastore}/featuretypes/{table_name}.json",
        )
        if check.status_code == 200:
            updated = self._request(
                "PUT",
                f"/workspaces/{workspace}/datastores/{datastore}/featuretypes/{table_name}.json",
                json_payload=payload,
            )
            if updated.status_code not in (200, 201):
                updated.raise_for_status()
        elif check.status_code == 404:
            created = self._request(
                "POST",
                f"/workspaces/{workspace}/datastores/{datastore}/featuretypes",
                json_payload=payload,
            )
            if created.status_code not in (200, 201):
                created.raise_for_status()
        else:
            check.raise_for_status()

        layer_name = f"{workspace}:{table_name}"
        return {
            "workspace": workspace,
            "datastore": datastore,
            "table_name": table_name,
            "layer_name": layer_name,
            "wms_url": f"{self.public_base}/{workspace}/wms",
            "wfs_url": f"{self.public_base}/{workspace}/wfs",
        }

    def delete_layer(self, workspace: str, datastore: str, table_name: str) -> None:
        workspace = _sanitize_identifier(workspace, prefix="ws")
        datastore = _sanitize_identifier(datastore, prefix="store")
        table_name = _sanitize_identifier(table_name, prefix="layer")
        qualified_name = f"{workspace}:{table_name}"

        for path in (
            f"/layers/{qualified_name}.json",
            f"/workspaces/{workspace}/datastores/{datastore}/featuretypes/{table_name}.json",
        ):
            response = self._request("DELETE", path, params={"recurse": "true"})
            if response.status_code not in (200, 202, 404):
                log.warning(
                    "GeoServer vector delete returned HTTP %s for %s",
                    response.status_code,
                    path,
                )
