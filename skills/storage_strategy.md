# Skill: Storage Strategy (MinIO / GCS)

## Purpose
Abstract cloud object storage using an S3-compatible interface. Dev uses MinIO,
production uses GCS (via HMAC keys for S3-compatible API) or AWS S3.

## Bucket Structure
```
raw-images/
  └── {tenant_id}/{image_id}/original.{ext}

processed-images/
  └── {tenant_id}/{image_id}/cog.tif
```

## Python Abstraction (boto3 / S3-compatible)

```python
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import os

class StorageClient:
    def __init__(self):
        self.backend = os.getenv("STORAGE_BACKEND", "minio")
        kwargs = dict(
            aws_access_key_id=os.getenv("STORAGE_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("STORAGE_SECRET_KEY"),
            region_name="us-east-1",
        )
        if self.backend == "minio":
            kwargs["endpoint_url"] = os.getenv("STORAGE_ENDPOINT", "http://minio:9000")
            kwargs["config"] = Config(signature_version="s3v4")
        self.s3 = boto3.client("s3", **kwargs)
        self.raw_bucket = os.getenv("STORAGE_BUCKET_RAW", "raw-images")
        self.processed_bucket = os.getenv("STORAGE_BUCKET_PROCESSED", "processed-images")

    def generate_upload_url(self, key: str, expiry: int = 3600) -> str:
        return self.s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.raw_bucket, "Key": key},
            ExpiresIn=expiry,
        )

    def generate_download_url(self, bucket: str, key: str, expiry: int = 3600) -> str:
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiry,
        )

    def download_file(self, bucket: str, key: str, local_path: str) -> None:
        self.s3.download_file(bucket, key, local_path)

    def upload_file(self, local_path: str, bucket: str, key: str) -> None:
        self.s3.upload_file(local_path, bucket, key)

    def ensure_buckets(self) -> None:
        for bucket in [self.raw_bucket, self.processed_bucket]:
            try:
                self.s3.head_bucket(Bucket=bucket)
            except ClientError:
                self.s3.create_bucket(Bucket=bucket)
```

## Signed URL CORS Policy (MinIO)
```json
{
  "CORSRules": [{
    "AllowedOrigins": ["*"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3600
  }]
}
```
Apply with: `mc anonymous set-json cors.json myminio/raw-images`

## GCS Production Notes
- Use `google-cloud-storage` SDK for full GCS features (IAM, lifecycle)
- For S3-compatible interface: enable HMAC keys under Cloud Storage → Settings
- Set `STORAGE_ENDPOINT=https://storage.googleapis.com`
- GeoServer can access GCS buckets directly via gs:// with service account credentials
