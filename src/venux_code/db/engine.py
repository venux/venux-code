"""Async SQLAlchemy engine and session factory for Venux Code.

Uses ``aiosqlite`` as the async SQLite driver.

Usage::

    from venux_code.db.engine import get_engine, get_session_factory, init_db

    await init_db()                        # create tables
    async with get_session_factory()() as session:
        ...
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from venux_code.db.models import Base

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine(url: Optional[str] = None, echo: bool = False) -> AsyncEngine:
    """Return (and lazily create) the module-level async engine.

    Parameters
    ----------
    url:
        SQLAlchemy database URL.  Falls back to the ``Settings.db_url``
        when *None*.
    echo:
        If *True*, emit SQL statements to stderr.
    """
    global _engine
    if _engine is None:
        if url is None:
            from venux_code.config.settings import get_settings

            url = get_settings().db_url
        _engine = create_async_engine(url, echo=echo)
    return _engine


def get_session_factory(
    url: Optional[str] = None, echo: bool = False
) -> async_sessionmaker[AsyncSession]:
    """Return (and lazily create) an ``async_sessionmaker`` bound to the engine."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine(url=url, echo=echo)
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def scoped_session(
    url: Optional[str] = None, echo: bool = False
) -> AsyncGenerator[AsyncSession, None]:
    """Convenience context manager that yields an ``AsyncSession``.

    Commits on success, rolls back on exception, and always closes.
    """
    factory = get_session_factory(url=url, echo=echo)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(url: Optional[str] = None, echo: bool = False) -> None:
    """Create all tables defined in ``Base.metadata``."""
    engine = get_engine(url=url, echo=echo)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Dispose the engine and clear cached references (useful in tests)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None
