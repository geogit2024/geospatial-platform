from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from config import get_settings
from models import Base
from services.plan_seeder import seed_default_plans, ensure_default_subscription

settings = get_settings()

# NullPool: Cloud Run scales to zero — persistent connection pools are useless and
# cause stale-connection errors on cold starts. Each request gets a fresh connection.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _apply_schema_compatibility_updates(conn)

    async with AsyncSessionLocal() as session:
        await seed_default_plans(session)
        await ensure_default_subscription(session, tenant_external_id=settings.default_tenant_id)


async def _apply_schema_compatibility_updates(conn) -> None:
    # Backfill support for installs where `images` table already exists without tenant_id.
    if conn.dialect.name == "postgresql":
        await conn.execute(
            text(
                """
                ALTER TABLE images
                ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'default';
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_images_tenant_id ON images (tenant_id);
                """
            )
        )


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
