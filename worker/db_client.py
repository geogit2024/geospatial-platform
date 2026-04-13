from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncSession:
    return AsyncSessionLocal()
