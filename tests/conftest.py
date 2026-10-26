import asyncio
import sys

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from financial_assistant.config import Settings
from financial_assistant.persistence.executions import ExecutionStore
from financial_assistant.persistence.tables import Base

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def settings(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"
    return Settings(
        environment="test",
        database_url=url,
        source_database_url=url,
        checkpoint_url="unused",
        dev_auth_enabled=True,
        dev_token="test-token-" + "x" * 32,
    )


@pytest.fixture
async def store(settings):
    engine = create_async_engine(settings.database_url.get_secret_value())
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield ExecutionStore(async_sessionmaker(engine, expire_on_commit=False), settings)
    await engine.dispose()
