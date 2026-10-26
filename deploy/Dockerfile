FROM python:3.12.12-slim-bookworm AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy TIKTOKEN_CACHE_DIR=/app/tokenizer-cache
RUN pip install --no-cache-dir uv==0.13.5
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
RUN .venv/bin/python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"

FROM python:3.12.12-slim-bookworm
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TIKTOKEN_CACHE_DIR=/app/tokenizer-cache
RUN groupadd --gid 10001 finance && useradd --uid 10001 --gid finance --create-home finance
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/tokenizer-cache /app/tokenizer-cache
COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"]
CMD ["uvicorn", "financial_assistant.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--timeout-graceful-shutdown", "30"]
