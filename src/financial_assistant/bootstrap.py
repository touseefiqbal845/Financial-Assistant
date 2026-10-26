from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from openai import AsyncOpenAI
from psycopg.conninfo import make_conninfo
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from financial_assistant.agents.main_agent import MainAgent
from financial_assistant.agents.planning_agent import PlanningAgent
from financial_assistant.agents.specialist import Specialist
from financial_assistant.config import Settings
from financial_assistant.connectors.databases.postgres import PostgresSources
from financial_assistant.connectors.models.openai_adapter import OpenAIAdapter
from financial_assistant.contracts.models import Role
from financial_assistant.persistence.executions import ExecutionStore
from financial_assistant.security.authentication import Authenticator
from financial_assistant.tools.dispatcher import ToolDispatcher
from financial_assistant.workflows.graph import build_graph


@dataclass
class Services:
    store: ExecutionStore
    auth: Authenticator
    graph: Any = None


def prompt(name: str) -> str:
    return (Path(__file__).parent / "prompts" / f"{name}.md").read_text(encoding="utf-8")


async def build_services(
    settings: Settings, stack: AsyncExitStack, *, worker: bool = False
) -> Services:
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )
    stack.push_async_callback(engine.dispose)
    store = ExecutionStore(async_sessionmaker(engine, expire_on_commit=False), settings)
    services = Services(store=store, auth=Authenticator(settings))
    if not worker:
        return services
    if not settings.openai_api_key:
        raise ValueError("FIN_OPENAI_API_KEY is required for worker execution.")
    source_engine = create_async_engine(
        settings.source_database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )
    stack.push_async_callback(source_engine.dispose)
    client = AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(), timeout=25, max_retries=0
    )
    stack.push_async_callback(client.close)
    model = OpenAIAdapter(client, store, settings)
    sources = PostgresSources(
        async_sessionmaker(source_engine, expire_on_commit=False), model, settings.embedding_model
    )
    dispatcher = ToolDispatcher(sources, store, settings)
    workers = {
        Role.DATA: Specialist(model, settings.data_model, prompt("specialist"), dispatcher),
        Role.DOCUMENTS: Specialist(
            model, settings.document_model, prompt("specialist"), dispatcher
        ),
        Role.ANALYSIS: Specialist(model, settings.analysis_model, prompt("specialist"), dispatcher),
    }
    checkpointer = await stack.enter_async_context(
        AsyncPostgresSaver.from_conn_string(
            make_conninfo(settings.checkpoint_url.get_secret_value(), connect_timeout=5)
        )
    )
    services.graph = build_graph(
        MainAgent(model, settings.main_model, prompt("main")),
        PlanningAgent(model, settings.planner_model, prompt("planner")),
        workers,
        settings,
        checkpointer,
    )
    return services
