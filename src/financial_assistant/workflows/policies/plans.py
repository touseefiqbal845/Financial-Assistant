from financial_assistant.contracts.models import Plan, Role


class InvalidPlan(ValueError):
    pass


def validate_plan(plan: Plan, max_tasks: int) -> Plan:
    tasks = {task.id: task for task in plan.tasks}
    if len(tasks) != len(plan.tasks) or len(tasks) > max_tasks:
        raise InvalidPlan("Duplicate task identifiers or excessive task count.")
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id not in tasks or task_id in visiting:
            raise InvalidPlan("Missing dependency or dependency cycle.")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in tasks[task_id].depends_on:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task in plan.tasks:
        visit(task.id)
        if task.role != Role.ANALYSIS and task.depends_on:
            raise InvalidPlan("Retrieval tasks must be independent in this workflow.")
        if task.role == Role.ANALYSIS:
            if not any(tasks[d].role == Role.DATA for d in task.depends_on):
                raise InvalidPlan("Financial analysis requires structured financial data.")
    if sum(t.role == Role.ANALYSIS for t in plan.tasks) != 1:
        raise InvalidPlan("Exactly one financial-analysis task is required.")
    if sum(t.role == Role.DATA for t in plan.tasks) != 1:
        raise InvalidPlan("Exactly one financial-data task is required.")
    analysis = next(t for t in plan.tasks if t.role == Role.ANALYSIS)
    if set(analysis.depends_on) != {t.id for t in plan.tasks if t.role != Role.ANALYSIS}:
        raise InvalidPlan("Analysis must wait for every retrieval task.")
    return plan
