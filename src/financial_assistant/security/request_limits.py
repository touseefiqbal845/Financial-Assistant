import asyncio
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestLimits:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        body = bytearray()
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > 8192:
                        response = JSONResponse(
                            {"error": "request_size", "request_id": str(uuid4())}, status_code=413
                        )
                        await response(scope, receive, send)
                        return
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            response = JSONResponse(
                {"error": "request_timeout", "request_id": str(uuid4())}, status_code=408
            )
            await response(scope, receive, send)
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)
