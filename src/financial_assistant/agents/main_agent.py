from typing import Literal

from financial_assistant.contracts.models import Claim, Contract, Narrative, Question
from financial_assistant.ports.model import Model


class Intake(Contract):
    action: Literal["proceed", "clarify"]
    clarification: str


class MainAgent:
    def __init__(self, model: Model, model_name: str, instructions: str):
        self.model, self.model_name, self.instructions = model, model_name, instructions

    async def intake(self, execution_id: str, question: Question) -> Intake:
        if len(question.periods) != 2:
            return Intake(
                action="clarify",
                clarification="Provide exactly two reporting periods, such as 2026-Q1 and 2026-Q2.",
            )
        return await self.model.structured(
            execution_id=execution_id,
            model=self.model_name,
            instructions=self.instructions
            + " Decide whether this read-only two-period financial comparison is sufficiently specified. Do not answer it yet.",
            payload={"question": question.model_dump(mode="json")},
            output=Intake,
        )

    async def compose(
        self, execution_id: str, claims: tuple[Claim, ...], limitations: tuple[str, ...]
    ) -> Narrative:
        return await self.model.structured(
            execution_id=execution_id,
            model=self.model_name,
            instructions=self.instructions,
            payload={
                "approved_claims": [c.model_dump() for c in claims],
                "limitations": limitations,
            },
            output=Narrative,
        )
