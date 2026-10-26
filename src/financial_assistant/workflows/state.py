from typing import TypedDict


class GraphState(TypedDict, total=False):
    execution_id: str
    question: dict
    scope: dict
    clarification: str
    plan: dict
    results: dict[str, dict]
    answer: dict
