from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Storage — GCS (credentials via ADC, no keys needed)
    storage_bucket_raw: str = "raw-images-geopublish"
    storage_bucket_processed: str = "processed-images-geopublish"

    # Redis
    redis_url: str = "redis://redis:6379/0"
    redis_stream_uploaded: str = "image:uploaded"
    redis_stream_processed: str = "image:processed"
    redis_consumer_group: str = "workers"

    # GeoServer
    geoserver_url: str = "http://geoserver:8080/geoserver"
    geoserver_public_url: str = ""
    geoserver_admin_user: str = "admin"
    geoserver_admin_password: str = "geoserver"
    geoserver_workspace: str = "geoimages"
    geoserver_data_dir: str = "/opt/geoserver_data"
    vector_default_datastore: str = "postgis_ds"
    postgis_schema: str = "public"

    # Database
    database_url: str = "postgresql+asyncpg://geo:geo@postgres:5432/geodb"

    # API
    api_secret_key: str = "changeme"
    signed_url_expiry_seconds: int = 3600
    cors_origins: str = "http://localhost:3000,http://localhost:8080,https://geopublish-frontend-owbbo3ghkq-uc.a.run.app,https://geopublish-frontend-758336857324.us-central1.run.app"
    cors_origin_regex: str = r"https://([a-zA-Z0-9-]+\.)*(arcgis\.com|arcgisonline\.com)"

    # Metrics
    default_tenant_id: str = "default"
    metrics_default_window_days: int = 30
    metrics_max_window_days: int = 365
    metrics_top_files_limit: int = 5
    metrics_storage_cache_ttl_seconds: int = 300
    metrics_cost_cache_ttl_seconds: int = 1800
    billing_cost_source: str = "configured"  # configured | gcp_billing_export
    billing_currency: str = "BRL"
    cost_per_gb_month: float = 0.15
    cost_per_process: float = 0.05
    cost_per_download: float = 0.01
    gcp_project_id: str = ""
    gcp_billing_export_project: str = ""
    gcp_billing_export_table: str = ""
    ogc_access_log_batch_size: int = 200
    ogc_access_log_flush_interval_seconds: int = 5
    ogc_access_log_sample_rate_high_volume: float = 0.1

    # Worker trigger — starts the Cloud Run Job on demand after queueing work.
    worker_job_trigger_enabled: bool = False
    worker_job_project_id: str = ""
    worker_job_region: str = "us-central1"
    worker_job_name: str = "geopublish-worker-job"
    worker_job_trigger_lock_enabled: bool = True
    worker_job_trigger_lock_key: str = "worker:cloud-run-job:trigger-lock"
    worker_job_trigger_lock_ttl_seconds: int = 60

    # Email (SMTP)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "GeoPublish"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    app_public_url: str = "http://localhost:3000"
    upload_max_size_mb: int = 2048

    # Upload cost estimate (pre-processing simulation)
    upload_cost_estimate_enabled_default: bool = False
    upload_cost_estimate_force_enabled: bool = False
    upload_cost_estimate_feature_key: str = "upload_cost_estimate_v1"
    upload_cost_estimate_session_ttl_minutes: int = 120
    upload_cost_estimate_temp_bucket: str = ""
    upload_cost_estimate_temp_prefix: str = "tmp/cost-estimate"
    upload_cost_estimate_temp_signed_url_expiry_seconds: int = 900
    upload_cost_estimate_default_monthly_downloads: int = 100
    upload_cost_estimate_default_avg_download_size_ratio: float = 0.35
    upload_cost_estimate_default_processed_size_ratio_raster: float = 0.65
    upload_cost_estimate_default_processed_size_ratio_vector: float = 0.35
    upload_cost_estimate_default_processing_base_units: float = 1.0
    upload_cost_estimate_default_processing_units_per_gb_raster: float = 2.0
    upload_cost_estimate_default_processing_units_per_gb_vector: float = 1.2
    upload_cost_estimate_default_uncertainty_min_factor: float = 0.7
    upload_cost_estimate_default_uncertainty_max_factor: float = 1.4

    # Processing strategy/cost controls
    raster_target_crs: str = "EPSG:3857"
    raster_skip_reproject_if_same_crs: bool = True
    raster_skip_cog_if_already_cog: bool = True
    raster_generate_overviews_min_mb: int = 100
    vector_light_max_mb: int = 20
    vector_light_max_features: int = 10000


@lru_cache
def get_settings() -> Settings:
    return Settings()
