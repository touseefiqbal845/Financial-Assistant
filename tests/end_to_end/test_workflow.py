import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from financial_assistant.api.app import create_app
from financial_assistant.contracts.models import Question, Scope
from financial_assistant.worker import process
from tests.support import DEMO_SCOPE, FixtureSources, services


@pytest.mark.parametrize(
    "failed,missing,status",
    [(False, False, "complete"), (True, False, "partial"), (False, True, "insufficient_evidence")],
)
async def test_full_graph_and_failure_modes(settings, store, failed, missing, status):
    service, model = services(
        settings, store, FixtureSources(fail_documents=failed, missing_period=missing)
    )
    question = Question(
        question="Why did profit decline and what do management notes say?",
        entity="acme",
        periods=("2026-Q1", "2026-Q2"),
    )
    execution_id = await store.create(question, DEMO_SCOPE)
    owner = str(uuid4())
    row = await store.claim(owner)
    await process(service, row, owner)
    saved = await store.get(execution_id, DEMO_SCOPE)
    assert saved.status == "succeeded", saved.error_code
    assert saved.result["status"] == status
    if not missing:
        assert "-33.33%" in saved.result["text"]
    assert model.maximum_active == 2


async def test_api_auth_scope_and_cancellation(settings, store):
    service, _ = services(settings, store)
    app = create_app(settings, service)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        headers = {"Authorization": "Bearer " + settings.dev_token.get_secret_value()}
        body = {"question": "Compare profits", "entity": "acme", "periods": ["2026-Q1", "2026-Q2"]}
        assert (await client.post("/questions", json=body)).status_code == 401
        assert (
            await client.post("/questions", json={**body, "entity": "beta"}, headers=headers)
        ).status_code == 403
        response = await client.post("/questions", json=body, headers=headers)
        assert response.status_code == 202
        execution_id = response.json()["execution_id"]
        assert (await client.get(f"/executions/{execution_id}", headers=headers)).status_code == 200
        assert (
            await client.post(f"/executions/{execution_id}/cancel", headers=headers, json={})
        ).status_code == 202
        assert (await client.get(f"/executions/{execution_id}", headers=headers)).json()[
            "status"
        ] == "cancelled"
        assert (await client.get("/metrics")).status_code == 401
        assert (
            await client.post("/questions", content="x" * 9000, headers=headers)
        ).status_code == 413


async def test_execution_ownership_is_not_guessable_access(settings, store):
    execution_id = await store.create(
        Question(question="Compare profits", entity="acme"), DEMO_SCOPE
    )
    stranger = Scope(user_id="stranger", tenant_id="demo", entities=("acme",))
    assert await store.get(execution_id, stranger) is None
    assert not await store.cancel(execution_id, stranger)


async def test_missing_periods_clarify_without_model_spend(settings, store):
    service, model = services(settings, store)
    execution_id = await store.create(
        Question(question="Compare profits", entity="acme"), DEMO_SCOPE
    )
    owner = str(uuid4())
    await process(service, await store.claim(owner), owner)
    row = await store.get(execution_id, DEMO_SCOPE)
    assert row.result["status"] == "clarification"
    assert model.calls == 0


async def test_running_cancellation(settings, store):
    service, _ = services(settings, store)
    execution_id = await store.create(
        Question(question="Compare profits", entity="acme", periods=("2026-Q1", "2026-Q2")),
        DEMO_SCOPE,
    )
    owner = str(uuid4())
    row = await store.claim(owner)

    class SlowGraph:
        async def aget_state(self, config):
            class Snapshot:
                next = ()
                values = {}

            return Snapshot()

        async def ainvoke(self, initial, config):
            await asyncio.sleep(10)

    service.graph = SlowGraph()
    job = asyncio.create_task(process(service, row, owner))
    await asyncio.sleep(0.05)
    await store.cancel(execution_id, DEMO_SCOPE)
    await asyncio.wait_for(job, 2)
    assert (await store.get(execution_id, DEMO_SCOPE)).status == "cancelled"
