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
        health = await client.get("/health")
        ready = await client.get("/ready")
        assert health.status_code == ready.status_code == 200
        question = {"question": "Compare profits", "entity": "acme", "periods": []}
        assert (await client.post("/questions", json=question)).status_code == 401
        denied = await client.post(
            "/questions", json={**question, "entity": "beta"}, headers=headers
        )
        assert denied.status_code == 403
        accepted = await client.post("/questions", json=question, headers=headers)
        accepted.raise_for_status()
        execution_id = accepted.json()["execution_id"]
        cancellation = await client.post(
            f"/executions/{execution_id}/cancel", json={}, headers=headers
        )
        cancellation.raise_for_status()
        result = await client.get(f"/executions/{execution_id}", headers=headers)
        assert result.json()["status"] == "cancelled"
        destination = Path("artifacts/container-smoke.json")
        destination.parent.mkdir(exist_ok=True)
        await asyncio.to_thread(
            destination.write_text,
            json.dumps(
                {
                    "health": health.status_code,
                    "ready": ready.status_code,
                    "unauthenticated": 401,
                    "cross_entity": denied.status_code,
                    "cancelled_status": result.json()["status"],
                    "model_calls": 0,
                },
                indent=2,
            ),
        )
    print(
        "Container HTTP smoke passed: readiness, authentication, entity denial, durable submission, cancellation."
    )


if __name__ == "__main__":
    asyncio.run(run())
