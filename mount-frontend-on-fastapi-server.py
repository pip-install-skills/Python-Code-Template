from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import os

app = FastAPI(
    swagger_ui_parameters={"syntaxHighlight": False}
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return FileResponse("client/dist/index.html")

@app.exception_handler(404)
async def exception_404_handler(request, exc):
    return FileResponse("client/dist/index.html")

app.mount("/", StaticFiles(directory="client/dist/"), name="ui")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host='0.0.0.0', port=8000, workers=2, reload=False)
