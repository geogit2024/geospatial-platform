#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# GeoServer Workspace Initializer
# Run after GeoServer is up to create workspace and default settings
# ──────────────────────────────────────────────────────────────────────

GEOSERVER_URL="${GEOSERVER_URL:-http://localhost:8080/geoserver}"
ADMIN_USER="${GEOSERVER_ADMIN_USER:-admin}"
ADMIN_PASS="${GEOSERVER_ADMIN_PASSWORD:-geoserver}"
WORKSPACE="${GEOSERVER_WORKSPACE:-geoimages}"

AUTH="-u ${ADMIN_USER}:${ADMIN_PASS}"
BASE="${GEOSERVER_URL}/rest"

echo "[init] Waiting for GeoServer..."
until curl -sf "${GEOSERVER_URL}/web/" > /dev/null; do
  sleep 5
done
echo "[init] GeoServer is up."

# Create workspace
echo "[init] Creating workspace: ${WORKSPACE}"
curl -sf ${AUTH} \
  -X POST "${BASE}/workspaces" \
  -H "Content-Type: application/json" \
  -d "{\"workspace\":{\"name\":\"${WORKSPACE}\"}}" \
  || echo "[init] Workspace may already exist, skipping."

# Enable CORS on GeoServer (via settings API)
echo "[init] Configuring CORS..."
curl -sf ${AUTH} \
  -X PUT "${BASE}/settings" \
  -H "Content-Type: application/json" \
  -d '{
    "global": {
      "settings": {
        "verbose": false,
        "verboseExceptions": false,
        "localWorkspaceIncludesPrefix": false
      }
    }
  }' || true

echo "[init] GeoServer initialization complete."
echo "[init] Workspace '${WORKSPACE}' ready."
echo "[init] WMS: ${GEOSERVER_URL}/${WORKSPACE}/wms"
echo "[init] WMTS: ${GEOSERVER_URL}/gwc/service/wmts"
echo "[init] WCS: ${GEOSERVER_URL}/${WORKSPACE}/wcs"
