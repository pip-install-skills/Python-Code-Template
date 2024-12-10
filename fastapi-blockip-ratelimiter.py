from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from cachetools import TTLCache

# Initialize FastAPI app
app = FastAPI(
    title="Template",
    swagger_ui_parameters={"syntaxHighlight": False}
)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a TTL cache for blocked IPs (1 hour TTL)
blocked_ips = TTLCache(maxsize=1000, ttl=3600)

# Create a dictionary to track `4xx` responses by IP
failed_attempts = {}

# Middleware to block IPs
@app.middleware("http")
async def block_ip_middleware(request: Request, call_next):
    client_ip = request.client.host  # Get client IP address

    # Check if the IP is blocked
    if client_ip in blocked_ips:
        return JSONResponse(
            status_code=429,
            content={"detail": "Your IP is temporarily blocked due to excessive failed requests. Please try again after 1 hour."}
        )

    # Process the request
    response = await call_next(request)

    # Track `4xx` responses
    if 400 <= response.status_code < 500:
        if client_ip not in failed_attempts:
            failed_attempts[client_ip] = 1
        else:
            failed_attempts[client_ip] += 1

        # Block IP if `4xx` count exceeds 30
        if failed_attempts[client_ip] >= 30:
            blocked_ips[client_ip] = "blocked"
            del failed_attempts[client_ip]  # Reset failed attempts for this IP
    else:
        # Reset counter on a successful request
        if client_ip in failed_attempts:
            del failed_attempts[client_ip]

    return response

# Rate limit exceeded handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    error_message = exc.detail  # Extract message from exception details
    if "5 per 1 minute" in error_message:
        message = "Rate limit of 5 requests per minute exceeded. Please try again after a minute."
    elif "60 per 1 minute" in error_message:
        message = "Rate limit of 60 requests per minute exceeded. Please try again after a minute."
    elif "10 per 1 hour" in error_message:
        message = "Rate limit of 10 requests per hour exceeded. Please try again after an hour."
    else:
        message = "Rate limit exceeded. Please try again later."

    return JSONResponse(
        status_code=429,
        content={"detail": message}
    )

# Add additional middlewares
app.add_middleware(SlowAPIMiddleware)


@app.get("/")
async def root():
    return RedirectResponse(url="/docs")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
