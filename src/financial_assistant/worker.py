import asyncio
import logging
import signal
from contextlib import AsyncExitStack
from uuid import uuid4

from financial_assistant.bootstrap import Services, build_services
from financial_assistant.config import Settings
from financial_assistant.observability.telemetry import (
    EVENTS,
    configure_logging,
    configure_tracing,
    span,
    worker_metrics,
)
from financial_assistant.persistence.executions import ExecutionStopped, utc
from financial_assistant.persistence.tables import Execution
from financial_assistant.platform import run_async


async def process(services: Services, row: Execution, owner: str) -> None:
    from datetime import UTC, datetime

    config = {
        "configurable": {"thread_id": f"{row.tenant_id}:{row.user_id}:{row.id}"},
        "recursion_limit": 24,
    }
    task: asyncio.Task | None = None
    try:
        await services.store.heartbeat(row.id, owner)
        snapshot = await services.graph.aget_state(config)
        initial = (
            None
            if snapshot.next
            else {"execution_id": row.id, "question": row.request, "scope": row.scope}
        )
        if snapshot.values.get("answer") and not snapshot.next:
            await services.store.finish(row.id, owner, "succeeded", snapshot.values["answer"])
            return
        remaining = (utc(row.deadline) - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise ExecutionStopped("Execution expired.")
        with span("execution"):
            async with asyncio.timeout(remaining):
                task = asyncio.create_task(services.graph.ainvoke(initial, config))
                while not task.done():
                    await asyncio.wait({task}, timeout=0.25)
                    await services.store.heartbeat(row.id, owner)
                result = await task
        await services.store.finish(row.id, owner, "succeeded", result["answer"])
        EVENTS.labels("execution", "succeeded").inc()
    except asyncio.CancelledError:
        raise
    except ExecutionStopped:
        await services.store.finish(row.id, owner, "cancelled", error="cancelled_or_expired")
        EVENTS.labels("execution", "cancelled").inc()
    except Exception as exc:
        error = "timeout" if isinstance(exc, TimeoutError) else "execution_failed"
        await services.store.finish(row.id, owner, "failed", error=error)
        logging.getLogger("financial_assistant").error(
            "execution_failed type=%s", type(exc).__name__
        )
        EVENTS.labels("execution", "failed").inc()
    finally:
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def run() -> None:
    configure_logging()
    configure_tracing()
    settings = Settings()
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stopped.set)
        except NotImplementedError:
            pass
    async with AsyncExitStack() as stack:
        if settings.metrics_token:
            server, _ = worker_metrics(settings.metrics_token.get_secret_value())
            stack.callback(server.shutdown)
            stack.callback(server.server_close)
        services = await build_services(settings, stack, worker=True)
        owner = str(uuid4())
        while not stopped.is_set():
            row = await services.store.claim(owner)
            if row:
                await process(services, row, owner)
            else:
                try:
                    await asyncio.wait_for(stopped.wait(), timeout=1)
                except TimeoutError:
                    pass


def main() -> None:
    run_async(run())


if __name__ == "__main__":
    main()
