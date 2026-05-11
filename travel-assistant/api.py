import os
import sys
import uuid
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from phoenix.otel import using_attributes  # noqa: E402 — safe to import without a running server

# Phoenix tracing — enabled when PHOENIX_COLLECTOR_ENDPOINT is set (e.g. in Docker Compose).
# auto_instrument=True patches LangChain/LangGraph/OpenAI automatically; no changes needed
# in agent or tool code. Silently skipped when Phoenix is not running.
tracer_provider = None
if os.getenv("PHOENIX_COLLECTOR_ENDPOINT"):
    from phoenix.otel import register
    tracer_provider = register(
        project_name="travel-assistant",
        auto_instrument=True,
    )

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from agent import build_agent  # noqa: E402
from tools import ALL_TOOLS  # noqa: E402

agent = build_agent()

app = FastAPI(
    title="Travel Assistant API",
    description="A LangGraph travel assistant with tools for weather, attractions, flights, hotels, currency, and more.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None


class ChatResponse(BaseModel):
    response: str


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Send a message to the travel assistant and get a response."""
    attrs = {"session_id": request.session_id or str(uuid.uuid4())}
    if request.user_id:
        attrs["user_id"] = request.user_id
    with using_attributes(**attrs):
        result = agent.invoke({"messages": [HumanMessage(content=request.message)]})
    return ChatResponse(response=result["messages"][-1].content)


@app.get("/config")
def config():
    """Return client config including Phoenix project ID (proxied to avoid CORS)."""
    phoenix_endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
    project_id = None
    if phoenix_endpoint:
        try:
            resp = requests.get(f"{phoenix_endpoint}/v1/projects", timeout=3)
            project = next((p for p in resp.json()["data"] if p["name"] == "travel-assistant"), None)
            if project:
                project_id = project["id"]
        except Exception:
            pass
    return {"phoenix_project_id": project_id}


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/tools")
def list_tools():
    """List all available travel assistant tools with descriptions."""
    return [{"name": t.name, "description": t.description} for t in ALL_TOOLS]


@app.on_event("shutdown")
def on_shutdown():
    if tracer_provider:
        tracer_provider.force_flush()
