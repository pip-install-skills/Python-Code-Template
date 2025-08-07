
import httpx
import itertools
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from starlette.responses import StreamingResponse, Response
from starlette.background import BackgroundTask

load_dotenv()

# 1. Read your Azure endpoint and key
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_KEY      = os.getenv("AZURE_OPENAI_API_KEY", "")

if not AZURE_ENDPOINT or not AZURE_KEY:
    raise RuntimeError(
        "Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY (without trailing slashes)"
    )

# 2. Prepare round-robin over (endpoint, key) pairs
credential_cycle = itertools.cycle({AZURE_ENDPOINT: AZURE_KEY}.items())

app = FastAPI()

@app.middleware("http")
async def proxy_middleware(request: Request, call_next):
    # Rotate to next (endpoint, api_key) pair
    endpoint, api_key = next(credential_cycle)

    # Rebuild the full target URL
    target_url = f"{endpoint}{request.url.path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    # Copy incoming headers, drop Host, override api-key
    headers = dict(request.headers)
    headers.pop("host", None)
    headers["api-key"] = api_key

    # Read raw body
    body = await request.body()

    async with httpx.AsyncClient() as client:
        req = client.build_request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
        )
        try:
            upstream = await client.send(req, stream=True)
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Upstream error: {e}")

    return StreamingResponse(
        upstream.aiter_raw(),
        background=BackgroundTask(upstream.aclose),
        status_code=upstream.status_code,
        headers=dict(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )

@app.api_route(
    "/{full_path:path}",
    methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"]
)
async def catch_all(full_path: str):
    return Response(status_code=404)
