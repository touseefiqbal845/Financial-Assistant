from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class Model(Protocol):
    async def structured(
        self, *, execution_id: str, model: str, instructions: str, payload: dict, output: type[T]
    ) -> T: ...


class Embedder(Protocol):
    async def embed(
        self, texts: list[str], execution_id: str | None = None
    ) -> list[list[float]]: ...
