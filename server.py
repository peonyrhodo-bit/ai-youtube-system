import os
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse


APP_NAME = "AI YouTube System"

PORT = int(os.getenv("PORT", "8000"))

ENGINE_URL = os.getenv(
    "ENGINE_URL",
    "http://site-insight-engine:8000",
).rstrip("/")

REQUEST_TIMEOUT = float(
    os.getenv("ENGINE_REQUEST_TIMEOUT", "300")
)


app = FastAPI(
    title=APP_NAME,
    version="0.1.0",
)


def now():
    return datetime.now(timezone.utc).isoformat()


async def engine_request(
    method: str,
    path: str,
    params: dict | None = None,
    json: dict | None = None,
):
    url = f"{ENGINE_URL}{path}"

    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT
        ) as client:

            response = await client.request(
    method,
    url,
    params=params,
    json=json,
)

    except httpx.RequestError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "engine_unavailable",
                "engine_url": ENGINE_URL,
                "error_type": type(error).__name__,
                "error": str(error),
            },
        ) from error

    try:
        data = response.json()
    except Exception:
        data = {
            "raw_response": response.text,
        }

    if response.status_code >= 500:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "engine_error",
                "engine_status_code": response.status_code,
                "response": data,
            },
        )

    return data


@app.get("/")
async def root():
    return {
        "service": APP_NAME,
        "status": "ok",
        "time": now(),
    }


@app.get("/health")
async def health():
    return {
        "service": APP_NAME,
        "status": "ok",
        "time": now(),
    }


@app.get("/status")
async def status():
    engine = {
        "status": "unknown",
        "url": ENGINE_URL,
    }

    try:
        data = await engine_request(
            "GET",
            "/health",
        )

        engine = {
            "status": "ok",
            "url": ENGINE_URL,
            "response": data,
        }

    except HTTPException as error:
        engine = {
            "status": "error",
            "url": ENGINE_URL,
            "error": error.detail,
        }

    return {
        "service": APP_NAME,
        "status": "ok",
        "time": now(),
        "engine": engine,
    }


@app.post("/director/run")
async def director_run(
    language: str = "ru",
    region_code: str = "RU",
    hours_back: int = 72,
    max_results: int = 50,
):
    if not 1 <= hours_back <= 168:
        raise HTTPException(
            status_code=400,
            detail="hours_back must be between 1 and 168",
        )

    if not 1 <= max_results <= 50:
        raise HTTPException(
            status_code=400,
            detail="max_results must be between 1 and 50",
        )

    return await engine_request(
        "GET",
        "/director/run",
        params={
            "language": language,
            "region_code": region_code,
            "hours_back": hours_back,
            "max_results": max_results,
        },
    )


@app.get("/director/history")
async def director_history():
    return await engine_request(
        "GET",
        "/director/history",
    )
class DirectorChatRequest(BaseModel):
    message: str

@app.post("/director/chat")
async def director_chat(
    request: DirectorChatRequest,
):
    return await engine_request(
        "POST",
        "/director/chat",
        json=request.model_dump(),
    )

@app.get("/events")
async def events():
    return await engine_request(
        "GET",
        "/events",
    )


@app.get("/radar")
async def radar(
    language: str = "ru",
    hours_back: int = 72,
    max_results: int = 50,
):
    return await engine_request(
        "GET",
        "/radar",
        params={
            "language": language,
            "hours_back": hours_back,
            "max_results": max_results,
        },
    )


@app.get("/director-debug")
async def director_debug():
    return await engine_request(
        "GET",
        "/director-debug",
    )


@app.get("/radar-debug")
async def radar_debug(
    max_results: int = 10,
    language: str = "ru",
    hours_back: int = 72,
):
    return await engine_request(
        "GET",
        "/radar-debug",
        params={
            "max_results": max_results,
            "language": language,
            "hours_back": hours_back,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request,
    error: Exception,
):
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error_type": type(error).__name__,
            "error": str(error),
            "path": str(request.url.path),
            "time": now(),
        },
    )
