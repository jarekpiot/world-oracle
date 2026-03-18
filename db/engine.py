"""
World Oracle — Database Engine
Async SQLAlchemy engine, session factory, and connection management.

Reads DATABASE_URL from environment:
  postgresql://...          → production (Railway injects this)
  sqlite+aiosqlite:///...   → local dev / tests
"""

import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker


def get_database_url() -> str:
    """Get and normalize DATABASE_URL from environment."""
    url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///world_oracle.db")

    # Railway uses postgres:// but asyncpg needs postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # SQLite needs aiosqlite driver
    if url.startswith("sqlite:///") and "+aiosqlite" not in url:
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    return url


DATABASE_URL = get_database_url()

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
    **({"pool_size": 5, "max_overflow": 10} if "postgresql" in DATABASE_URL else {}),
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    """Dependency for FastAPI — yields an async session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Create all tables. Used for dev/tests. Production uses Alembic."""
    from db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Dispose engine on shutdown."""
    await engine.dispose()
