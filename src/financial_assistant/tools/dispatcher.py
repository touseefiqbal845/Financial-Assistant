import asyncio

from financial_assistant.config import Settings
from financial_assistant.contracts.models import Decision, Question, Role, Scope, TaskResult
from financial_assistant.finance.calculations import IncompatibleValues, compare_periods
from financial_assistant.observability.telemetry import EVENTS, span
from financial_assistant.persistence.executions import ExecutionStore
from financial_assistant.ports.sources import Sources
from financial_assistant.security.authorization import AccessDenied, check_evidence, require_entity

ALLOWED = {
    Role.DATA: {"financial_records"},
    Role.DOCUMENTS: {"document_search"},
    Role.ANALYSIS: {"compare_periods"},
}


class ToolDispatcher:
    def __init__(self, sources: Sources, store: ExecutionStore, settings: Settings):
        self.sources, self.store, self.settings = sources, store, settings

    async def execute(
        self,
        *,
        execution_id: str,
        task_id: str,
        role: Role,
        decision: Decision,
        question: Question,
        scope: Scope,
        dependencies: tuple[TaskResult, ...],
    ) -> TaskResult:
        require_entity(scope, question.entity)
        if decision.tool not in ALLOWED[role]:
            await self.store.audit(execution_id, "tool.denied", "denied")
            EVENTS.labels("tool", "denied").inc()
            raise AccessDenied("Tool is not available to this agent.")
        try:
            with span("tool." + decision.tool):
                async with asyncio.timeout(self.settings.tool_timeout_seconds):
                    if decision.tool == "financial_records":
                        records, evidence = await self.sources.records(question, scope)
                        check_evidence(scope, evidence)
                        result = TaskResult(
                            task_id=task_id, status="succeeded", records=records, evidence=evidence
                        )
                    elif decision.tool == "document_search":
                        evidence = await self.sources.search(
                            question, scope, decision.arguments.query, execution_id
                        )
                        check_evidence(scope, evidence)
                        result = TaskResult(task_id=task_id, status="succeeded", evidence=evidence)
                    else:
                        records = tuple(r for item in dependencies for r in item.records)
                        calculation = compare_periods(records)
                        result = TaskResult(
                            task_id=task_id, status="succeeded", limitations=(str(calculation),)
                        )
            await self.store.audit(execution_id, "tool." + decision.tool, "succeeded")
            return result
        except (TimeoutError, ConnectionError, IncompatibleValues):
            await self.store.audit(execution_id, "tool." + decision.tool, "failed")
            EVENTS.labels("tool", "failed").inc()
            return TaskResult(
                task_id=task_id,
                status="failed",
                error_code="tool_unavailable",
                limitations=("A required tool could not complete its operation.",),
            )
