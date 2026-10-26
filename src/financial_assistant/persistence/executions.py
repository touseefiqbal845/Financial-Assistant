from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from financial_assistant.config import Settings
from financial_assistant.contracts.models import Question, Scope
from financial_assistant.persistence.tables import AuditEvent, Execution


class BudgetExceeded(RuntimeError):
    pass


class ExecutionStopped(RuntimeError):
    pass


class QueueFull(RuntimeError):
    pass


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class ExecutionStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings):
        self.sessions = sessions
        self.settings = settings

    async def create(self, question: Question, scope: Scope) -> str:
        now = datetime.now(UTC)
        execution_id = str(uuid4())
        async with self.sessions.begin() as session:
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
                    {"scope": f"admission:{scope.tenant_id}:{scope.user_id}"},
                )
            pending = await session.scalar(
                select(func.count())
                .select_from(Execution)
                .where(
                    Execution.tenant_id == scope.tenant_id,
                    Execution.user_id == scope.user_id,
                    Execution.status.in_(("pending", "running")),
                )
            )
            if pending is not None and pending >= 20:
                raise QueueFull("Too many outstanding executions.")
            session.add(
                Execution(
                    id=execution_id,
                    tenant_id=scope.tenant_id,
                    user_id=scope.user_id,
                    entity=question.entity,
                    scope=scope.model_dump(mode="json"),
                    request=question.model_dump(mode="json"),
                    created_at=now,
                    deadline=now + timedelta(seconds=self.settings.execution_timeout_seconds),
                )
            )
        return execution_id

    async def get(self, execution_id: str, scope: Scope) -> Execution | None:
        async with self.sessions() as session:
            return await session.scalar(
                select(Execution).where(
                    Execution.id == execution_id,
                    Execution.tenant_id == scope.tenant_id,
                    Execution.user_id == scope.user_id,
                    Execution.entity.in_(scope.entities),
                )
            )

    async def cancel(self, execution_id: str, scope: Scope) -> bool:
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(Execution)
                .where(
                    Execution.id == execution_id,
                    Execution.tenant_id == scope.tenant_id,
                    Execution.user_id == scope.user_id,
                    Execution.entity.in_(scope.entities),
                )
                .with_for_update()
            )
            if row is None:
                return False
            row.cancel_requested = True
            if row.status == "pending":
                row.status = "cancelled"
            return True

    async def claim(self, owner: str) -> Execution | None:
        now = datetime.now(UTC)
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(Execution)
                .where(
                    or_(
                        Execution.status == "pending",
                        and_(Execution.status == "running", Execution.lease_until < now),
                    )
                )
                .order_by(Execution.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                return None
            row.status = "running"
            row.lease_owner = owner
            row.lease_until = now + timedelta(seconds=30)
            return row

    async def heartbeat(self, execution_id: str, owner: str) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(Execution, execution_id, with_for_update=True)
            if row is None or row.lease_owner != owner or row.status != "running":
                raise ExecutionStopped("Execution lease was lost.")
            if row.cancel_requested or utc(row.deadline) <= datetime.now(UTC):
                raise ExecutionStopped("Execution cancelled or expired.")
            row.lease_until = datetime.now(UTC) + timedelta(seconds=30)

    async def reserve(self, execution_id: str, tokens: int, cost: Decimal) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(Execution, execution_id, with_for_update=True)
            if row is None or row.cancel_requested or utc(row.deadline) <= datetime.now(UTC):
                raise ExecutionStopped("Execution cancelled or expired.")
            if (
                row.calls + 1 > self.settings.max_model_calls
                or row.reserved_tokens + tokens > self.settings.max_tokens
                or row.reserved_cost + cost > self.settings.max_cost_usd
            ):
                raise BudgetExceeded("Execution budget exhausted.")
            row.calls += 1
            row.reserved_tokens += tokens
            row.reserved_cost += cost

    async def usage(
        self, execution_id: str, input_tokens: int, output_tokens: int, cost: Decimal
    ) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(Execution, execution_id, with_for_update=True)
            if row is None:
                raise ExecutionStopped("Execution not found.")
            row.input_tokens += input_tokens
            row.output_tokens += output_tokens
            row.actual_cost += cost

    async def finish(
        self,
        execution_id: str,
        owner: str,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(Execution, execution_id, with_for_update=True)
            if row is None or row.lease_owner != owner:
                raise ExecutionStopped("Execution lease was lost.")
            row.status = "cancelled" if row.cancel_requested else status
            row.result = None if row.cancel_requested else result
            row.error_code = error
            row.lease_until = None

    async def audit(self, execution_id: str, action: str, outcome: str) -> None:
        async with self.sessions.begin() as session:
            session.add(
                AuditEvent(
                    id=str(uuid4()),
                    execution_id=execution_id,
                    action=action,
                    outcome=outcome,
                    created_at=datetime.now(UTC),
                )
            )
