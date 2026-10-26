from openai import AsyncOpenAI

from financial_assistant.config import Settings
from financial_assistant.platform import run_async


async def run() -> None:
    settings = Settings()
    if not settings.openai_api_key:
        raise ValueError("FIN_OPENAI_API_KEY is not configured.")
    requested = {
        settings.main_model,
        settings.planner_model,
        settings.data_model,
        settings.document_model,
        settings.analysis_model,
        settings.embedding_model,
    }
    async with AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(), max_retries=0
    ) as client:
        available = {item.id async for item in client.models.list()}
    missing = requested - available
    if missing:
        raise ValueError("Requested models are unavailable: " + ", ".join(sorted(missing)))
    print(
        "All configured model IDs are listed for this account. Run bounded live evaluation to verify capabilities."
    )


def main() -> None:
    run_async(run())
