import asyncio
import json
import math
from decimal import Decimal
from typing import TypeVar

import tiktoken
from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel

from financial_assistant.config import Settings
from financial_assistant.observability.telemetry import COST, EVENTS, TOKENS, span
from financial_assistant.persistence.executions import ExecutionStore

T = TypeVar("T", bound=BaseModel)


class ModelOutputError(RuntimeError):
    pass


class OpenAIAdapter:
    def __init__(self, client: AsyncOpenAI, store: ExecutionStore, settings: Settings):
        self.client, self.store, self.settings = client, store, settings
        self.encoding = tiktoken.get_encoding("o200k_base")

    def cost(self, model: str, inputs: int, outputs: int) -> Decimal:
        if model not in self.settings.pricing:
            raise ModelOutputError("Model has no configured price; refusing unbudgeted execution.")
        incoming, outgoing = self.settings.pricing[model]
        return (inputs * incoming + outputs * outgoing) / Decimal(1000000)

    async def structured(
        self, *, execution_id: str, model: str, instructions: str, payload: dict, output: type[T]
    ) -> T:
        serialized = json.dumps(payload, default=str)
        if len(serialized) > 40000:
            raise ModelOutputError("Model context exceeds application limit.")
        token_text = instructions + serialized + json.dumps(output.model_json_schema())
        estimate = math.ceil(len(self.encoding.encode(token_text)) * 1.2) + 512
        cap = self.settings.max_output_tokens
        for attempt in range(2):
            await self.store.reserve(execution_id, estimate + cap, self.cost(model, estimate, cap))
            try:
                with span("model.structured"):
                    response = await self.client.responses.parse(
                        model=model,
                        instructions=instructions,
                        input=serialized,
                        text_format=output,
                        max_output_tokens=cap,
                        store=False,
                    )
                if response.usage:
                    incoming, outgoing = response.usage.input_tokens, response.usage.output_tokens
                    await self.store.usage(
                        execution_id, incoming, outgoing, self.cost(model, incoming, outgoing)
                    )
                    TOKENS.labels("input").inc(incoming)
                    TOKENS.labels("output").inc(outgoing)
                    COST.inc(float(self.cost(model, incoming, outgoing)))
                if response.output_parsed is None:
                    raise ModelOutputError(
                        "Model refused or did not produce a complete structured response."
                    )
                return response.output_parsed
            except (RateLimitError, APIConnectionError, APIStatusError) as exc:
                if isinstance(exc, RateLimitError) and exc.code in {
                    "insufficient_quota",
                    "credit_balance_exhausted",
                }:
                    raise
                transient = not isinstance(exc, APIStatusError) or exc.status_code in {
                    429,
                    500,
                    502,
                    503,
                    504,
                }
                if not transient or attempt == 1:
                    raise
                EVENTS.labels("model_retry", "transient").inc()
                await asyncio.sleep(0.5)
        raise ModelOutputError("Model retries exhausted.")

    async def embed(self, texts: list[str], execution_id: str | None = None) -> list[list[float]]:
        if not texts or len(texts) > 32 or any(len(t) > 12000 for t in texts):
            raise ValueError("Embedding batch exceeds limits.")
        tokens = sum(len(self.encoding.encode(text)) for text in texts)
        model = self.settings.embedding_model
        if execution_id:
            await self.store.reserve(execution_id, tokens, self.cost(model, tokens, 0))
        with span("model.embedding"):
            response = await self.client.embeddings.create(
                model=model,
                input=texts,
                dimensions=self.settings.embedding_dimensions,
            )
        if execution_id:
            await self.store.usage(
                execution_id,
                response.usage.total_tokens,
                0,
                self.cost(model, response.usage.total_tokens, 0),
            )
        vectors = [item.embedding for item in response.data]
        if any(len(vector) != self.settings.embedding_dimensions for vector in vectors):
            raise ModelOutputError("Embedding dimensions do not match the index.")
        return vectors
