import asyncio
from decimal import Decimal
from typing import TypeVar

from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from financial_assistant.agents.main_agent import Intake, MainAgent
from financial_assistant.agents.planning_agent import PlanningAgent
from financial_assistant.agents.specialist import Specialist
from financial_assistant.bootstrap import Services, prompt
from financial_assistant.config import Settings
from financial_assistant.contracts.models import (
    Claim,
    Decision,
    Evidence,
    FinancialRecord,
    Narrative,
    Plan,
    Question,
    Role,
    Scope,
    Task,
    ToolArgs,
)
from financial_assistant.ingestion.seed import DEMO_NOTES, DEMO_ROWS
from financial_assistant.persistence.executions import ExecutionStore
from financial_assistant.security.authentication import Authenticator
from financial_assistant.security.authorization import require_entity
from financial_assistant.tools.dispatcher import ToolDispatcher
from financial_assistant.workflows.graph import build_graph

T = TypeVar("T", bound=BaseModel)
DEMO_SCOPE = Scope(user_id="demo-user", tenant_id="demo", entities=("acme",))


class DeterministicModel:
    def __init__(self):
        self.calls = 0
        self.active = 0
        self.maximum_active = 0

    async def structured(
        self, *, execution_id: str, model: str, instructions: str, payload: dict, output: type[T]
    ) -> T:
        self.calls += 1
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        try:
            await asyncio.sleep(0.001)
            if output is Intake:
                result = Intake(action="proceed", clarification="")
            elif output is Plan:
                result = Plan(
                    tasks=(
                        Task(
                            id="data", role=Role.DATA, instruction="Retrieve records", depends_on=()
                        ),
                        Task(
                            id="docs",
                            role=Role.DOCUMENTS,
                            instruction="Retrieve notes",
                            depends_on=(),
                        ),
                        Task(
                            id="analysis",
                            role=Role.ANALYSIS,
                            instruction="Compare periods",
                            depends_on=("data", "docs"),
                        ),
                    )
                )
            elif output is Decision:
                finished = payload.get("observation") is not None
                result = Decision(
                    action="finish" if finished else "tool",
                    tool="none" if finished else payload["allowed_tools"][0],
                    arguments=ToolArgs(query="management operating expenses explanation"),
                )
            elif output is Narrative:
                if "approved_claims" in payload:
                    result = Narrative(
                        claims=tuple(Claim.model_validate(c) for c in payload["approved_claims"]),
                        limitations=(),
                    )
                else:
                    evidence = [
                        e
                        for dependency in payload["dependencies"]
                        for e in dependency["evidence"]
                        if e["page"]
                    ]
                    result = Narrative(
                        claims=tuple(
                            Claim(
                                text="Management notes attribute increased expenses to logistics disruption and a marketing campaign; this is management's explanation.",
                                evidence_ids=(e["id"],),
                            )
                            for e in evidence
                        ),
                        limitations=(),
                    )
            else:
                raise AssertionError(f"Unexpected schema {output}")
            return output.model_validate(result.model_dump())
        finally:
            self.active -= 1


class FixtureSources:
    def __init__(self, *, fail_documents: bool = False, missing_period: bool = False):
        self.fail_documents, self.missing_period = fail_documents, missing_period

    async def records(self, question: Question, scope: Scope):
        require_entity(scope, question.entity)
        records, evidence = [], []
        for tenant, entity, period, revenue, expenses in DEMO_ROWS:
            if (
                tenant != scope.tenant_id
                or entity != question.entity
                or period not in question.periods
            ):
                continue
            if self.missing_period and period.endswith("Q2"):
                continue
            record = FinancialRecord(
                evidence_id=f"{tenant}-{entity}-{period}",
                entity=entity,
                period=period,
                currency="PKR",
                scale="units",
                designation="actual",
                revenue=Decimal(revenue),
                expenses=Decimal(expenses),
            )
            records.append(record)
            evidence.append(
                Evidence(
                    id=record.evidence_id,
                    tenant_id=tenant,
                    entity=entity,
                    source="synthetic-ledger",
                    period=period,
                    version="v1",
                    content=record.model_dump_json(),
                )
            )
        return tuple(records), tuple(evidence)

    async def search(self, question: Question, scope: Scope, query: str, execution_id: str):
        require_entity(scope, question.entity)
        if self.fail_documents:
            raise ConnectionError("Injected document failure")
        content = DEMO_NOTES[(scope.tenant_id, question.entity)]
        return (
            Evidence(
                id="demo-management",
                tenant_id=scope.tenant_id,
                entity=question.entity,
                source="synthetic-management.md",
                period="2026-Q2",
                page=1,
                version="v1",
                content=content,
            ),
        )


def services(settings: Settings, store: ExecutionStore, sources=None, checkpointer=None):
    model = DeterministicModel()
    dispatcher = ToolDispatcher(sources or FixtureSources(), store, settings)
    workers = {
        role: Specialist(model, settings.data_model, prompt("specialist"), dispatcher)
        for role in Role
    }
    graph = build_graph(
        MainAgent(model, settings.main_model, prompt("main")),
        PlanningAgent(model, settings.planner_model, prompt("planner")),
        workers,
        settings,
        checkpointer or InMemorySaver(),
    )
    return Services(store, Authenticator(settings), graph), model
