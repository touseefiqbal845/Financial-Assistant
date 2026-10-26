import json
import logging
import os
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Thread
from time import perf_counter
from typing import Any
from wsgiref.simple_server import WSGIServer, make_server

from opentelemetry import trace
from prometheus_client import Counter, Histogram, make_wsgi_app

LATENCY = Histogram("finance_step_seconds", "Step duration", ["step"])
EVENTS = Counter("finance_events_total", "Bounded operational events", ["kind", "outcome"])
TOKENS = Counter("finance_model_tokens_total", "Model usage", ["direction"])
COST = Counter("finance_model_estimated_cost_usd_total", "Estimated model spend")
tracer = trace.get_tracer("financial_assistant")


def redact(value: str) -> str:
    value = re.sub(r"Bearer\s+\S+", "Bearer [REDACTED]", value, flags=re.I)
    value = re.sub(r"sk-[\w-]+", "[REDACTED]", value)
    return re.sub(r"(://[^:\s/]+:)[^@\s]+@", r"\1[REDACTED]@", value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"level": record.levelname, "message": redact(record.getMessage())})


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.getLogger("financial_assistant").handlers = [handler]
    logging.getLogger("financial_assistant").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def configure_tracing() -> None:
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": "financial-assistant"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)


def worker_metrics(token: str) -> tuple[WSGIServer, Thread]:
    metrics_app = make_wsgi_app()

    def protected(environ: dict, start_response: Any) -> Any:
        if not secrets.compare_digest(environ.get("HTTP_AUTHORIZATION", ""), "Bearer " + token):
            start_response("401 Unauthorized", [("Content-Type", "text/plain")])
            return [b"Unauthorized"]
        return metrics_app(environ, start_response)

    server = make_server("0.0.0.0", 9001, protected)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


@contextmanager
def span(step: str) -> Iterator[Any]:
    start = perf_counter()
    with tracer.start_as_current_span(
        step, record_exception=False, set_status_on_exception=False
    ) as current:
        try:
            yield current
        finally:
            LATENCY.labels(step).observe(perf_counter() - start)
