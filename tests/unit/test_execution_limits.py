from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from financial_assistant.contracts.models import Question
from financial_assistant.persistence.executions import QueueFull
from financial_assistant.persistence.tables import Execution
from financial_assistant.worker import process
from tests.support import DEMO_SCOPE, services


async def test_admission_is_bounded(store):
    question = Question(question="Compare profits", entity="acme")
    for _ in range(20):
        await store.create(question, DEMO_SCOPE)
    with pytest.raises(QueueFull):
        await store.create(question, DEMO_SCOPE)


async def test_expired_execution_does_not_call_model(settings, store):
    service, model = services(settings, store)
    execution_id = await store.create(
        Question(question="Compare profits", entity="acme"), DEMO_SCOPE
    )
    async with store.sessions.begin() as session:
        row = await session.get(Execution, execution_id)
        row.deadline = datetime.now(UTC) - timedelta(seconds=1)
    owner = str(uuid4())
    await process(service, await store.claim(owner), owner)
    row = await store.get(execution_id, DEMO_SCOPE)
    assert row.status == "cancelled" and model.calls == 0
