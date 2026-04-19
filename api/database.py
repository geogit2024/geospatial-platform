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
        statements = [
            """
            ALTER TABLE images
            ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'default';
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_images_tenant_id ON images (tenant_id);
            """,
            "ALTER TABLE images ADD COLUMN IF NOT EXISTS wfs_url TEXT;",
            "ALTER TABLE images ADD COLUMN IF NOT EXISTS asset_kind VARCHAR(32);",
            "ALTER TABLE images ADD COLUMN IF NOT EXISTS source_format VARCHAR(64);",
            "ALTER TABLE images ADD COLUMN IF NOT EXISTS geometry_type VARCHAR(64);",
            "ALTER TABLE images ADD COLUMN IF NOT EXISTS workspace VARCHAR(128);",
            "ALTER TABLE images ADD COLUMN IF NOT EXISTS datastore VARCHAR(128);",
            "ALTER TABLE images ADD COLUMN IF NOT EXISTS postgis_table VARCHAR(128);",
            """
            CREATE TABLE IF NOT EXISTS layers_metadata (
                id VARCHAR(36) PRIMARY KEY,
                image_id VARCHAR(36) NOT NULL UNIQUE,
                nome VARCHAR(512) NOT NULL,
                tipo VARCHAR(64) NOT NULL,
                geometry_type VARCHAR(64),
                tabela_postgis VARCHAR(128),
                workspace VARCHAR(128),
                datastore VARCHAR(128),
                wms_url TEXT,
                wfs_url TEXT,
                bbox TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """,
            "CREATE INDEX IF NOT EXISTS ix_layers_metadata_image_id ON layers_metadata (image_id);",
        ]
        for statement in statements:
            await conn.execute(text(statement))


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
