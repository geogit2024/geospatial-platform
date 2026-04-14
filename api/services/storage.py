import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from config import get_settings

settings = get_settings()


def _make_s3_client(endpoint_url: str):
    kwargs = dict(
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        region_name="us-east-1",
    )
    if settings.storage_backend == "minio":
        kwargs["endpoint_url"] = endpoint_url
        kwargs["config"] = Config(signature_version="s3v4")
    return boto3.client("s3", **kwargs)


# Internal client — used for bucket operations and worker access
_s3_internal = None
# Public client — used only for generating browser-facing presigned URLs (HTTPS)
_s3_public = None


def get_s3():
    """Internal S3 client (fast, HTTP, within Railway network)."""
    global _s3_internal
    if _s3_internal is None:
        _s3_internal = _make_s3_client(settings.storage_endpoint)
    return _s3_internal


def get_s3_public():
    """S3 client configured with the public HTTPS endpoint.
    Presigned URLs generated here are reachable by browsers.
    Falls back to internal client when storage_public_url is not set (dev).
    """
    global _s3_public
    if _s3_public is None:
        public_url = settings.storage_public_url or settings.storage_endpoint
        _s3_public = _make_s3_client(public_url)
    return _s3_public


_PUBLIC_READ_POLICY = """{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"AWS": ["*"]},
    "Action": ["s3:GetObject"],
    "Resource": ["arn:aws:s3:::{bucket}/*"]
  }]
}"""


def ensure_buckets() -> None:
    s3 = get_s3()
    for bucket in [settings.storage_bucket_raw, settings.storage_bucket_processed]:
        try:
            s3.head_bucket(Bucket=bucket)
        except ClientError:
            s3.create_bucket(Bucket=bucket)

    # Make processed bucket publicly readable so GeoServer can fetch COGs via plain URL
    # (presigned URLs cannot exceed MinIO's 7-day TTL limit)
    try:
        s3.put_bucket_policy(
            Bucket=settings.storage_bucket_processed,
            Policy=_PUBLIC_READ_POLICY.format(bucket=settings.storage_bucket_processed),
        )
    except ClientError as e:
        print(f"[WARN] Could not set public policy on {settings.storage_bucket_processed}: {e}")


def generate_upload_url(key: str, content_type: str = "image/tiff") -> str:
    """Generate a presigned PUT URL using the public endpoint so browsers can upload directly."""
    return get_s3_public().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.storage_bucket_raw,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=settings.signed_url_expiry_seconds,
    )


def generate_download_url(bucket: str, key: str) -> str:
    """Generate a presigned GET URL using the public endpoint."""
    return get_s3_public().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=settings.signed_url_expiry_seconds,
    )
