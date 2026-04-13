# Geospatial Image Publishing Platform

OGC-ready platform for raster ingestion, GDAL processing, and WMS/WMTS/WCS
publication via GeoServer. Designed for drone imagery and high-resolution
raster datasets.

## Architecture

```
Client
  │
  ├── POST /api/upload/signed-url  →  API generates signed URL
  │                                   Client uploads directly to MinIO
  ├── POST /api/upload/confirm     →  API enqueues processing job
  │
  │   Redis Stream: image:uploaded
  │        │
  │   [Worker] GDAL Pipeline
  │        ├── gdalwarp  → reproject to EPSG:4326
  │        ├── gdaladdo  → build overviews/pyramids
  │        └── gdal_translate → export as COG
  │
  │   Redis Stream: image:processed
  │        │
  │   [Worker] GeoServer REST API
  │        └── register Coverage Store + Layer
  │
  └── GET /api/services/{id}/ogc  →  WMS / WMTS / WCS URLs
```

## Services

| Service   | Port | Description                        |
|-----------|------|------------------------------------|
| API       | 8000 | FastAPI REST service               |
| GeoServer | 8080 | OGC WMS/WMTS/WCS publication       |
| MinIO     | 9000 | S3-compatible object storage       |
| MinIO UI  | 9001 | MinIO web console                  |
| PostgreSQL| 5432 | Metadata database (internal)       |
| Redis     | 6379 | Event queue (internal)             |

## Quick Start

```bash
# 1. Clone / copy and configure environment
cp .env.example .env

# 2. Start all services
docker compose up --build -d

# 3. Wait for GeoServer to fully start (~60s), then init workspace
docker compose exec geoserver \
  curl -u admin:geoserver -X POST http://localhost:8080/geoserver/rest/workspaces \
  -H "Content-Type: application/json" \
  -d '{"workspace":{"name":"geoimages"}}'

# 4. API docs available at:
#    http://localhost:8000/docs
```

## API Endpoints

### Upload

```http
POST /api/upload/signed-url
Content-Type: application/json
{"filename": "survey.tif", "content_type": "image/tiff"}

→ {"image_id": "...", "upload_url": "http://...", "raw_key": "...", "expires_in": 3600}
```

```http
# After uploading file directly to upload_url:
POST /api/upload/confirm
{"image_id": "..."}

→ {"image_id": "...", "status": "uploaded", "message": "Processing queued"}
```

### Images

```http
GET  /api/images/             # List all images (supports ?status=published)
GET  /api/images/{id}         # Get single image with status
DELETE /api/images/{id}       # Delete image record
```

### OGC Services

```http
GET /api/services/{id}/ogc
→ {
    "layer": "geoimages:img_...",
    "services": {
      "wms": {"url": "...", "getcapabilities": "..."},
      "wmts": {"url": "...", "getcapabilities": "..."},
      "wcs": {"url": "...", "getcapabilities": "..."}
    }
  }
```

## Processing Status Flow

```
pending → uploading → uploaded → processing → processed → publishing → published
                                                                   ↘ error
```

## Scaling Workers

```bash
# Scale to 4 worker replicas for parallel processing
docker compose up -d --scale worker=4
```

## Supported Input Formats

GeoTIFF, GeoTIFF (ECW, JP2), and any GDAL-supported raster format:
`.tif`, `.tiff`, `.geotiff`, `.jp2`, `.ecw`, `.img`

## Production Notes

- Replace MinIO with GCS: set `STORAGE_BACKEND=gcs` and configure HMAC keys
- GeoServer clustering: use shared NFS volume for `geoserver_data`
- Redis: use Redis Cluster or managed service (Redis Cloud, Upstash)
- Workers: deploy as Railway / Cloud Run jobs for serverless scale
