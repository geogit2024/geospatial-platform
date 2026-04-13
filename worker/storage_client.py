import boto3
from botocore.config import Config
from config import get_settings

settings = get_settings()


def make_s3_client():
    kwargs = dict(
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        region_name="us-east-1",
    )
    if settings.storage_backend == "minio":
        kwargs["endpoint_url"] = settings.storage_endpoint
        kwargs["config"] = Config(signature_version="s3v4")
    return boto3.client("s3", **kwargs)


def download_from_bucket(bucket: str, key: str, local_path: str) -> None:
    s3 = make_s3_client()
    s3.download_file(bucket, key, local_path)


def upload_to_bucket(local_path: str, bucket: str, key: str) -> None:
    s3 = make_s3_client()
    s3.upload_file(local_path, bucket, key)
