#!/bin/sh
# Cloud Run: single worker (scaling is handled at service level)
PORT="${PORT:-8080}"
echo "Starting API on port ${PORT}"
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}"
