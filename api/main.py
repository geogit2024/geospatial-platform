import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import init_db
from routers import images_router, services_router, upload_router

settings = get_settings()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("api.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting API — binding to port, DB init runs in background")

    # DB initialization runs in background so Cloud Run readiness is not blocked.
    async def _init_db_background() -> None:
        try:
            await asyncio.wait_for(init_db(), timeout=10.0)
            logger.info("DB init completed")
        except asyncio.TimeoutError:
            logger.warning("DB init timed out; server continues")
        except Exception:
            logger.exception("DB init failed; server continues")

    try:
        asyncio.get_running_loop().create_task(_init_db_background())
    except RuntimeError:
        logger.warning("No running event loop for DB background task; skipping")

    logger.info("API ready — lifespan startup complete")
    yield
    logger.info("API lifespan shutdown complete")


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


@app.get("/")
async def root() -> dict:
    return {"status": "ok"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "geospatial-api"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting uvicorn on 0.0.0.0:%s", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
