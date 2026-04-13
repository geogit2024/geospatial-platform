#!/bin/sh
# Startup script — reads Railway-injected PORT
echo "Starting API on port ${PORT:-8000}"
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 2
