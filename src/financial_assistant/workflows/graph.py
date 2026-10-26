import asyncio

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from financial_assistant.agents.main_agent import MainAgent
from financial_assistant.agents.planning_agent import PlanningAgent
from financial_assistant.agents.specialist import Specialist
from financial_assistant.config import Settings
from financial_assistant.contracts.models import (
    Answer,
    Plan,
    Question,
    Role,
    Scope,
    Task,
    TaskResult,
)
from financial_assistant.finance.calculations import IncompatibleValues
from financial_assistant.observability.telemetry import EVENTS, span
from financial_assistant.persistence.executions import BudgetExceeded, ExecutionStopped
from financial_assistant.security.authorization import AccessDenied, check_evidence
from financial_assistant.validation.answers import (
    UnsupportedClaim,
    financial_claim,
    validate_claims,
)
from financial_assistant.workflows.policies.plans import InvalidPlan, validate_plan
from financial_assistant.workflows.state import GraphState


def build_graph(
    main: MainAgent,
    planner: PlanningAgent,
    workers: dict[Role, Specialist],
    settings: Settings,
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    async def intake(state: GraphState) -> dict:
        result = await main.intake(
            state["execution_id"], Question.model_validate(state["question"])
        )
        return {"clarification": result.clarification if result.action == "clarify" else ""}

    async def planning(state: GraphState) -> dict:
        feedback = ""
        for _ in range(2):
            plan = await planner.plan(
                state["execution_id"], Question.model_validate(state["question"]), feedback
            )
            try:
                validate_plan(plan, settings.max_tasks)
                return {"plan": plan.model_dump(mode="json"), "results": {}}
            except InvalidPlan as exc:
                feedback = str(exc)
                EVENTS.labels("replan", "invalid").inc()
        raise InvalidPlan("Planner did not produce a valid plan within two attempts.")

    async def execute_wave(state: GraphState) -> dict:
        plan = Plan.model_validate(state["plan"])
        results = {key: TaskResult.model_validate(value) for key, value in state["results"].items()}
        eligible = [
            task
            for task in plan.tasks
            if task.id not in results
            and all(dependency in results for dependency in task.depends_on)
        ]
        if not eligible:
            raise InvalidPlan("No executable task remains.")
        semaphore = asyncio.Semaphore(settings.max_concurrency)

        async def execute(task: Task) -> TaskResult:
            async with semaphore:
                dependencies = tuple(results[key] for key in task.depends_on)
                if task.role == Role.ANALYSIS and any(
                    result.status != "succeeded"
                    for result in dependencies
                    if result.task_id in {t.id for t in plan.tasks if t.role == Role.DATA}
                ):
                    return TaskResult(
                        task_id=task.id, status="skipped", error_code="missing_financial_data"
                    )
                try:
                    with span("agent." + task.role.value):
                        return await workers[task.role].run(
                            execution_id=state["execution_id"],
                            task=task,
                            question=Question.model_validate(state["question"]),
                            scope=Scope.model_validate(state["scope"]),
                            dependencies=dependencies,
                        )
                except (AccessDenied, BudgetExceeded, ExecutionStopped):
                    raise
                except Exception:
                    EVENTS.labels("task", "failed").inc()
                    return TaskResult(
                        task_id=task.id,
                        status="failed",
                        error_code="specialist_failed",
                        limitations=("A specialist could not complete its task.",),
                    )

        # Updates are merged once per wave, avoiding concurrent writes to graph state.
        async with asyncio.TaskGroup() as group:
            pending = [group.create_task(execute(task)) for task in eligible]
        for item in pending:
            result = item.result()
            results[result.task_id] = result
        return {"results": {key: value.model_dump(mode="json") for key, value in results.items()}}

    async def finalize(state: GraphState) -> dict:
        if state.get("clarification"):
            return {
                "answer": Answer(status="clarification", text=state["clarification"]).model_dump(
                    mode="json"
                )
            }
        results = tuple(TaskResult.model_validate(value) for value in state["results"].values())
        evidence = tuple(item for result in results for item in result.evidence)
        check_evidence(Scope.model_validate(state["scope"]), evidence)
        records = tuple(record for result in results for record in result.records)
        limitations = tuple(message for result in results for message in result.limitations)
        if len(records) != 2:
            return {
                "answer": Answer(
                    status="insufficient_evidence",
                    text="Two compatible financial periods are required; evidence is incomplete.",
                    evidence=evidence,
                    limitations=limitations,
                ).model_dump(mode="json")
            }
        try:
            authoritative = financial_claim(records)
        except IncompatibleValues:
            return {
                "answer": Answer(
                    status="insufficient_evidence",
                    text="Financial values have incompatible units, currencies, or reporting designations.",
                    evidence=evidence,
                ).model_dump(mode="json")
            }
        explanations = tuple(claim for result in results for claim in result.claims)
        try:
            validate_claims(explanations, evidence, records)
        except UnsupportedClaim:
            explanations = ()
            limitations += ("Unsupported model claims were removed.",)
        if explanations:
            narrative = await main.compose(state["execution_id"], explanations, limitations)
            # The composer may select and reorder approved statements, not introduce new claims.
            approved = {(c.text, c.evidence_ids) for c in explanations}
            explanations = tuple(
                c for c in narrative.claims if (c.text, c.evidence_ids) in approved
            )
        if not explanations:
            limitations += (
                "No validated document explanation is available; figures alone do not prove causality.",
            )
        partial = any(result.status != "succeeded" for result in results) or not explanations
        claims = (authoritative, *explanations)
        text = "\n".join(c.text + " [" + ", ".join(c.evidence_ids) + "]" for c in claims)
        answer = Answer(
            status="partial" if partial else "complete",
            text=text,
            claims=claims,
            evidence=evidence,
            limitations=limitations,
        )
        return {"answer": answer.model_dump(mode="json")}

    graph = StateGraph(GraphState)
    graph.add_node("intake", intake)
    graph.add_node("planning", planning)
    graph.add_node("execute_wave", execute_wave)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges(
        "intake", lambda s: "finalize" if s.get("clarification") else "planning"
    )
    graph.add_edge("planning", "execute_wave")
    graph.add_conditional_edges(
        "execute_wave",
        lambda s: "finalize" if len(s["results"]) == len(s["plan"]["tasks"]) else "execute_wave",
    )
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
