from financial_assistant.contracts.models import Plan, Question
from financial_assistant.ports.model import Model


class PlanningAgent:
    def __init__(self, model: Model, model_name: str, instructions: str):
        self.model, self.model_name, self.instructions = model, model_name, instructions

    async def plan(self, execution_id: str, question: Question, feedback: str = "") -> Plan:
        return await self.model.structured(
            execution_id=execution_id,
            model=self.model_name,
            instructions=self.instructions,
            payload={"question": question.model_dump(mode="json"), "validation_feedback": feedback},
            output=Plan,
        )
