# GDAL Worker — uses official GDAL Ubuntu image
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.8.4

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 worker

WORKDIR /worker

# Install Python deps (--break-system-packages required on Ubuntu 22.04+)
RUN pip3 install --no-cache-dir --break-system-packages \
    "redis==5.0.4" \
    "boto3==1.34.100" \
    "httpx==0.27.0" \
    "sqlalchemy[asyncio]==2.0.30" \
    "asyncpg==0.29.0" \
    "pydantic-settings==2.2.1"

COPY --chown=worker:worker . .

ENV GDAL_CACHEMAX=512
ENV GDAL_NUM_THREADS=ALL_CPUS
ENV PYTHONUNBUFFERED=1

USER worker

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import redis; r = redis.from_url('${REDIS_URL:-redis://redis:6379}'); r.ping()" || exit 1

CMD ["python3", "worker.py"]
