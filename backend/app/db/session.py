from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Verify if we should use asyncpg
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

try:
    engine = create_async_engine(db_url, echo=False)
    AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    logger.error(f"Failed to initialize database engine: {e}")
    engine = None
    AsyncSessionLocal = None

Base = declarative_base()

async def get_db():
    if not AsyncSessionLocal:
        raise RuntimeError("Database not initialized")
    async with AsyncSessionLocal() as session:
        yield session
