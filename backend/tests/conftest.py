"""Pytest test configuration and fixtures."""
import os
import tempfile
from typing import AsyncGenerator
import duckdb
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.init_db import init_system_data
from app.main import app
from app.api.v1.deps import get_db_session

# Set testing environment so lifespan does not attempt connection to default postgres
settings.ENVIRONMENT = "testing"

# Use isolated temporary DuckDB file for analytical testing
_test_duckdb_dir = tempfile.mkdtemp()
_test_duckdb_path = os.path.join(_test_duckdb_dir, "test_askyourdata.duckdb")
settings.DUCKDB_DATABASE_PATH = _test_duckdb_path


def seed_test_duckdb() -> None:
    """Seed test analytical tables into isolated test DuckDB."""
    with duckdb.connect(_test_duckdb_path, read_only=False) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS global_sales (
                category VARCHAR,
                region VARCHAR,
                customer_name VARCHAR,
                units_sold INTEGER,
                total_revenue DOUBLE,
                net_profit DOUBLE
            );
            DELETE FROM global_sales;
            INSERT INTO global_sales VALUES
                ('Technology', 'North America', 'Alice Johnson', 10, 12500.0, 3100.0),
                ('Furniture', 'Europe', 'Bob Smith', 5, 8400.0, 1200.0),
                ('Office Supplies', 'Asia', 'Charlie Brown', 20, 3200.0, 800.0);
        """)


seed_test_duckdb()

# Use in-memory SQLite with StaticPool so all async connections share the same memory DB
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestAsyncSession = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSession() as session:
        await init_system_data(session)
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client with overridden database dependency."""
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
