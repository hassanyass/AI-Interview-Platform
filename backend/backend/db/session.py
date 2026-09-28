from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import declarative_base
from backend.core.config import settings
import logging
from urllib.parse import urlsplit, parse_qsl

logger = logging.getLogger(__name__)

# Build the async DSN.
#
# We deliberately do NOT just string-replace the scheme on the raw
# DATABASE_URL and hand that string to create_async_engine/make_url.
# SQLAlchemy's own DSN parser splits user:pass@host on the FIRST "@",
# so a password containing an unescaped "@" (or other reserved char)
# gets silently misparsed — the tail of the password gets prepended to
# the hostname (e.g. "...1962@aws-0-....pooler.supabase.com" instead of
# just the real hostname), which then fails DNS resolution in a way
# that's easy to mistake for a network/DNS bug rather than a URL bug.
# urlsplit() is lenient (splits on the LAST "@", matching RFC 3986 /
# browser behavior), so we parse with that and rebuild the DSN via
# URL.create(), which percent-encodes each component correctly instead
# of re-serializing an ambiguous string.
raw_url = settings.DATABASE_URL
parts = urlsplit(raw_url)
db_url = URL.create(
    "postgresql+asyncpg",
    username=parts.username,
    password=parts.password,
    host=parts.hostname,
    port=parts.port,
    database=parts.path.lstrip("/") or None,
    query=dict(parse_qsl(parts.query)),
)

# Fail closed (H2-B): a DATABASE_URL the engine cannot even parse used to
# leave `engine = None` and let the process boot, 500ing on first use.
# Now the import raises and the process does not start. Connectivity is
# not checked here (the engine connects lazily) -- /ready reports that.
engine = create_async_engine(
    db_url,
    echo=False,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
    pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
    # A connection the pooler/NAT silently dropped is detected and replaced
    # instead of surfacing as one failed request.
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
