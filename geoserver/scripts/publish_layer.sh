#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# Manually publish a COG to GeoServer via REST API
# Usage: ./publish_layer.sh <image_id> <cog_file_path> [title]
# ──────────────────────────────────────────────────────────────────────

IMAGE_ID="${1:?Usage: $0 <image_id> <cog_file_path> [title]}"
COG_PATH="${2:?Usage: $0 <image_id> <cog_file_path> [title]}"
TITLE="${3:-Layer ${IMAGE_ID}}"

GEOSERVER_URL="${GEOSERVER_URL:-http://localhost:8080/geoserver}"
ADMIN_USER="${GEOSERVER_ADMIN_USER:-admin}"
ADMIN_PASS="${GEOSERVER_ADMIN_PASSWORD:-geoserver}"
WORKSPACE="${GEOSERVER_WORKSPACE:-geoimages}"

AUTH="-u ${ADMIN_USER}:${ADMIN_PASS}"
BASE="${GEOSERVER_URL}/rest"
STORE_NAME="img_$(echo ${IMAGE_ID} | tr '-' '_')"
LAYER_NAME="${STORE_NAME}"
FILE_URL="file:${COG_PATH}"

echo "[publish] Creating coverage store: ${STORE_NAME}"
curl -sf ${AUTH} \
  -X PUT "${BASE}/workspaces/${WORKSPACE}/coveragestores/${STORE_NAME}" \
  -H "Content-Type: application/json" \
  -d "{
    \"coverageStore\": {
      \"name\": \"${STORE_NAME}\",
      \"type\": \"GeoTIFF\",
      \"enabled\": true,
      \"workspace\": {\"name\": \"${WORKSPACE}\"},
      \"url\": \"${FILE_URL}\"
    }
  }" && echo "[publish] Store created." || echo "[publish] Store creation failed."

echo "[publish] Configuring coverage layer: ${LAYER_NAME}"
curl -sf ${AUTH} \
  -X PUT "${BASE}/workspaces/${WORKSPACE}/coveragestores/${STORE_NAME}/coverages/${LAYER_NAME}" \
  -H "Content-Type: application/json" \
  -d "{
    \"coverage\": {
      \"name\": \"${LAYER_NAME}\",
      \"title\": \"${TITLE}\",
      \"enabled\": true,
      \"srs\": \"EPSG:4326\"
    }
  }" && echo "[publish] Layer configured." || echo "[publish] Layer config failed."

echo ""
echo "─────────────────────────────────────────────────────"
echo "Layer: ${WORKSPACE}:${LAYER_NAME}"
echo "WMS:  ${GEOSERVER_URL}/${WORKSPACE}/wms?service=WMS&version=1.3.0&request=GetCapabilities"
echo "WMTS: ${GEOSERVER_URL}/gwc/service/wmts?REQUEST=GetCapabilities"
echo "WCS:  ${GEOSERVER_URL}/${WORKSPACE}/wcs?service=WCS&version=2.0.1&request=GetCapabilities"
