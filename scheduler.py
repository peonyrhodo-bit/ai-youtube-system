import asyncio
import os
from datetime import datetime, timezone

import httpx


ENGINE_URL = os.getenv(
    "ENGINE_URL",
    "http://site-insight-engine:8000",
)

INTERVAL = int(
    os.getenv("DIRECTOR_INTERVAL", "21600")
)


def now():
    return datetime.now(timezone.utc).isoformat()


async def run_director():
    url = f"{ENGINE_URL}/director/run"

    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.get(
            url,
            params={
                "language": "ru",
                "region_code": "RU",
                "hours_back": 72,
                "max_results": 50,
            },
        )

        response.raise_for_status()

        print(
            now(),
            "DIRECTOR_RUN",
            response.json(),
            flush=True,
        )


async def scheduler_loop():
    while True:
        try:
            await run_director()

        except Exception as error:
            print(
                now(),
                "DIRECTOR_ERROR",
                type(error).__name__,
                str(error),
                flush=True,
            )

        await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    asyncio.run(scheduler_loop())
