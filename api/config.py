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
    billing_cost_source: str = "configured"  # configured | gcp_billing_export
    billing_currency: str = "BRL"
    cost_per_gb_month: float = 0.15
    cost_per_process: float = 0.05
    cost_per_download: float = 0.01
    gcp_project_id: str = ""
    gcp_billing_export_project: str = ""
    gcp_billing_export_table: str = ""

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
