from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import docker
import os
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins. Adjust this for security.
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

client = docker.from_env()

class CodeRequest(BaseModel):
    code: str

@app.post("/run-code/")
async def run_code(request: CodeRequest):
    # Validate input code
    if len(request.code.strip()) == 0:
        raise HTTPException(status_code=400, detail="Code cannot be empty")

    # Create a temporary directory for the code
    temp_dir = f"/tmp/{uuid.uuid4()}"
    os.makedirs(temp_dir)
    
    # Save the code to a file
    code_file_path = os.path.join(temp_dir, "script.py")
    with open(code_file_path, "w") as code_file:
        code_file.write(request.code)
    
    try:
        # Check if the file exists before running the container
        if not os.path.exists(code_file_path):
            raise HTTPException(status_code=500, detail="Code file was not created")

        # Run the code in a Docker container
        result = client.containers.run(
            "my-python-env",
            f"python /mnt/script.py",
            volumes={os.path.abspath(temp_dir): {'bind': '/mnt', 'mode': 'ro'}},
            network_disabled=False,  # Disable network access
            user='nobody',  # Run as a non-root user
            mem_limit='100m',  # Limit memory usage
            pids_limit=10,  # Limit process creation
            detach=False,  # Wait for the container to finish
            remove=True,  # Remove the container after execution
            stderr=True  # Capture stderr
        )
    except docker.errors.ContainerError as e:
        raise HTTPException(status_code=400, detail=f"Error running code: {e.stderr.decode()}")
    finally:
        # Clean up the temporary directory
        if os.path.exists(code_file_path):
            os.remove(code_file_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
    response = {"result": result.decode("utf-8")}
    return JSONResponse(content=response, status_code=status.HTTP_200_OK)

@app.get("/")
async def root():
    return RedirectResponse(url="/docs")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
