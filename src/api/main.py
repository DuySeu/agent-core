"""FastAPI application entrypoint.

Run (from the repo root):

    PYTHONPATH=src uvicorn api.main:app --reload

Then open http://127.0.0.1:8000/docs for the interactive API.
"""

from fastapi import FastAPI

from api.routes import chat, health

app = FastAPI(title="agent-core API")

app.include_router(health.router, tags=["health"])
app.include_router(chat.router, tags=["chat"])


@app.get("/")
def root():
    return {"service": "agent-core", "docs": "/docs", "health": "/health"}
