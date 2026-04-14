from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import init_db
from services.storage import ensure_buckets
from routers import upload_router, images_router, services_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
    except Exception as e:
        print(f"[WARN] DB init failed (will retry on request): {e}")
    try:
        ensure_buckets()
    except Exception as e:
        print(f"[WARN] Could not ensure storage buckets: {e}")
    yield


app = FastAPI(
    title="Geospatial Image Publishing Platform",
    description=(
        "OGC-ready platform for raster ingestion, GDAL processing, "
        "and WMS/WMTS/WCS publication via GeoServer."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api")
app.include_router(images_router, prefix="/api")
app.include_router(services_router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "geospatial-api",
        "storage_public_url": settings.storage_public_url or "(not set)",
        "storage_endpoint": settings.storage_endpoint,
    }
