import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("FIREBASE_PROJECT_ID", "test-project")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")
os.environ.setdefault("ENVIRONMENT", "development")
# File-backed SQLite so sync TestClient, asyncio.run() seeds, and httpx share one DB
# (:memory: is not shared across connections / event loops). Override for Postgres CI.
if "DATABASE_URL" not in os.environ:
    _fd, _test_sqlite_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(_fd)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_sqlite_path}"

from app.main import app


def _register_pytest_error_routes() -> None:
    from fastapi import APIRouter

    r = APIRouter()

    @r.get("/__pytest/unhandled")
    async def _unhandled() -> None:
        raise RuntimeError("pytest intentional")

    app.include_router(r, prefix="/api/v1")


_register_pytest_error_routes()


@pytest.fixture(scope="session", autouse=True)
def _init_test_schema():
    from app.db.base import init_db

    asyncio.run(init_db())
    yield


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
