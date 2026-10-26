import argparse
import json
from contextlib import AsyncExitStack
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from financial_assistant.bootstrap import build_services
from financial_assistant.config import Settings
from financial_assistant.connectors.models.preflight import run as preflight
from financial_assistant.contracts.models import Question, Scope
from financial_assistant.platform import run_async
from financial_assistant.worker import process


async def evaluate(budget: Decimal) -> dict:
    settings = Settings()
    if settings.environment != "development":
        raise ValueError("Live demo evaluation requires the synthetic development environment.")
    await preflight()
    settings = settings.model_copy(update={"max_cost_usd": min(budget / 2, Decimal("0.45"))})
    scope = Scope(user_id="live-evaluation", tenant_id="demo", entities=("acme",))
    results = []
    async with AsyncExitStack() as stack:
        services = await build_services(settings, stack, worker=True)
        for question in (
            Question(
                question="Why did profit decline? Compare the supplied quarters and cite management notes.",
                entity="acme",
                periods=("2026-Q1", "2026-Q2"),
            ),
            Question(question="Compare profits", entity="acme"),
        ):
            execution_id = await services.store.create(question, scope)
            owner = str(uuid4())
            row = await services.store.claim(owner)
            if row is None or row.id != execution_id:
                raise RuntimeError(
                    "Run live evaluation with the worker stopped and no queued jobs."
                )
            started = perf_counter()
            await process(services, row, owner)
            saved = await services.store.get(execution_id, scope)
            if saved is None:
                raise RuntimeError("Evaluation execution disappeared.")
            answer = saved.result
            passed = saved.status == "succeeded" and answer is not None
            if answer:
                passed = passed and (
                    answer["status"] == "clarification"
                    if not question.periods
                    else "-33.33%" in answer["text"] and bool(answer["evidence"])
                )
            results.append(
                {
                    "execution_id": execution_id,
                    "passed": passed,
                    "answer": answer,
                    "duration_seconds": perf_counter() - started,
                    "input_tokens": saved.input_tokens,
                    "output_tokens": saved.output_tokens,
                    "estimated_cost_usd": str(saved.actual_cost),
                    "error_code": saved.error_code,
                }
            )
            if not passed:
                break
    return {
        "mode": "live-openai",
        "models": {"main": settings.main_model, "planner": settings.planner_model},
        "pricing_version": settings.pricing_version,
        "budget_usd": str(budget),
        "results": results,
        "passed": len(results) == 2 and all(item["passed"] for item in results),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--budget-usd", type=Decimal, default=Decimal("1.00"))
    args = parser.parse_args()
    if not args.allow_paid or not Decimal("0") < args.budget_usd <= Decimal("1"):
        parser.error("Explicit --allow-paid and a budget between zero and US$1 are required.")
    report = run_async(evaluate(args.budget_usd))
    destination = Path("artifacts/live-evaluation.json")
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Live evaluation:", "passed" if report["passed"] else "failed")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
