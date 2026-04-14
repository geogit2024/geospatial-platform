from pydantic_settings import BaseSettings
from functools import lru_cache


class WorkerSettings(BaseSettings):
    # Storage
    storage_backend: str = "minio"
    storage_endpoint: str = "http://minio:9000"
    storage_public_url: str = ""          # Public HTTPS URL for GeoServer to reach processed COGs
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket_raw: str = "raw-images"
    storage_bucket_processed: str = "processed-images"

    # Redis
    redis_url: str = "redis://redis:6379/0"
    redis_stream_uploaded: str = "image:uploaded"
    redis_stream_processed: str = "image:processed"
    redis_consumer_group: str = "workers"

    # GeoServer
    geoserver_url: str = "http://geoserver:8080/geoserver"           # internal — REST API calls
    geoserver_public_url: str = ""                                    # public HTTPS — OGC URLs for clients
    geoserver_admin_user: str = "admin"
    geoserver_admin_password: str = "geoserver"
    geoserver_workspace: str = "geoimages"
    geoserver_data_dir: str = "/opt/geoserver_data"

    # Database
    database_url: str = "postgresql+asyncpg://geo:geo@postgres:5432/geodb"

    # Worker
    worker_concurrency: int = 4
    target_crs: str = "EPSG:3857"  # Web Mercator — required by ArcGIS Online / Leaflet

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
