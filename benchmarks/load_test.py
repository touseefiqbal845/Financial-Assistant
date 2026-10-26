import argparse
import asyncio
import os
from statistics import median
from time import perf_counter

import httpx
from dotenv import load_dotenv


async def run(url: str, requests: int) -> None:
    semaphore = asyncio.Semaphore(4)
    samples = []
    headers = {"Authorization": "Bearer " + os.environ["FIN_DEV_TOKEN"]}
    async with httpx.AsyncClient(base_url=url, timeout=10) as client:

        async def submit() -> None:
            async with semaphore:
                started = perf_counter()
                response = await client.post(
                    "/questions",
                    headers=headers,
                    json={"question": "Compare profits", "entity": "acme", "periods": []},
                )
                response.raise_for_status()
                execution_id = response.json()["execution_id"]
                cancelled = await client.post(
                    f"/executions/{execution_id}/cancel", headers=headers, json={}
                )
                cancelled.raise_for_status()
                samples.append(perf_counter() - started)

        await asyncio.gather(*(submit() for _ in range(requests)))
    print(
        {
            "requests": requests,
            "median_submission_cancel_seconds": median(samples),
            "max_seconds": max(samples),
        }
    )


if __name__ == "__main__":
    load_dotenv(".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=10, choices=range(1, 101))
    args = parser.parse_args()
    asyncio.run(run(args.url, args.requests))
