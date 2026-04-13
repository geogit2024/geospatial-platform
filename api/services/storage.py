import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from config import get_settings

settings = get_settings()


def _make_s3_client():
    kwargs = dict(
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        region_name="us-east-1",
    )
    if settings.storage_backend == "minio":
        kwargs["endpoint_url"] = settings.storage_endpoint
        kwargs["config"] = Config(signature_version="s3v4")
    return boto3.client("s3", **kwargs)


_s3 = None


def get_s3():
    global _s3
    if _s3 is None:
        _s3 = _make_s3_client()
    return _s3


def ensure_buckets() -> None:
    s3 = get_s3()
    for bucket in [settings.storage_bucket_raw, settings.storage_bucket_processed]:
        try:
            s3.head_bucket(Bucket=bucket)
        except ClientError:
            s3.create_bucket(Bucket=bucket)


def generate_upload_url(key: str, content_type: str = "image/tiff") -> str:
    s3 = get_s3()
    return s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.storage_bucket_raw,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=settings.signed_url_expiry_seconds,
    )


def generate_download_url(bucket: str, key: str) -> str:
    s3 = get_s3()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=settings.signed_url_expiry_seconds,
    )
