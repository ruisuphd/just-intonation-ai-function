from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a session and commit when the request handler returns successfully.

    Many routes also call ``await db.commit()`` before returning; that is redundant
    but harmless (second commit is effectively a no-op on an already-committed session).
    Prefer explicit commits in multi-step flows; rely on this auto-commit for simple reads.
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    if settings.is_production:
        return
    if not settings.DATABASE_AUTO_CREATE:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
