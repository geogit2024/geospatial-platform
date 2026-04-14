import os
import boto3
from botocore.config import Config
from config import get_settings

settings = get_settings()

_s3_client = None


def get_s3():
    global _s3_client
    if _s3_client is None:
        kwargs = dict(
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            region_name="us-east-1",
        )
        if settings.storage_backend == "minio":
            kwargs["endpoint_url"] = settings.storage_endpoint
            kwargs["config"] = Config(
                signature_version="s3v4",
                # Disable multipart threshold so s3transfer doesn't need ContentLength
            )
        _s3_client = boto3.client("s3", **kwargs)
    return _s3_client


def download_from_bucket(bucket: str, key: str, local_path: str) -> None:
    """Download using get_object() to avoid s3transfer's ContentLength requirement.
    s3.download_file() uses s3transfer which calls HeadObject and expects ContentLength
    in the response — Railway's HTTPS proxy may strip this header, causing KeyError.
    """
    s3 = get_s3()
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    response = s3.get_object(Bucket=bucket, Key=key)
    with open(local_path, "wb") as f:
        # Stream in chunks to handle large files
        for chunk in response["Body"].iter_chunks(chunk_size=8 * 1024 * 1024):
            f.write(chunk)


def generate_cog_url(bucket: str, key: str, ttl_seconds: int = 60 * 60 * 24 * 365) -> str:
    """Generate a long-lived presigned HTTPS URL for GeoServer to read the COG.
    Uses the same endpoint as the internal client (STORAGE_ENDPOINT).
    GeoServer must be able to reach this URL from its container.
    """
    s3 = get_s3()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=ttl_seconds,
    )


def upload_to_bucket(local_path: str, bucket: str, key: str) -> None:
    """Upload using put_object() to avoid s3transfer's ContentLength requirement."""
    s3 = get_s3()
    file_size = os.path.getsize(local_path)
    with open(local_path, "rb") as f:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=f,
            ContentLength=file_size,
        )
