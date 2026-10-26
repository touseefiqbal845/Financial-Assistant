import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from financial_assistant.bootstrap import Services, build_services
from financial_assistant.config import Settings
from financial_assistant.contracts.models import Question, Scope
from financial_assistant.observability.telemetry import configure_logging, configure_tracing
from financial_assistant.persistence.executions import QueueFull
from financial_assistant.security.authorization import AccessDenied, require_entity
from financial_assistant.security.request_limits import RequestLimits


def create_app(settings: Settings | None = None, injected: Services | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        configure_tracing()
        async with AsyncExitStack() as stack:
            selected = settings or Settings()
            app.state.settings = selected
            app.state.services = injected or await build_services(selected, stack)
            yield

    app = FastAPI(title="Financial Assistant", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            {"error": exc.detail, "request_id": request.state.request_id},
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {"error": "invalid_request", "request_id": request.state.request_id}, status_code=422
        )

    @app.exception_handler(AccessDenied)
    async def access_error(request: Request, exc: AccessDenied) -> JSONResponse:
        return JSONResponse(
            {"error": "access_denied", "request_id": request.state.request_id}, status_code=403
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            {"error": "internal_error", "request_id": request.state.request_id}, status_code=500
        )

    @app.exception_handler(QueueFull)
    async def queue_error(request: Request, exc: QueueFull) -> JSONResponse:
        return JSONResponse(
            {"error": "queue_limit", "request_id": request.state.request_id}, status_code=429
        )

    async def scope(request: Request, authorization: str | None = Header(default=None)) -> Scope:
        return await request.app.state.services.auth.authenticate(authorization)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(request: Request) -> dict:
        try:
            async with request.app.state.services.store.sessions() as session:
                await session.execute(text("SELECT 1 FROM executions LIMIT 1"))
        except Exception as exc:
            raise HTTPException(503, "storage_not_ready") from exc
        return {"status": "ready", "execution": "durable-worker-required"}

    @app.post("/questions", status_code=202)
    async def ask(
        body: Question, request: Request, identity: Annotated[Scope, Depends(scope)]
    ) -> dict:
        require_entity(identity, body.entity)
        execution_id = await request.app.state.services.store.create(body, identity)
        return {"execution_id": execution_id, "status": "pending"}

    @app.get("/executions/{execution_id}")
    async def execution(
        execution_id: UUID, request: Request, identity: Annotated[Scope, Depends(scope)]
    ) -> dict:
        row = await request.app.state.services.store.get(str(execution_id), identity)
        if row is None:
            raise HTTPException(404, "execution_not_found")
        return {
            "execution_id": row.id,
            "status": row.status,
            "answer": row.result,
            "error_code": row.error_code,
            "usage": {
                "calls": row.calls,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "estimated_cost_usd": str(row.actual_cost),
                "pricing_version": request.app.state.settings.pricing_version,
            },
        }

    @app.post("/executions/{execution_id}/cancel", status_code=202)
    async def cancel(
        execution_id: UUID, request: Request, identity: Annotated[Scope, Depends(scope)]
    ) -> dict:
        if not await request.app.state.services.store.cancel(str(execution_id), identity):
            raise HTTPException(404, "execution_not_found")
        return {"execution_id": str(execution_id), "cancellation_requested": True}

    @app.get("/metrics")
    async def metrics(
        request: Request, authorization: str | None = Header(default=None)
    ) -> Response:
        token = request.app.state.settings.metrics_token
        if not token or not secrets.compare_digest(
            authorization or "", "Bearer " + token.get_secret_value()
        ):
            raise HTTPException(401, "metrics_auth_required")
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.add_middleware(RequestLimits)
    return app


app = create_app()
