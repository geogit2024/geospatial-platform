from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Storage — GCS (credentials via ADC, no keys needed)
    storage_bucket_raw: str = "raw-images-geopublish"
    storage_bucket_processed: str = "imagens-processadas-geopublicas"

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
    cors_origins: str = "http://localhost:3000,http://localhost:8080"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
