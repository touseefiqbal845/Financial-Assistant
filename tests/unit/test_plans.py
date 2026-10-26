import pytest

from financial_assistant.contracts.models import Plan, Role, Task
from financial_assistant.workflows.policies.plans import InvalidPlan, validate_plan


def task(name, role, deps=()):
    return Task(id=name, role=role, instruction="Retrieve or analyze", depends_on=deps)


@pytest.mark.parametrize(
    "tasks",
    [
        (task("a", Role.DATA), task("a", Role.ANALYSIS, ("a",))),
        (task("a", Role.DATA), task("b", Role.ANALYSIS, ("missing",))),
        (task("a", Role.DATA, ("b",)), task("b", Role.ANALYSIS, ("a",))),
        (task("a", Role.DATA),),
        (task("a", Role.DATA), task("b", Role.DOCUMENTS), task("c", Role.ANALYSIS, ("a",))),
    ],
)
def test_invalid_plans(tasks):
    with pytest.raises(InvalidPlan):
        validate_plan(Plan(tasks=tasks), 6)


def test_valid_plan_and_budget():
    plan = Plan(tasks=(task("a", Role.DATA), task("b", Role.ANALYSIS, ("a",))))
    assert validate_plan(plan, 2) == plan
    with pytest.raises(InvalidPlan):
        validate_plan(plan, 1)
