from financial_assistant.contracts.models import (
    Decision,
    Narrative,
    Question,
    Role,
    Scope,
    Task,
    TaskResult,
)
from financial_assistant.ports.model import Model
from financial_assistant.tools.dispatcher import ALLOWED, ToolDispatcher


class Specialist:
    def __init__(
        self, model: Model, model_name: str, instructions: str, dispatcher: ToolDispatcher
    ):
        self.model, self.model_name = model, model_name
        self.instructions, self.dispatcher = instructions, dispatcher

    async def run(
        self,
        *,
        execution_id: str,
        task: Task,
        question: Question,
        scope: Scope,
        dependencies: tuple[TaskResult, ...],
    ) -> TaskResult:
        observation: TaskResult | None = None
        for _ in range(2):
            decision = await self.model.structured(
                execution_id=execution_id,
                model=self.model_name,
                instructions=self.instructions,
                payload={
                    "task": task.model_dump(mode="json"),
                    "question": question.model_dump(mode="json"),
                    "allowed_tools": sorted(ALLOWED[task.role]),
                    "observation": observation.model_dump(mode="json") if observation else None,
                },
                output=Decision,
            )
            if decision.action == "finish":
                break
            if observation is not None:
                break
            observation = await self.dispatcher.execute(
                execution_id=execution_id,
                task_id=task.id,
                role=task.role,
                decision=decision,
                question=question,
                scope=scope,
                dependencies=dependencies,
            )
        if observation is None:
            return TaskResult(
                task_id=task.id,
                status="failed",
                error_code="no_tool_result",
                limitations=("Agent did not retrieve the required evidence.",),
            )
        if task.role == Role.ANALYSIS and observation.status == "succeeded":
            narrative = await self.model.structured(
                execution_id=execution_id,
                model=self.model_name,
                instructions=self.instructions
                + " Describe document-supported explanations only. Cite evidence identifiers. Distinguish management statements from proven causes.",
                payload={
                    "question": question.model_dump(mode="json"),
                    "dependencies": [item.model_dump(mode="json") for item in dependencies],
                    "calculation": observation.model_dump(mode="json"),
                },
                output=Narrative,
            )
            return observation.model_copy(
                update={"claims": narrative.claims, "limitations": narrative.limitations}
            )
        return observation
