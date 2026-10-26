import os
from uuid import uuid4

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from financial_assistant.config import Settings
from financial_assistant.connectors.databases.postgres import PostgresSources
from financial_assistant.contracts.models import Question
from financial_assistant.ingestion.pipeline import Ingestion
from financial_assistant.ingestion.seed import seed_rows
from financial_assistant.persistence.executions import ExecutionStore
from financial_assistant.persistence.tables import DocumentChunk
from tests.support import DEMO_SCOPE, services

pytestmark = pytest.mark.postgres


class FixedEmbedder:
    def __init__(self):
        self.calls = 0

    async def embed(self, texts, execution_id=None):
        self.calls += 1
        return [[1.0] + [0.0] * 1535 for _ in texts]


@pytest.fixture
async def postgres():
    url = os.environ.get("FIN_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FIN_TEST_POSTGRES_URL is not configured; real PostgreSQL test not run.")
    if not url.endswith("/finance_verify"):
        raise ValueError("Integration tests require the dedicated finance_verify database.")
    settings = Settings()
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await seed_rows(sessions)
    reader_url = (
        settings.source_database_url.get_secret_value().rsplit("/", 1)[0] + "/finance_verify"
    )
    reader = create_async_engine(reader_url)
    try:
        yield settings, sessions, async_sessionmaker(reader, expire_on_commit=False)
    finally:
        await reader.dispose()
        await engine.dispose()


async def test_real_pgvector_ingestion_search_and_rls(postgres):
    settings, sessions, reader = postgres
    embedder = FixedEmbedder()
    ingestion = Ingestion(sessions, embedder, "fixture-embedding")
    document_id = "verify-" + uuid4().hex
    arguments = dict(
        tenant_id="demo",
        entity="acme",
        document_id=document_id,
        source="synthetic.md",
        period="2026-Q2",
    )
    assert await ingestion.ingest(**arguments, pages=[(3, "SYNTHETIC logistics expenses")]) == 1
    assert await ingestion.ingest(**arguments, pages=[(3, "SYNTHETIC logistics expenses")]) == 0
    assert embedder.calls == 1
    await ingestion.ingest(**arguments, pages=[(4, "SYNTHETIC revised logistics expenses")])
    await ingestion.ingest(
        tenant_id="other",
        entity="beta",
        document_id=document_id,
        source="private.md",
        period="2026-Q2",
        pages=[(1, "OTHER ENTITY SECRET")],
    )
    sources = PostgresSources(reader, embedder, "fixture-embedding")
    question = Question(question="Compare profits", entity="acme", periods=("2026-Q1", "2026-Q2"))
    records, evidence = await sources.records(question, DEMO_SCOPE)
    assert len(records) == 2
    assert all(e.tenant_id == "demo" for e in evidence)
    retrieved = await sources.search(question, DEMO_SCOPE, "expenses", "fixture")
    assert retrieved and all(e.entity == "acme" for e in retrieved)
    async with reader.begin() as session:
        assert not (await session.scalars(select(DocumentChunk))).all()
        await session.execute(
            text(
                "SELECT set_config('app.tenant_id', 'demo', true), set_config('app.entity_id', 'acme', true)"
            )
        )
        rows = (await session.scalars(select(DocumentChunk))).all()
        assert rows and all(row.tenant_id == "demo" and row.entity == "acme" for row in rows)
        with pytest.raises(DBAPIError):
            await session.execute(text("DELETE FROM financial_records"))


async def test_durable_checkpoint_resume_after_planning(postgres):
    settings, sessions, _ = postgres
    checkpoint_url = os.environ["FIN_TEST_POSTGRES_URL"].replace(
        "postgresql+psycopg://", "postgresql://"
    )
    store = ExecutionStore(sessions, settings)
    question = Question(
        question="Compare profits and management notes",
        entity="acme",
        periods=("2026-Q1", "2026-Q2"),
    )
    execution_id = await store.create(question, DEMO_SCOPE)
    config = {"configurable": {"thread_id": f"demo:demo-user:{execution_id}"}}
    async with AsyncPostgresSaver.from_conn_string(checkpoint_url) as saver:
        service, _ = services(settings, store, checkpointer=saver)
        await service.graph.ainvoke(
            {
                "execution_id": execution_id,
                "question": question.model_dump(mode="json"),
                "scope": DEMO_SCOPE.model_dump(mode="json"),
            },
            config,
            interrupt_after=["planning"],
        )
        snapshot = await service.graph.aget_state(config)
        assert snapshot.next == ("execute_wave",)
    async with AsyncPostgresSaver.from_conn_string(checkpoint_url) as saver:
        recovered, model = services(settings, store, checkpointer=saver)
        result = await recovered.graph.ainvoke(None, config)
        assert result["answer"]["status"] == "complete"
        assert "-33.33%" in result["answer"]["text"]
        assert model.calls == 8
