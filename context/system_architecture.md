# System Architecture — Geospatial Image Publishing Platform

## Overview

OGC-ready geospatial raster publishing platform. Receives drone images, processes
them via GDAL, stores in cloud buckets, and publishes as WMS/WMTS/WCS services
via GeoServer.

## Architecture Diagram

```
Frontend (WebGIS / ArcGIS / QGIS)
         ↓
  [API] GET /upload/signed-url
         ↓
  Direct upload → Cloud Storage (GCS / MinIO)
         ↓
  Storage event trigger → message queue (Redis Streams)
         ↓
  [Worker] consumes queue
         ↓
  GDAL Pipeline:
    1. Reproject → EPSG:4326 (or target CRS)
    2. Convert to COG (Cloud Optimized GeoTIFF)
    3. Build overviews / pyramids
         ↓
  Write processed COG → Storage bucket (processed/)
         ↓
  [Worker] calls GeoServer REST API
         ↓
  GeoServer registers store + layer
         ↓
  OGC Services: WMS / WMTS / WCS
         ↓
  [API] returns service URLs to client
```

## Components

| Component | Tech        | Responsibility                        | Port |
|-----------|-------------|---------------------------------------|------|
| API       | FastAPI     | Orchestration, signed URLs, status    | 8000 |
| Worker    | Python+GDAL | Async GDAL pipeline, GeoServer calls  | —    |
| Storage   | MinIO/GCS   | Blob persistence (raw + processed)    | 9000 |
| Queue     | Redis       | Decouple API ↔ Worker                 | 6379 |
| GeoServer | Java WAR    | OGC services (WMS/WMTS/WCS)           | 8080 |
| DB        | PostgreSQL  | Image metadata, processing status     | 5432 |

## Data Flow

### Upload Flow
1. Client requests signed URL → `POST /api/upload/signed-url`
2. API generates pre-signed URL from storage client
3. Client uploads directly to bucket (bypasses API)
4. Bucket triggers event → published to Redis Streams key `image:uploaded`

### Processing Flow
1. Worker reads from `image:uploaded` stream
2. Downloads raw file from bucket
3. Runs GDAL pipeline (reproject → COG → overviews)
4. Uploads processed COG to `processed/` prefix in bucket
5. Updates DB record: status = `processed`
6. Publishes event to `image:processed` stream

### Publication Flow
1. Worker reads from `image:processed` stream
2. Calls GeoServer REST API to create:
   - Coverage Store (GeoTIFF from bucket path)
   - Coverage Layer
   - Configured WMS/WMTS endpoints
3. Updates DB record: status = `published`, stores OGC URLs
4. API returns service URLs to client via `GET /api/images/{id}`

## Architectural Decisions

### ADR-001: Signed URLs for Upload
**Decision**: Direct-to-bucket upload via signed URLs.
**Reason**: Avoids API bandwidth bottleneck for large raster files (100MB+).
**Trade-off**: Requires bucket CORS configuration.

### ADR-002: Redis Streams for Decoupling
**Decision**: Redis Streams as event bus between API and Worker.
**Reason**: Lightweight, persistent, supports consumer groups for horizontal scaling.
**Trade-off**: Additional infra component; Redis Pub/Sub considered but lacks persistence.

### ADR-003: COG as Output Format
**Decision**: All processed rasters stored as Cloud Optimized GeoTIFF.
**Reason**: COG supports efficient HTTP range requests; compatible with GeoServer, QGIS, ArcGIS.
**Trade-off**: Larger overviews storage footprint.

### ADR-004: GeoServer for OGC Services
**Decision**: GeoServer as OGC publication layer.
**Reason**: Production-grade WMS/WMTS/WCS support, mature REST API, ArcGIS compatible.
**Trade-off**: Java-based, heavier than alternatives; managed via REST API only.

### ADR-005: MinIO for Local, GCS for Production
**Decision**: MinIO in dev/MVP, GCS interface-compatible in production.
**Reason**: Same S3-compatible API, zero cloud cost during development.
**Trade-off**: Slight GCS SDK differences for signed URLs in prod.

## Environment Variables

```env
# Storage
STORAGE_BACKEND=minio            # minio | gcs
STORAGE_ENDPOINT=http://minio:9000
STORAGE_ACCESS_KEY=minioadmin
STORAGE_SECRET_KEY=minioadmin
STORAGE_BUCKET_RAW=raw-images
STORAGE_BUCKET_PROCESSED=processed-images

# Queue
REDIS_URL=redis://redis:6379/0

# GeoServer
GEOSERVER_URL=http://geoserver:8080/geoserver
GEOSERVER_ADMIN_USER=admin
GEOSERVER_ADMIN_PASSWORD=geoserver
GEOSERVER_WORKSPACE=geoimages

# Database
DATABASE_URL=postgresql+asyncpg://geo:geo@postgres:5432/geodb

# API
API_SECRET_KEY=changeme
SIGNED_URL_EXPIRY_SECONDS=3600
```

## Scalability

- **API**: Stateless FastAPI → scale horizontally behind load balancer
- **Worker**: Multiple replicas reading same Redis Streams consumer group
- **GeoServer**: Clustered mode with shared data directory on NFS/GCS
- **Storage**: Object storage → infinite horizontal scale

## Future Evolution

- Multi-tenant SaaS: add `tenant_id` to all models + storage prefix isolation
- NDVI / raster analysis: add analysis pipeline step in Worker
- Distributed processing: replace Redis Streams with Kafka / Cloud Pub/Sub
- Tile caching: add GeoWebCache (bundled with GeoServer) or external MapProxy
