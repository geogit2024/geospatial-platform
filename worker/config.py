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
    postgis_schema: str = "public"

    # Worker
    worker_concurrency: int = 4
    target_crs: str = "EPSG:3857"  # Web Mercator - required by ArcGIS Online / Leaflet
    worker_heartbeat_seconds: int = 20
    worker_enable_stalled_recovery: bool = True
    worker_recover_processing_minutes: int = 30
    worker_recover_publishing_minutes: int = 20
    worker_mode: str = "service"  # service | job
    worker_enable_health_server: bool = True
    worker_enable_startup_sync: bool = True
    worker_job_idle_exit_seconds: int = 45
    worker_job_max_runtime_seconds: int = 540
    worker_job_block_ms: int = 4000
    worker_job_batch_count: int = 8

    # Redis stream resilience
    redis_claim_min_idle_ms: int = 900000
    redis_claim_batch: int = 10
    redis_claim_interval_seconds: int = 30

    # Vector pipeline / GeoServer publication
    vector_workspace_prefix: str = "user"
    vector_default_datastore: str = "postgis_ds"
    vector_processing_timeout_seconds: int = 900
    vector_publish_timeout_seconds: int = 120
    vector_simplify_tolerance: float = 0.0
    vector_simplify_min_features: int = 5000

    # Processing strategy/cost controls
    raster_target_crs: str = "EPSG:3857"
    raster_skip_reproject_if_same_crs: bool = True
    raster_skip_cog_if_already_cog: bool = True
    raster_generate_overviews_min_mb: int = 100
    vector_light_max_mb: int = 20
    vector_light_max_features: int = 10000

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
