from typing import Protocol

from financial_assistant.contracts.models import Evidence, FinancialRecord, Question, Scope


class Sources(Protocol):
    async def records(
        self, question: Question, scope: Scope
    ) -> tuple[tuple[FinancialRecord, ...], tuple[Evidence, ...]]: ...

    async def search(
        self, question: Question, scope: Scope, query: str, execution_id: str
    ) -> tuple[Evidence, ...]: ...
