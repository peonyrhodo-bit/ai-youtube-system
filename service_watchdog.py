import asyncio
import os
from datetime import datetime, timezone

import httpx


CHECK_INTERVAL = int(
    os.getenv("SERVICE_CHECK_INTERVAL", "60")
)

SERVICES = {
    "site-insight-engine": os.getenv(
        "ENGINE_HEALTH_URL",
        "http://site-insight-engine:8000/health",
    ),
    "youtube-mcp": os.getenv(
        "MCP_HEALTH_URL",
        "http://youtube-mcp:8000/",
    ),
}


def now():
    return datetime.now(timezone.utc).isoformat()


async def check_service(
    name: str,
    url: str,
):
    try:
        async with httpx.AsyncClient(
            timeout=10
        ) as client:

            response = await client.get(url)

        if response.status_code < 500:
            return {
                "service": name,
                "status": "ok",
                "code": response.status_code,
            }

        return {
            "service": name,
            "status": "error",
            "code": response.status_code,
        }

    except Exception as error:
        return {
            "service": name,
            "status": "down",
            "error": str(error),
        }


async def watchdog():
    previous = {}

    while True:

        for name, url in SERVICES.items():

            result = await check_service(
                name,
                url,
            )

            state = result["status"]

            if previous.get(name) != state:
                print(
                    now(),
                    "SERVICE_STATE_CHANGED",
                    result,
                    flush=True,
                )

            previous[name] = state

        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(watchdog())
