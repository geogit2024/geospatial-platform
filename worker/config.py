from pydantic_settings import BaseSettings
from functools import lru_cache


class WorkerSettings(BaseSettings):
    # Storage - GCS (credentials via ADC, no keys needed)
    storage_bucket_raw: str = "raw-images-geopublish"
    storage_bucket_processed: str = "processed-images-geopublish"

    # Redis
    redis_url: str = "redis://redis:6379/0"
    redis_stream_uploaded: str = "image:uploaded"
    redis_stream_processed: str = "image:processed"
    redis_consumer_group: str = "workers"

    # GeoServer
    geoserver_url: str = "http://geoserver:8080/geoserver"  # internal - REST API calls
    geoserver_public_url: str = ""  # public HTTPS - OGC URLs for clients
    geoserver_admin_user: str = "admin"
    geoserver_admin_password: str = "geoserver"
    geoserver_workspace: str = "geoimages"
    geoserver_data_dir: str = "/opt/geoserver_data"

    # Database
    database_url: str = "postgresql+asyncpg://geo:geo@postgres:5432/geodb"

    # Worker
    worker_concurrency: int = 4
    target_crs: str = "EPSG:3857"  # Web Mercator - required by ArcGIS Online / Leaflet
    worker_heartbeat_seconds: int = 20
    worker_enable_stalled_recovery: bool = True
    worker_recover_processing_minutes: int = 30
    worker_recover_publishing_minutes: int = 20

    # Redis stream resilience
    redis_claim_min_idle_ms: int = 120000
    redis_claim_batch: int = 10
    redis_claim_interval_seconds: int = 15

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
