import json
import redis.asyncio as aioredis
from config import get_settings

settings = get_settings()

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def publish_upload_event(image_id: str, raw_key: str, filename: str) -> None:
    r = await get_redis()
    await r.xadd(
        settings.redis_stream_uploaded,
        {
            "image_id": image_id,
            "raw_key": raw_key,
            "filename": filename,
        },
    )


async def publish_processed_event(image_id: str, processed_key: str, metadata: dict) -> None:
    r = await get_redis()
    payload = {"image_id": image_id, "processed_key": processed_key}
    payload.update({k: str(v) for k, v in metadata.items()})
    await r.xadd(settings.redis_stream_processed, payload)
