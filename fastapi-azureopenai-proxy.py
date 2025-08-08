from fastapi import FastAPI, Request, HTTPException
from starlette.responses import StreamingResponse, PlainTextResponse
from starlette.background import BackgroundTask
from typing import List, Tuple
from urllib.parse import urlparse

import httpx
import asyncio
import json
import logging
import os
import time
import uuid
import contextvars

# ---- Basic logging with request_id ----
request_id_var = contextvars.ContextVar("request_id", default="-")

class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")
        return True

def init_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    fmt = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format=fmt,
    )
    # Attach filter to all handlers (works under uvicorn too)
    root = logging.getLogger()
    f = RequestIdFilter()
    for h in root.handlers:
        h.addFilter(f)

init_logging()
logger = logging.getLogger("azure-proxy")

CONFIG_PATH = os.getenv("AZURE_PROXY_CONFIG", "azure_instances.json")

"""
Example config file (azure_instances.json):

{
  "instances": [
    { "endpoint": "https://eastus-xyz.openai.azure.com", "api_key": "XXXX" },
    { "endpoint": "https://westus-xyz.openai.azure.com/", "api_key": "YYYY" },
    { "endpoint": "https://swedencentral-abc.openai.azure.com/", "api_key": "ZZZZ" }
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
N = len(CREDENTIALS)
logger.info("Loaded %d upstream instance(s); auth header='%s'", N, HEADER_NAME)

# ---------- Proxy w/ rotating failover ----------
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade"
}

app = FastAPI()
app.state.rr_pos = 0                 # start index for next request
app.state.rr_lock = asyncio.Lock()   # protects rr_pos

def _host(url: str) -> str:
    return urlparse(url).netloc or url

@app.middleware("http")
async def proxy_middleware(request: Request, call_next):
    # set/propagate a request id (8-hex is readable; use full uuid if you prefer)
    req_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:8]
    request_id_var.set(req_id)

    started = time.perf_counter()

    # Determine the attempt order for THIS request using the shared pointer.
    async with request.app.state.rr_lock:
        start = request.app.state.rr_pos
    order_indices = [(start + off) % N for off in range(N)]
    order = [(i, CREDENTIALS[i]) for i in order_indices]

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
    logger.info("Request %s %s (order=%s)",
                request.method, request.url.path,
                ",".join(_host(CREDENTIALS[i][0]) for i in order_indices))

    last_error = None
    async with httpx.AsyncClient() as client:
        for attempt_num, (abs_idx, (endpoint, api_key)) in enumerate(order, start=1):
            target_url = f"{endpoint}{path_and_query}"
            headers = dict(base_headers)
            headers[HEADER_NAME] = api_key
            # propagate request id upstream if you want (not required)
            headers.setdefault("x-request-id", req_id)

            logger.info("Attempt %d/%d -> %s", attempt_num, N, _host(endpoint))

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
                logger.error("Attempt %d failed with transport error: %s", attempt_num, e)
                continue

            if upstream.status_code >= 400:
                await upstream.aclose()
                last_error = f"HTTP {upstream.status_code} from {endpoint}"
                if upstream.status_code >= 500:
                    logger.error("Attempt %d got %s", attempt_num, last_error)
                else:
                    logger.warning("Attempt %d got %s", attempt_num, last_error)
                continue

            # ---- SUCCESS: advance shared pointer to the element AFTER the one that succeeded
            async with request.app.state.rr_lock:
                request.app.state.rr_pos = (abs_idx + 1) % N

            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.info("Success via %s (status=%d, duration=%dms). Next start=%d",
                        _host(endpoint), upstream.status_code, duration_ms, request.app.state.rr_pos)

            resp_headers = {k: v for k, v in upstream.headers.items()
                            if k.lower() not in HOP_BY_HOP}
            resp_headers["x-request-id"] = req_id

            return StreamingResponse(
                upstream.aiter_raw(),
                background=BackgroundTask(upstream.aclose),
                status_code=upstream.status_code,
                headers=resp_headers,
                media_type=upstream.headers.get("content-type"),
            )

    # ---- ALL FAILED: optionally advance by 1 so next request doesn't retry the same first
    async with request.app.state.rr_lock:
        request.app.state.rr_pos = (start + 1) % N

    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.error("All upstreams failed after %dms. Next start=%d. Last error: %s",
                 duration_ms, request.app.state.rr_pos, last_error or "unknown error")
    # include the request id back to the client
    raise HTTPException(status_code=502, detail=f"All upstreams failed. Last error: {last_error or 'unknown error'}")

@app.api_route(
    "/{full_path:path}",
    methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"]
)
async def catch_all(full_path: str):
    # echo request id here too
    return PlainTextResponse("Not found", status_code=404, headers={"x-request-id": request_id_var.get("-")})
