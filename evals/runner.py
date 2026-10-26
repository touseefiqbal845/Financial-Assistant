import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from evals.scorers.task_success import score
from financial_assistant.config import Settings
from financial_assistant.contracts.models import Question
from financial_assistant.persistence.executions import ExecutionStore
from financial_assistant.persistence.tables import Base
from financial_assistant.worker import process
from tests.support import DEMO_SCOPE, FixtureSources, services


async def run() -> dict:
    cases_path = Path("evals/datasets/financial_questions.jsonl")
    dataset = await asyncio.to_thread(cases_path.read_bytes)
    cases = [json.loads(line) for line in dataset.decode().splitlines()]
    results = []
    with TemporaryDirectory() as temporary:
        url = f"sqlite+aiosqlite:///{Path(temporary).as_posix()}/eval.db"
        settings = Settings(
            environment="test",
            database_url=url,
            source_database_url=url,
            checkpoint_url="unused",
            dev_auth_enabled=True,
            dev_token="evaluation-" + "x" * 32,
        )
        engine = create_async_engine(url)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            store = ExecutionStore(async_sessionmaker(engine, expire_on_commit=False), settings)
            for case in cases:
                service, model = services(
                    settings,
                    store,
                    FixtureSources(
                        fail_documents=case.get("fail_documents", False),
                        missing_period=case.get("missing_period", False),
                    ),
                )
                question = Question(
                    question=case["question"], entity=case["entity"], periods=case["periods"]
                )
                execution_id = await store.create(question, DEMO_SCOPE)
                owner = str(uuid4())
                start = perf_counter()
                await process(service, await store.claim(owner), owner)
                row = await store.get(execution_id, DEMO_SCOPE)
                scores = score(row.result, case) if row.result else {"execution": False}
                results.append(
                    {
                        "id": case["id"],
                        "passed": all(scores.values()),
                        "scores": scores,
                        "duration_seconds": round(perf_counter() - start, 4),
                        "fixture_model_calls": model.calls,
                        "answer": row.result,
                    }
                )
        finally:
            await engine.dispose()
    revision = await asyncio.to_thread(
        subprocess.run, ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    )
    import hashlib

    prompts = Path("src/financial_assistant/prompts")
    prompt_data = await asyncio.to_thread(
        lambda: b"".join(p.read_bytes() for p in sorted(prompts.glob("*.md")))
    )
    report = {
        "mode": "deterministic-fixtures",
        "live_model_verified": False,
        "dataset_sha256": hashlib.sha256(dataset).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt_data).hexdigest(),
        "revision": revision.stdout.strip() or "uncommitted",
        "models": {"main": settings.main_model, "planner": settings.planner_model},
        "actual_api_cost_usd": "0",
        "results": results,
        "pass_rate": sum(r["passed"] for r in results) / len(results),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/evaluation.json")
    arguments = parser.parse_args()
    report = asyncio.run(run())
    destination = Path(arguments.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"Deterministic fixture evaluation: {report['pass_rate']:.0%}. Live LLM quality remains unverified."
    )
    if report["pass_rate"] < 1:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
