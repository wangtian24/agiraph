"""FastAPI server — all endpoints for the Agiraph API."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agiraph.agent import Agent
from agiraph.config import BASE_DIR, SERVER_HOST, SERVER_PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Agiraph", version="2.0", description="Autonomous AI Agent Framework")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent registry — all active agents
agent_registry: dict[str, Agent] = {}


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class CreateAgentRequest(BaseModel):
    goal: str
    model: str = "anthropic/claude-sonnet-4-5"
    mode: str = "finite"


class SendRequest(BaseModel):
    message: str
    to: str = "coordinator"


class RespondRequest(BaseModel):
    response: str
    question_id: str | None = None


# ---------------------------------------------------------------------------
# Agent Lifecycle
# ---------------------------------------------------------------------------


@app.post("/agents")
async def create_agent(req: CreateAgentRequest) -> dict:
    """Create a new agent with a goal."""
    agent = Agent(goal=req.goal, model=req.model, mode=req.mode)
    agent_registry[agent.id] = agent

    # Start the agent in the background
    asyncio.create_task(agent.start())

    logger.info(f"Agent {agent.id} created and started: {req.goal[:80]}")
    return agent.summary()


@app.get("/agents")
async def list_agents() -> list[dict]:
    """List all agents."""
    return [a.summary() for a in agent_registry.values()]


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict:
    """Get agent status and summary."""
    agent = _get_agent(agent_id)
    return agent.summary()


@app.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str) -> dict:
    """Stop and remove an agent."""
    agent = _get_agent(agent_id)
    await agent.stop()
    agent_registry.pop(agent_id, None)
    return {"status": "deleted", "id": agent_id}


@app.post("/agents/{agent_id}/stop")
async def stop_agent(agent_id: str) -> dict:
    """Stop the agent — kill coordinator and workers, keep state for inspection."""
    agent = _get_agent(agent_id)
    await agent.stop()
    return {"status": "stopped", "id": agent_id}


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------


@app.post("/agents/{agent_id}/send")
async def send_message(agent_id: str, req: SendRequest) -> dict:
    """Send a message to the agent (human -> agent)."""
    agent = _get_agent(agent_id)
    result = await agent.send_message(req.message, req.to)
    return {"status": "sent", "to": req.to, "message": req.message}


@app.post("/agents/{agent_id}/respond")
async def respond_to_question(agent_id: str, req: RespondRequest) -> dict:
    """Respond to an ask_human question."""
    agent = _get_agent(agent_id)
    await agent.respond_to_question(req.response)
    return {"status": "delivered"}


@app.get("/agents/{agent_id}/conversation")
async def get_conversation(agent_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """Get conversation thread."""
    agent = _get_agent(agent_id)
    start = max(0, len(agent.conversation_log) - offset - limit)
    end = len(agent.conversation_log) - offset
    return agent.conversation_log[start:end]


# ---------------------------------------------------------------------------
# Work Board
# ---------------------------------------------------------------------------


@app.get("/agents/{agent_id}/board")
async def get_board(agent_id: str) -> dict:
    """Get all work nodes and their status."""
    agent = _get_agent(agent_id)
    return agent.board_view()


@app.get("/agents/{agent_id}/board/{node_id}")
async def get_node(agent_id: str, node_id: str) -> dict:
    """Get a single node's detail."""
    agent = _get_agent(agent_id)
    node = agent.board.get(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    result = node.to_dict()

    # Include published files if available
    if node.data_dir:
        published = node.data_dir / "published"
        if published.exists():
            result["published_files"] = [f.name for f in published.iterdir()]
        spec = node.data_dir / "_spec.md"
        if spec.exists():
            result["spec"] = spec.read_text()
    return result


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------


@app.get("/agents/{agent_id}/workers")
async def get_workers(agent_id: str) -> list[dict]:
    """List active workers."""
    agent = _get_agent(agent_id)
    return agent.workers_view()


# ---------------------------------------------------------------------------
# Workspace File Browser
# ---------------------------------------------------------------------------


@app.get("/agents/{agent_id}/workspace")
async def list_workspace(agent_id: str, path: str = "") -> dict:
    """List workspace files/directories."""
    agent = _get_agent(agent_id)
    base = agent.current_run_dir
    target = (base / path).resolve()

    if not str(target).startswith(str(base.resolve())):
        raise HTTPException(status_code=403, detail="Path escapes workspace")

    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    if target.is_file():
        content = target.read_text(errors="replace")
        return {"type": "file", "path": path, "content": content[:100000]}

    entries = []
    for item in sorted(target.iterdir()):
        entries.append({
            "name": item.name,
            "type": "dir" if item.is_dir() else "file",
            "size": item.stat().st_size if item.is_file() else None,
        })
    return {"type": "dir", "path": path, "entries": entries}


# ---------------------------------------------------------------------------
# Memory File Browser
# ---------------------------------------------------------------------------


@app.get("/agents/{agent_id}/memory")
async def list_memory(agent_id: str, path: str = "") -> dict:
    """List memory files."""
    agent = _get_agent(agent_id)
    base = agent.path / "memory"
    target = (base / path).resolve()

    if not str(target).startswith(str(base.resolve())):
        raise HTTPException(status_code=403, detail="Path escapes memory dir")

    if not target.exists():
        return {"type": "dir", "path": path, "entries": []}

    if target.is_file():
        return {"type": "file", "path": path, "content": target.read_text(errors="replace")}

    entries = []
    for item in sorted(target.iterdir()):
        entries.append({
            "name": item.name,
            "type": "dir" if item.is_dir() else "file",
        })
    return {"type": "dir", "path": path, "entries": entries}


# ---------------------------------------------------------------------------
# Events (WebSocket + Polling)
# ---------------------------------------------------------------------------


@app.websocket("/agents/{agent_id}/events")
async def event_stream(websocket: WebSocket, agent_id: str):
    """WebSocket stream of agent events."""
    await websocket.accept()
    agent = _get_agent_safe(agent_id)
    if not agent:
        await websocket.close(code=4004, reason="Agent not found")
        return

    queue = agent.event_bus.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event.to_dict())
    except WebSocketDisconnect:
        pass
    finally:
        agent.event_bus.unsubscribe(queue)


@app.get("/agents/{agent_id}/events")
async def get_events(agent_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """Get recent events (polling fallback)."""
    agent = _get_agent(agent_id)
    events = agent.event_bus.recent(limit=limit, offset=offset)
    return [e.to_dict() for e in events]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_agent(agent_id: str) -> Agent:
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return agent


def _get_agent_safe(agent_id: str) -> Agent | None:
    return agent_registry.get(agent_id)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------


def main():
    """Start the Agiraph server."""
    print(f"Starting Agiraph v2 server on {SERVER_HOST}:{SERVER_PORT}")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")


if __name__ == "__main__":
    main()
