from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
from typing import Dict

import time

app = FastAPI()
middleware_instance = LoginAttemptMiddleware(app)
app.add_middleware(LoginAttemptMiddleware, app=app)

class LoginAttemptMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # Dictionaries to keep track of failed attempts and block timings
        self.failed_attempts: Dict[str, int] = defaultdict(int)
        self.block_until: Dict[str, float] = defaultdict(float)

    def get_client_ip(self, request: Request) -> str:
        """Returns the actual client IP address from the request."""
        # Get the client IP address from the X-Forwarded-For header if present
        x_forwarded_for = request.headers.get('X-Forwarded-For')
        if x_forwarded_for:
            # Split the header to get the first IP address in the list
            client_ip = x_forwarded_for.split(',')[0].strip()
        else:
            # Use the request client host if no X-Forwarded-For header is present
            client_ip = request.client.host
        return client_ip

    async def dispatch(self, request: Request, call_next):
        client_ip = self.get_client_ip(request)  # Retrieve the client IP using the helper function
        print(client_ip)
        current_time = time.time()
        print(self.failed_attempts)
        print(self.block_until)
        # Check if the IP is blocked
        if current_time < self.block_until.get(client_ip, 0):
            # Return a response indicating the IP is blocked
            message = {"message": "Too many failed login attempts. Please try again later."}
            return JSONResponse(content=message, status_code=429)

        # Process the request
        response = await call_next(request)

        # If the request results in a failed login (401 Unauthorized), increment the counter
        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            self.failed_attempts[client_ip] += 1
            # If failed attempts reach the limit (3), block the IP for 10 minutes
            if self.failed_attempts[client_ip] >= 3:
                self.block_until[client_ip] = current_time + 10  # Block for 10 minutes
                # Reset the failed attempts counter
                self.failed_attempts[client_ip] = 0

        return response


@app.delete("/unblock-ip/{ip_address}")
async def unblock_ip(ip_address: str):
    """Endpoint to unblock a specific IP address."""
    # Remove the IP address from the block_until dictionary
    if ip_address in middleware_instance.block_until:
        del middleware_instance.block_until[ip_address]
        # Reset the failed attempts counter for this IP address
        if ip_address in middleware_instance.failed_attempts:
            del middleware_instance.failed_attempts[ip_address]
        return {"message": f"IP address {ip_address} has been unblocked."}
    else:
        raise HTTPException(status_code=404, detail="IP address not found in blocked list.")

