from fastapi import FastAPI, Request
from starlette.responses import StreamingResponse, PlainTextResponse
from starlette.background import BackgroundTask
from typing import List, Tuple
from urllib.parse import urlparse

import httpx
import itertools
import json
import logging
import os
import time

# ---- Basic logging (tunable via LOG_LEVEL) ----
_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("azure-proxy")

CONFIG_PATH = os.getenv("AZURE_PROXY_CONFIG", "azure_instances.json")

"""
Example config file (azure_instances.json):

{
  "instances": [
    { "endpoint": "https://eastus-xyz.openai.azure.com", "api_key": "XXXX" },
    { "endpoint": "https://westus-xyz.openai.azure.com/", "api_key": "XXXX" }
  ],
  "header_name": "api-key"
}
"""

# ---------- Load credentials from JSON ----------
def _load_config(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"Config file not found: {path}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Bad JSON in {path}: {e}")

    instances = data.get("instances") or []
    header_name = (data.get("header_name") or "api-key").strip()

    if not isinstance(instances, list) or not instances:
        raise RuntimeError("Config must contain a non-empty 'instances' array.")

    creds: List[Tuple[str, str]] = []
    for i, item in enumerate(instances):
        ep = (item.get("endpoint") or "").strip().rstrip("/")
        key = (item.get("api_key") or "").strip()
        if not ep or not key:
            raise RuntimeError(f"instances[{i}] must include 'endpoint' and 'api_key'.")
        creds.append((ep, key))

    # dedupe while keeping order
    seen = set()
    uniq = []
    for pair in creds:
        if pair not in seen:
            uniq.append(pair)
            seen.add(pair)

    return uniq, header_name

CREDENTIALS, HEADER_NAME = _load_config(CONFIG_PATH)
_rr_cycle = itertools.cycle(CREDENTIALS)
logger.info("Loaded %d upstream instance(s); auth header='%s'", len(CREDENTIALS), HEADER_NAME)

# ---------- Proxy w/ failover ----------
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade"
}

app = FastAPI()

def _host(url: str) -> str:
    return urlparse(url).netloc or url

@app.middleware("http")
async def proxy_middleware(request: Request, call_next):
    started = time.perf_counter()

    # round-robin starting point per request
    candidates = [next(_rr_cycle) for _ in range(len(CREDENTIALS))]

    # Build path+query and base headers once
    path_and_query = request.url.path
    if request.url.query:
        path_and_query += f"?{request.url.query}"

    base_headers = {k.lower(): v for k, v in request.headers.items()
                    if k.lower() not in HOP_BY_HOP and k.lower() != "host"}
    # scrub any inbound auth
    base_headers.pop("api-key", None)
    base_headers.pop("authorization", None)

    body = await request.body()

    logger.info("Request %s %s (attempts=%d)", request.method, request.url.path, len(candidates))

    last_error = None
    async with httpx.AsyncClient() as client:
        for idx, (endpoint, api_key) in enumerate(candidates, start=1):
            target_url = f"{endpoint}{path_and_query}"
            headers = dict(base_headers)
            headers[HEADER_NAME] = api_key

            logger.info("Attempt %d/%d -> %s", idx, len(candidates), _host(endpoint))

            req = client.build_request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )

            try:
                upstream = await client.send(req, stream=True)
            except httpx.HTTPError as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.error("Attempt %d failed with transport error: %s", idx, e)
                continue

            if upstream.status_code >= 400:
                await upstream.aclose()
                last_error = f"HTTP {upstream.status_code} from {endpoint}"
                if upstream.status_code >= 500:
                    logger.error("Attempt %d got %s", idx, last_error)
                else:
                    logger.warning("Attempt %d got %s", idx, last_error)
                continue

            # Success
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.info("Success via %s (status=%d, duration=%dms)",
                        _host(endpoint), upstream.status_code, duration_ms)

            resp_headers = {k: v for k, v in upstream.headers.items()
                            if k.lower() not in HOP_BY_HOP}
            return StreamingResponse(
                upstream.aiter_raw(),
                background=BackgroundTask(upstream.aclose),
                status_code=upstream.status_code,
                headers=resp_headers,
                media_type=upstream.headers.get("content-type"),
            )

    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.error("All upstreams failed after %dms. Last error: %s", duration_ms, last_error or "unknown error")
    return StreamingResponse(status_code=upstream.status_code, content=f"All upstreams failed. Last error: {last_error or 'unknown error'}")

@app.api_route(
    "/{full_path:path}",
    methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"]
)
async def catch_all(full_path: str):
    return PlainTextResponse("Not found", status_code=404)
