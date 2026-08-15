"""async engine / sessionmaker（SQLAlchemy 2.0 async）。"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from api.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        # ★ NullPool：Celery 任务各自 asyncio.run() 新建事件循环，共享连接池会跨循环复用
        #   导致 'Event loop is closed' / 'NoneType' send。用 NullPool 连接按需创建即用即弃，
        #   彻底消除跨循环连接复用问题（本系统信号频率低，连接开销可忽略）。
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_pre_ping=True,
            poolclass=NullPool,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每请求一个 session。"""
    factory = get_session_factory()
    async with factory() as session:
        yield session
