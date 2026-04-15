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
    # Run DB init in background so it never blocks uvicorn from binding to PORT.
    # Tables are created via migrations or Cloud SQL Studio on first deploy.
    import asyncio
    async def _init_db_background():
        try:
            await asyncio.wait_for(init_db(), timeout=10.0)
            print("[INFO] DB init completed")
        except asyncio.TimeoutError:
            print("[WARN] DB init timed out — server starting anyway")
        except Exception as e:
            print(f"[WARN] DB init failed — server starting anyway: {e}")
    asyncio.create_task(_init_db_background())
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
    return {"status": "ok", "service": "geospatial-api"}
