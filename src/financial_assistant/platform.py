import asyncio
import sys
from collections.abc import Coroutine
from typing import Any


def run_async[T](coroutine: Coroutine[Any, Any, T]) -> T:
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    return asyncio.run(coroutine, loop_factory=factory)
