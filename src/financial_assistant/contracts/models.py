from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Scope(Contract):
    user_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    entities: tuple[str, ...] = Field(min_length=1, max_length=20)


class Question(Contract):
    question: str = Field(min_length=5, max_length=4000)
    entity: str = Field(pattern=r"^[a-z][a-z0-9-]{0,49}$")
    periods: tuple[str, ...] = Field(default=(), max_length=4)

    @field_validator("periods")
    @classmethod
    def valid_periods(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        import re

        if len(value) != len(set(value)) or any(
            not re.fullmatch(r"20\d{2}-Q[1-4]", p) for p in value
        ):
            raise ValueError("Use unique periods such as 2026-Q1.")
        return tuple(sorted(value))


class Role(StrEnum):
    DATA = "financial_data"
    DOCUMENTS = "documents"
    ANALYSIS = "analysis"


class Task(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    role: Role
    instruction: str = Field(min_length=1, max_length=1200)
    depends_on: tuple[str, ...] = Field(max_length=6)


class Plan(Contract):
    tasks: tuple[Task, ...] = Field(min_length=1, max_length=12)


class Evidence(Contract):
    id: str
    tenant_id: str
    entity: str
    source: str
    period: str
    content: str = Field(max_length=5000)
    page: int | None = None
    version: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FinancialRecord(Contract):
    evidence_id: str
    entity: str
    period: str
    currency: Literal["PKR", "USD"]
    scale: Literal["units", "thousands", "millions"]
    designation: Literal["actual", "forecast", "estimate"]
    revenue: Decimal
    expenses: Decimal


class Claim(Contract):
    text: str = Field(min_length=1, max_length=1000)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=8)


class Narrative(Contract):
    claims: tuple[Claim, ...] = Field(max_length=8)
    limitations: tuple[str, ...] = Field(max_length=6)


class TaskResult(Contract):
    task_id: str
    status: Literal["succeeded", "failed", "skipped"]
    evidence: tuple[Evidence, ...] = ()
    records: tuple[FinancialRecord, ...] = ()
    claims: tuple[Claim, ...] = ()
    limitations: tuple[str, ...] = ()
    error_code: str | None = None


class Answer(Contract):
    status: Literal["complete", "partial", "insufficient_evidence", "clarification"]
    text: str
    claims: tuple[Claim, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    limitations: tuple[str, ...] = ()


class ToolArgs(Contract):
    query: str = Field(min_length=1, max_length=1200)


class Decision(Contract):
    action: Literal["tool", "finish"]
    tool: Literal["financial_records", "document_search", "compare_periods", "none"]
    arguments: ToolArgs
