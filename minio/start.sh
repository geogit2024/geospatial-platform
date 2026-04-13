#!/bin/sh
# MinIO start script — uses Railway-injected PORT for S3 API
MINIO_PORT="${PORT:-9000}"
echo "Starting MinIO server on port ${MINIO_PORT}"
exec minio server /data \
  --address ":${MINIO_PORT}" \
  --console-address ":9001"
