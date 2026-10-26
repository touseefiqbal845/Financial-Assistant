from decimal import Decimal

from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from financial_assistant.config import Settings
from financial_assistant.connectors.models.openai_adapter import OpenAIAdapter
from financial_assistant.ingestion.pipeline import Ingestion
from financial_assistant.persistence.executions import ExecutionStore
from financial_assistant.persistence.tables import FinancialRow
from financial_assistant.platform import run_async

DEMO_ROWS = (
    ("demo", "acme", "2026-Q1", "1000000", "700000"),
    ("demo", "acme", "2026-Q2", "1100000", "900000"),
    ("other", "beta", "2026-Q1", "500000", "300000"),
    ("other", "beta", "2026-Q2", "600000", "350000"),
)
DEMO_NOTES = {
    (
        "demo",
        "acme",
    ): "SYNTHETIC DEMO MANAGEMENT NOTES. Management attributes increased expenses to a temporary logistics disruption and a marketing campaign. These notes express management's explanation and do not independently prove causality.",
    (
        "other",
        "beta",
    ): "SYNTHETIC DEMO MANAGEMENT NOTES. Management reports improved contract renewals and controlled hiring costs.",
}


async def seed_rows(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions.begin() as session:
        for tenant, entity, period, revenue, expenses in DEMO_ROWS:
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                await session.execute(
                    text(
                        "SELECT set_config('app.tenant_id', :tenant, true), set_config('app.entity_id', :entity, true)"
                    ),
                    {"tenant": tenant, "entity": entity},
                )
            await session.merge(
                FinancialRow(
                    id=f"{tenant}-{entity}-{period}",
                    tenant_id=tenant,
                    entity=entity,
                    period=period,
                    currency="PKR",
                    scale="units",
                    designation="actual",
                    revenue=Decimal(revenue),
                    expenses=Decimal(expenses),
                )
            )


async def run() -> None:
    settings = Settings()
    if settings.environment == "production":
        raise ValueError("Synthetic seeding is forbidden in production.")
    if not settings.ingest_database_url or not settings.openai_api_key:
        raise ValueError("Ingestion credentials and OpenAI key are required.")
    engine = create_async_engine(settings.ingest_database_url.get_secret_value())
    app_engine = create_async_engine(settings.database_url.get_secret_value())
    client = AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(), max_retries=0, timeout=25
    )
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        await seed_rows(sessions)
        adapter = OpenAIAdapter(
            client, ExecutionStore(async_sessionmaker(app_engine), settings), settings
        )
        ingestion = Ingestion(sessions, adapter, settings.embedding_model)
        for (tenant, entity), content in DEMO_NOTES.items():
            await ingestion.ingest(
                tenant_id=tenant,
                entity=entity,
                document_id=f"{entity}-management",
                source=f"synthetic-{entity}-management.md",
                period="2026-Q2",
                pages=[(1, content)],
            )
        print("Seeded synthetic records and management documents for two isolated tenants.")
    finally:
        await client.close()
        await engine.dispose()
        await app_engine.dispose()


def main() -> None:
    run_async(run())
