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


@lru_cache
def get_settings() -> Settings:
    return Settings()
