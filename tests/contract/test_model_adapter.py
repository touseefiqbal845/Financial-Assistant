from types import SimpleNamespace

import httpx
import pytest
from openai import RateLimitError

from financial_assistant.agents.main_agent import Intake
from financial_assistant.connectors.models.openai_adapter import ModelOutputError, OpenAIAdapter
from financial_assistant.contracts.models import Question
from tests.support import DEMO_SCOPE


class Encoder:
    def encode(self, value):
        return list(range(len(value) // 4))


async def test_transient_retry_is_reserved_and_sdk_usage_recorded(settings, store, monkeypatch):
    monkeypatch.setattr("tiktoken.get_encoding", lambda _: Encoder())
    calls = []

    class Responses:
        async def parse(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                request = httpx.Request("POST", "https://api.openai.com/v1/responses")
                raise RateLimitError(
                    "rate limit", response=httpx.Response(429, request=request), body={}
                )
            return SimpleNamespace(
                output_parsed=Intake(action="proceed", clarification=""),
                usage=SimpleNamespace(input_tokens=100, output_tokens=20),
            )

    adapter = OpenAIAdapter(SimpleNamespace(responses=Responses()), store, settings)
    execution_id = await store.create(
        Question(question="Compare profits", entity="acme"), DEMO_SCOPE
    )
    result = await adapter.structured(
        execution_id=execution_id,
        model=settings.main_model,
        instructions="Analyze",
        payload={},
        output=Intake,
    )
    row = await store.get(execution_id, DEMO_SCOPE)
    assert result.action == "proceed"
    assert row.calls == 2
    assert row.input_tokens == 100 and row.output_tokens == 20
    assert calls[0]["store"] is False
    assert row.reserved_cost > row.actual_cost


async def test_refusal_never_becomes_a_valid_answer(settings, store, monkeypatch):
    monkeypatch.setattr("tiktoken.get_encoding", lambda _: Encoder())

    class Responses:
        async def parse(self, **kwargs):
            return SimpleNamespace(output_parsed=None, usage=None)

    adapter = OpenAIAdapter(SimpleNamespace(responses=Responses()), store, settings)
    execution_id = await store.create(
        Question(question="Compare profits", entity="acme"), DEMO_SCOPE
    )
    with pytest.raises(ModelOutputError):
        await adapter.structured(
            execution_id=execution_id,
            model=settings.main_model,
            instructions="Analyze",
            payload={},
            output=Intake,
        )
