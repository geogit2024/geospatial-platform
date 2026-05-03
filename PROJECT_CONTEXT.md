# PROJECT_CONTEXT

## Project Objective
Build and operate a geospatial publishing platform that ingests raster/vector data, processes assets with Python workers (GDAL/geospatial pipeline), and publishes interoperable OGC services (WMS/WMTS/WCS/WFS) via GeoServer.

## Tech Stack
- Backend API: Python, FastAPI, Uvicorn, SQLAlchemy (async), Pydantic Settings
- Worker: Python async worker, Redis Streams, GDAL/GeoPandas pipeline, GeoServer REST integration
- Frontend: Next.js 14, React 18, TypeScript, Tailwind
- Infra/Runtime: Docker Compose, PostgreSQL, Redis, MinIO, GeoServer

## Architecture Overview
1. Client requests signed upload URL from API.
2. Asset is uploaded to object storage (MinIO in dev; GCS-compatible pattern in production).
3. API/queue event triggers worker processing.
4. Worker normalizes/processes data and stores processed output.
5. Worker publishes layer/store in GeoServer.
6. API exposes metadata and OGC endpoints to frontend/clients.

## Key Modules
- `api/`: FastAPI orchestration, models, routers, services, metrics, auth-related API behavior
- `worker/`: queue consumers, raster/vector processing pipeline, GeoServer publication and recovery flows
- `frontend/`: Next.js app and dashboard/UI pages
- `tests/`: API/processing/metrics behavior tests
- `geoserver/`, `minio/`: service-specific helper scripts/config
- `context/`: architecture and system documentation

## Development Rules
- Keep business logic in `api/` and `worker/`; do not duplicate processing logic in frontend.
- Use `.env` at repository root as the single local environment source.
- Prefer local virtual environment (`.venv`) for Python and local `frontend/node_modules` for Node.js.
- Docker is the default local execution path for development parity.
- After code changes, rebuild and rerun containers via workspace Docker tasks.
- Use local `.venv` run/debug only as an optional fallback for isolated debugging.
- Do not commit credentials or generated secrets.

## Environment Isolation
- Python interpreter target: `./.venv/Scripts/python.exe` (workspace default).
- Python packages: install via `api/requirements.txt` and `worker/requirements.txt` into local `.venv`.
- Node packages: install via `frontend/package-lock.json` with `npm ci`.
- Environment variables: keep in root `.env` (project-specific, not global shell config).
- Runtime services: use `docker compose` for full local stack parity.

## Recommended Local Workflow
1. Copy `.env.example` to `.env` and adjust values.
2. Run task `Docker: Dev up (build)` (or `Docker: Dev up (build, detached)`).
3. When code changes in `api/` or `worker/`, run:
- `Docker: Rebuild API` for API changes
- `Docker: Rebuild Worker` for worker changes
4. Use `Docker: Logs` to follow runtime output and `Docker: Down` to stop services.
5. Use local tasks/debug only when container debugging is not necessary.

## AI Agent Guidance
- Read `PROJECT_CONTEXT.md`, `README.md`, and `context/system_architecture.md` before major changes.
- Preserve module boundaries (`api`, `worker`, `frontend`).
- Favor minimal, reversible configuration changes.
- Validate with module-appropriate tests before proposing merges.
