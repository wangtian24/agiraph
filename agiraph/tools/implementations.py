"""Tool implementations — the actual logic behind each tool."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from agiraph.config import BRAVE_API_KEY, MAX_MEMORY_INLINE, SERPER_API_KEY, SEARCH_PROVIDER
from agiraph.models import Message, Trigger, TriggerAction, WorkNode, Worker, generate_id

if TYPE_CHECKING:
    from agiraph.tools.context import ToolContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Work Management
# ---------------------------------------------------------------------------


async def impl_publish(context: ToolContext, summary: str) -> str:
    """Move scratch/ to published/. Finalize the node."""
    node = context.node
    if not node or not node.data_dir:
        return "Error: No active node to publish."

    scratch = node.data_dir / "scratch"
    published = node.data_dir / "published"
    published.mkdir(parents=True, exist_ok=True)

    if scratch.exists():
        for f in scratch.iterdir():
            dest = published / f.name
            if f.is_dir():
                shutil.copytree(f, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(f, dest)

    # Write status
    (node.data_dir / "_status.md").write_text(f"COMPLETED\n\n{summary}")
    node.status = "completed"
    node.result = summary

    # Update worker memory
    if context.worker and context.worker.worker_dir:
        mem_file = context.worker.worker_dir / "memory.md"
        mem_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mem_file, "a") as f:
            f.write(f"\n## Node: {node.id}\n{summary}\n")

    # Mark worker idle
    if context.worker:
        context.worker.status = "idle"

    # Emit event
    context.emit("node.completed", node_id=node.id, summary=summary)
    return f"Published. Node '{node.id}' complete."


async def impl_checkpoint(context: ToolContext, summary: str) -> str:
    """Signal stage completion."""
    if context.node:
        status_file = context.node.data_dir / "_status.md"
        status_file.write_text(f"CHECKPOINT\n\n{summary}")
    context.emit("node.checkpoint", node_id=context.node.id if context.node else "", summary=summary)
    return f"Checkpoint recorded: {summary}"


async def impl_create_work_node(context: ToolContext, task: str, deps: list[str] | None = None, refs: dict | None = None) -> str:
    """Create a new work node on the board."""
    node = WorkNode(
        id=generate_id(),
        task=task,
        dependencies=deps or [],
        refs=refs or {},
        parent_node=context.node.id if context.node else None,
    )

    # Create node directory
    run_dir = context.run_dir
    if run_dir:
        node.data_dir = run_dir / "nodes" / node.id
        node.data_dir.mkdir(parents=True, exist_ok=True)
        (node.data_dir / "scratch").mkdir(exist_ok=True)
        (node.data_dir / "published").mkdir(exist_ok=True)
        (node.data_dir / "_spec.md").write_text(task)
        if refs:
            (node.data_dir / "_refs.json").write_text(json.dumps(refs, indent=2))

    context.board.add(node)
    if context.node:
        context.node.children.append(node.id)

    context.emit("node.created", node_id=node.id, task=task[:100])
    return json.dumps({"node_id": node.id, "status": "created"})


async def impl_suggest_next(context: ToolContext, suggestion: str) -> str:
    """Suggest a follow-up node to the coordinator."""
    context.message_bus.send(
        from_id=context.worker.name if context.worker else "unknown",
        to_id="coordinator",
        content=f"[SUGGESTION] {suggestion}",
    )
    return "Suggestion sent to coordinator."


# ---------------------------------------------------------------------------
# Communication
# ---------------------------------------------------------------------------


async def impl_send_message(context: ToolContext, to: str, content: str) -> str:
    """Send a message to another entity."""
    from_id = context.worker.name if context.worker else "coordinator"
    context.message_bus.send(from_id=from_id, to_id=to, content=content)
    context.emit("message.sent", from_id=from_id, to_id=to, content=content[:200])
    return f"Message sent to {to}."


async def impl_check_messages(context: ToolContext) -> str:
    """Check inbox for new messages."""
    entity_id = context.worker.name if context.worker else "coordinator"
    messages = context.message_bus.receive(entity_id)
    if not messages:
        return "No new messages."
    parts = []
    for m in messages:
        parts.append(f"FROM {m.from_id}: {m.content}")
    return "\n---\n".join(parts)


async def impl_ask_human(context: ToolContext, question: str, channel: str = "cli") -> str:
    """Ask the human a question. Blocks until response."""
    if context.worker:
        context.worker.status = "waiting_for_human"

    context.emit("human.question", question=question, channel=channel,
                 worker_id=context.worker.id if context.worker else "coordinator")

    # Send to human's inbox
    from_id = context.worker.name if context.worker else "coordinator"
    context.message_bus.send(from_id=from_id, to_id="human", content=f"[QUESTION] {question}")

    # Block waiting for response
    try:
        response = await asyncio.wait_for(
            context.human_response_queue.get(),
            timeout=context.human_timeout,
        )
    except asyncio.TimeoutError:
        if context.worker:
            context.worker.status = "busy"
        return "Human did not respond within timeout. Proceeding with best judgment."

    if context.worker:
        context.worker.status = "busy"

    context.emit("human.response", response=response)
    return f"Human responded: {response}"


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


async def impl_read_file(context: ToolContext, path: str) -> str:
    """Read a file from the workspace."""
    full_path = context.resolve_path(path)
    if not full_path.exists():
        return f"Error: File not found: {path}"
    try:
        content = full_path.read_text()
        if len(content) > 50000:
            content = content[:50000] + "\n\n[... truncated ...]"
        return content
    except Exception as e:
        return f"Error reading {path}: {e}"


async def impl_write_file(context: ToolContext, path: str, content: str) -> str:
    """Write a file to the workspace."""
    full_path = context.resolve_path(path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    return f"Written {len(content)} chars to {path}"


async def impl_list_files(context: ToolContext, path: str) -> str:
    """List files in a directory."""
    full_path = context.resolve_path(path)
    if not full_path.exists():
        return f"Error: Directory not found: {path}"
    if not full_path.is_dir():
        return f"Error: Not a directory: {path}"

    entries = []
    for item in sorted(full_path.iterdir()):
        prefix = "📁 " if item.is_dir() else "📄 "
        entries.append(f"{prefix}{item.name}")
    return "\n".join(entries) if entries else "(empty directory)"


async def impl_read_ref(context: ToolContext, ref_name: str) -> str:
    """Read a referenced upstream node's output."""
    if not context.node or not context.node.data_dir:
        return "Error: No active node."

    refs_file = context.node.data_dir / "_refs.json"
    if not refs_file.exists():
        return "Error: No _refs.json found."

    refs = json.loads(refs_file.read_text())
    ref_path = refs.get(ref_name)
    if not ref_path:
        return f"Error: Ref '{ref_name}' not found. Available: {list(refs.keys())}"

    full_path = context.run_dir / ref_path
    if not full_path.exists():
        return f"Error: Referenced file not found: {ref_path}"

    content = full_path.read_text()
    if len(content) > 50000:
        content = content[:50000] + "\n\n[... truncated ...]"
    return content


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


async def impl_bash(context: ToolContext, command: str, timeout: int = 120) -> str:
    """Execute a shell command."""
    cwd = None
    if context.node and context.node.data_dir:
        cwd = str(context.node.data_dir / "scratch")
    elif context.run_dir:
        cwd = str(context.run_dir)

    context.emit("tool.called", tool="bash", command=command[:200])

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = (stdout.decode() + stderr.decode()).strip()
        if len(output) > 10000:
            output = output[:10000] + "\n\n[... truncated ...]"
        return output if output else "(no output)"
    except asyncio.TimeoutError:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------


async def impl_web_search(context: ToolContext, query: str) -> str:
    """Search the web using configured provider."""
    context.emit("tool.called", tool="web_search", query=query)

    try:
        if SEARCH_PROVIDER == "brave" and BRAVE_API_KEY:
            return await _brave_search(query)
        elif SEARCH_PROVIDER == "serper" and SERPER_API_KEY:
            return await _serper_search(query)
        else:
            return "Error: No search API configured. Set BRAVE_API_KEY or SERPER_API_KEY in .env"
    except Exception as e:
        return f"Search error: {e}"


async def _brave_search(query: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": 5},
            headers={"X-Subscription-Token": BRAVE_API_KEY, "Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    results = data.get("web", {}).get("results", [])
    if not results:
        return "No results found."

    formatted = []
    for r in results[:5]:
        formatted.append(f"**{r.get('title', 'No title')}**\n{r.get('url', '')}\n{r.get('description', '')}\n")
    return "\n---\n".join(formatted)


async def _serper_search(query: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": 5},
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    results = data.get("organic", [])
    if not results:
        return "No results found."

    formatted = []
    for r in results[:5]:
        formatted.append(f"**{r.get('title', 'No title')}**\n{r.get('link', '')}\n{r.get('snippet', '')}\n")
    return "\n---\n".join(formatted)


async def impl_web_fetch(context: ToolContext, url: str) -> str:
    """Fetch a webpage and convert to markdown."""
    context.emit("tool.called", tool="web_fetch", url=url)

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (compatible; Agiraph/2.0)"
            })
            resp.raise_for_status()
            html = resp.text

        # Convert HTML to markdown
        try:
            from markdownify import markdownify
            md = markdownify(html, heading_style="ATX", strip=["script", "style", "nav", "footer"])
        except ImportError:
            # Fallback: strip tags naively
            import re
            md = re.sub(r"<[^>]+>", "", html)

        md = md.strip()
        if len(md) > 15000:
            md = md[:15000] + "\n\n[... truncated ...]"
        return md if md else "(empty page)"
    except Exception as e:
        return f"Fetch error: {e}"


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


async def impl_memory_write(context: ToolContext, path: str, content: str) -> str:
    """Write to agent long-term memory."""
    memory_dir = context.agent_path / "memory"
    full_path = memory_dir / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    context.emit("memory.written", path=path)
    return f"Written to memory/{path}"


async def impl_memory_read(context: ToolContext, path: str) -> str:
    """Read from agent long-term memory."""
    memory_dir = context.agent_path / "memory"
    full_path = memory_dir / path
    if not full_path.exists():
        return f"Error: Memory file not found: memory/{path}"
    return full_path.read_text()


async def impl_memory_search(context: ToolContext, query: str) -> str:
    """Search memory files for relevant sections."""
    memory_dir = context.agent_path / "memory"
    if not memory_dir.exists():
        return "No memory files found."

    all_files = list(memory_dir.rglob("*.md"))
    if not all_files:
        return "No memory files found."

    total_size = sum(f.stat().st_size for f in all_files)

    # If small enough, return everything
    if total_size < MAX_MEMORY_INLINE:
        parts = []
        for f in all_files:
            rel = f.relative_to(memory_dir)
            parts.append(f"**{rel}**\n{f.read_text()}")
        return "\n\n---\n\n".join(parts)

    # Otherwise: grep for keywords, return matching sections
    keywords = query.lower().split()
    results = []
    for md_file in all_files:
        sections = _split_by_headers(md_file.read_text())
        for section in sections:
            if any(kw in section.lower() for kw in keywords):
                results.append((md_file.relative_to(memory_dir), section))

    if not results:
        return "No matching memory found."

    return "\n\n---\n\n".join(f"**{path}**\n{section}" for path, section in results[:10])


def _split_by_headers(text: str) -> list[str]:
    """Split markdown into sections at ## or ### headers."""
    sections = []
    current: list[str] = []
    for line in text.split("\n"):
        if line.startswith("## ") or line.startswith("### "):
            if current:
                sections.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current))
    return sections


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


async def impl_schedule(context: ToolContext, type: str, config: dict, action: str) -> str:
    """Schedule a future trigger."""
    trigger = Trigger(
        id=generate_id(),
        agent_id=context.agent_id,
        type=type,
        action=TriggerAction(type="wake_agent", payload={"task": action}),
        metadata=config,
    )
    context.trigger_store.append(trigger)
    context.emit("trigger.created", trigger_id=trigger.id, type=type)
    return json.dumps({"trigger_id": trigger.id, "type": type, "status": "active"})


async def impl_list_triggers(context: ToolContext) -> str:
    """List active triggers."""
    active = [t for t in context.trigger_store if t.status == "active"]
    if not active:
        return "No active triggers."
    parts = []
    for t in active:
        parts.append(f"- {t.id}: {t.type} | {t.action.payload.get('task', '')[:60]}")
    return "\n".join(parts)


async def impl_cancel_trigger(context: ToolContext, trigger_id: str) -> str:
    """Cancel a trigger."""
    for t in context.trigger_store:
        if t.id == trigger_id:
            t.status = "expired"
            return f"Trigger {trigger_id} cancelled."
    return f"Error: Trigger {trigger_id} not found."


# ---------------------------------------------------------------------------
# Coordinator-Only
# ---------------------------------------------------------------------------


async def impl_spawn_worker(context: ToolContext, name: str, role: str, type: str = "harnessed",
                            model: str | None = None, max_iterations: int = 20) -> str:
    """Spawn a new worker."""
    worker = Worker(
        id=generate_id(),
        name=name,
        type=type,
        model=model or context.default_model,
        max_iterations=max_iterations,
    )

    # Create worker directory
    if context.run_dir:
        worker.worker_dir = context.run_dir / "workers" / worker.id
        worker.worker_dir.mkdir(parents=True, exist_ok=True)
        (worker.worker_dir / "identity.md").write_text(f"# {name}\n\n{role}\n")
        (worker.worker_dir / "memory.md").write_text("")
        (worker.worker_dir / "notebook.md").write_text("")
        (worker.worker_dir / "history.json").write_text("[]")

    context.worker_pool.add(worker)
    context.message_bus.register(name)
    context.emit("worker.spawned", worker_id=worker.id, name=name, role=role)
    return json.dumps({"worker_id": worker.id, "name": name, "status": "idle"})


async def impl_assign_worker(context: ToolContext, node_id: str, worker_id: str) -> str:
    """Assign a worker to a node."""
    node = context.board.get(node_id)
    if not node:
        return f"Error: Node {node_id} not found."
    worker = context.worker_pool.get(worker_id)
    if not worker:
        return f"Error: Worker {worker_id} not found."

    node.assigned_worker = worker.id
    node.status = "assigned"
    worker.status = "busy"
    context.emit("node.assigned", node_id=node_id, worker_id=worker_id, worker_name=worker.name)
    return f"Assigned {worker.name} to node {node_id}."


async def impl_check_board(context: ToolContext) -> str:
    """Show all nodes and their status."""
    if not context.board.nodes:
        return "Work board is empty."
    lines = []
    for n in context.board.nodes.values():
        worker_info = f" (→ {n.assigned_worker})" if n.assigned_worker else ""
        result_preview = f" | Result: {n.result[:80]}..." if n.result else ""
        lines.append(f"- [{n.status.upper()}] {n.id}: {n.task[:80]}{worker_info}{result_preview}")
    return "\n".join(lines)


async def impl_reconvene(context: ToolContext, assessment: str) -> str:
    """End current stage, allow coordinator to plan next steps."""
    context.emit("stage.reconvened", assessment=assessment[:200])

    # Gather all node outputs
    completed = [n for n in context.board.nodes.values() if n.status == "completed"]
    outputs = []
    for n in completed:
        published_dir = n.data_dir / "published" if n.data_dir else None
        files_info = ""
        if published_dir and published_dir.exists():
            files = list(published_dir.iterdir())
            files_info = f" | Files: {[f.name for f in files]}"
        outputs.append(f"- {n.id}: {n.result or '(no result)'}{files_info}")

    return f"Stage reconvened.\n\nAssessment: {assessment}\n\nCompleted nodes:\n" + "\n".join(outputs)


async def impl_finish(context: ToolContext, summary: str) -> str:
    """Goal achieved — stop the agent."""
    context.emit("agent.completed", summary=summary)
    return f"AGENT_FINISHED: {summary}"
