import asyncio
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


async def run() -> None:
    load_dotenv(".env")
    headers = {"Authorization": "Bearer " + os.environ["FIN_DEV_TOKEN"]}
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=10) as client:
        submitted = await client.post(
            "/questions",
            headers=headers,
            json={"question": "Compare profits", "entity": "acme", "periods": []},
        )
        submitted.raise_for_status()
        execution_id = submitted.json()["execution_id"]
        for _ in range(60):
            response = await client.get(f"/executions/{execution_id}", headers=headers)
            response.raise_for_status()
            result = response.json()
            if result["status"] not in {"pending", "running"}:
                assert result["status"] == "succeeded", result
                assert result["answer"]["status"] == "clarification"
                assert result["usage"]["calls"] == 0
                destination = Path("artifacts/worker-smoke.json")
                await asyncio.to_thread(destination.write_text, json.dumps(result, indent=2))
                print(
                    "Separate container worker completed a persisted clarification job with zero model calls."
                )
                return
            await asyncio.sleep(0.5)
    raise TimeoutError("Worker did not complete the synthetic clarification job.")


if __name__ == "__main__":
    asyncio.run(run())
