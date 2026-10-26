from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from financial_assistant.contracts.models import Evidence, FinancialRecord, Question, Scope
from financial_assistant.persistence.tables import DocumentChunk, FinancialRow
from financial_assistant.ports.model import Embedder
from financial_assistant.security.authorization import require_entity


class PostgresSources:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], embedder: Embedder, embedding_model: str
    ):
        self.sessions, self.embedder, self.embedding_model = sessions, embedder, embedding_model

    async def set_scope(self, session: AsyncSession, scope: Scope, entity: str) -> None:
        require_entity(scope, entity)
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            await session.execute(
                text(
                    "SELECT set_config('app.tenant_id', :tenant, true), set_config('app.entity_id', :entity, true)"
                ),
                {"tenant": scope.tenant_id, "entity": entity},
            )

    async def records(
        self, question: Question, scope: Scope
    ) -> tuple[tuple[FinancialRecord, ...], tuple[Evidence, ...]]:
        async with self.sessions.begin() as session:
            await self.set_scope(session, scope, question.entity)
            rows = (
                await session.scalars(
                    select(FinancialRow)
                    .where(
                        FinancialRow.tenant_id == scope.tenant_id,
                        FinancialRow.entity == question.entity,
                        FinancialRow.period.in_(question.periods),
                    )
                    .order_by(FinancialRow.period)
                    .limit(4)
                )
            ).all()
        records = tuple(
            FinancialRecord.model_validate(
                {
                    "evidence_id": row.id,
                    "entity": row.entity,
                    "period": row.period,
                    "currency": row.currency,
                    "scale": row.scale,
                    "designation": row.designation,
                    "revenue": row.revenue,
                    "expenses": row.expenses,
                }
            )
            for row in rows
        )
        evidence = tuple(
            Evidence(
                id=row.id,
                tenant_id=scope.tenant_id,
                entity=row.entity,
                source="synthetic-ledger",
                period=row.period,
                version="seed-v1",
                content=record.model_dump_json(),
            )
            for row, record in zip(rows, records, strict=True)
        )
        return records, evidence

    async def search(
        self, question: Question, scope: Scope, query: str, execution_id: str
    ) -> tuple[Evidence, ...]:
        require_entity(scope, question.entity)
        vector = (await self.embedder.embed([query], execution_id))[0]
        async with self.sessions.begin() as session:
            await self.set_scope(session, scope, question.entity)
            statement = (
                select(DocumentChunk)
                .where(
                    DocumentChunk.tenant_id == scope.tenant_id,
                    DocumentChunk.entity == question.entity,
                    DocumentChunk.period.in_(question.periods),
                    DocumentChunk.embedding_model == self.embedding_model,
                )
                .order_by(DocumentChunk.embedding.cosine_distance(vector))
                .limit(4)
            )
            rows = (await session.scalars(statement)).all()
        return tuple(
            Evidence(
                id=row.id,
                tenant_id=row.tenant_id,
                entity=row.entity,
                source=row.source,
                period=row.period,
                content=row.content,
                page=row.page,
                version=row.version,
            )
            for row in rows
        )
