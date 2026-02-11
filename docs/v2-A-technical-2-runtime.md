# Agiraph v2-A — Technical Design: Part 2 — Runtime

**Part 2 of 4** | [Part 1: Core Concepts](./v2-A-technical-1-core.md) | [Part 3: Memory & Human](./v2-A-technical-3-memory-human.md) | [Part 4: Implementation](./v2-A-technical-4-implementation.md)
**Date:** 2026-02-11

_Covers: Collaboration system, built-in tools, provider adapter layer, scheduler._

---
## 3. Collaboration System

### 3.1 Coordinator

The top-level agent IS the coordinator. When it receives a big goal, it plans the work:

```python
class Coordinator:
    """The agent's brain. Runs as a harnessed worker with special tools."""

    tools = [
        create_work_node,      # add a node to the work board
        assign_worker,         # assign a worker to a node
        spawn_worker,          # create a new worker
        send_message,          # message a role/worker
        check_messages,        # read incoming messages
        read_workspace,        # read any workspace file
        write_workspace,       # write to workspace root
        check_board,           # see all nodes and their status
        reconvene,             # end current stage, assess, re-plan
        ask_human,             # ask the human a question
        finish,                # goal achieved, we're done
    ]
```

### 3.2 Stages and Reconvene

Same model as v2 design. Work happens in stages:

1. Coordinator creates work nodes for the current stage
2. Scheduler assigns workers to nodes (or coordinator does it explicitly)
3. Workers execute in parallel
4. When all nodes in a stage complete → coordinator reconvenes
5. Coordinator reads all outputs, decides next stage (or finishes)

```python
class Stage:
    name: str
    nodes: list[str]          # work node IDs in this stage
    status: str               # planning | running | reconvening | completed
    contract: StageContract

@dataclass
class StageContract:
    max_iterations_per_node: int = 10
    timeout_seconds: int = 300
    checkpoint_policy: str = "all_must_complete"  # or "majority" or "any"
```

### 3.3 Recursive Spawning

Any worker (harnessed, running in multi-turn mode) can spawn sub-work-nodes:

```python
def tool_create_work_node(context: ToolContext, task: str, role: str = "worker") -> dict:
    """Create a new work node on the board. It will be assigned to a worker."""
    node = WorkNode(
        id=generate_id(),
        task=task,
        parent_node=context.current_node.id,
        dependencies=[],
        status="pending"
    )
    context.board.add(node)
    context.current_node.children.append(node.id)
    return {"node_id": node.id, "status": "created"}
```

The spawning node can then block until children complete, or continue working.

### 3.4 Messaging

Workers can message each other by name/role:

```python
class MessageBus:
    def send(self, from_id: str, to_id: str, content: str):
        msg = Message(from_id=from_id, to_id=to_id, content=content, ts=time.time())
        with self._lock:
            self._queues[to_id].append(msg)
            self._log(msg)

    def receive(self, worker_id: str) -> list[Message]:
        with self._lock:
            return self._queues.pop(worker_id, [])
```

Messages are injected into the worker's next turn as system messages.

---

## 4. Built-in Tools

### 4.1 Core Tools (Available to All Workers)

```python
CORE_TOOLS = {
    # --- Work Management ---
    "publish": {
        "description": "Finalize your work on this node. Moves scratch/ → published/, "
                       "marks node complete. Other nodes can now reference your outputs.",
        "params": {"summary": "str — what you produced"},
    },
    "checkpoint": {
        "description": "Signal that you've completed this stage of work. Include a summary.",
        "params": {"summary": "str"},
    },
    "create_work_node": {
        "description": "Create a sub-task on the work board. It will be picked up by a worker.",
        "params": {"task": "str", "refs": "dict (optional) — pointers to other nodes' published data"},
    },

    # --- Communication ---
    "send_message": {
        "description": "Send a message to another worker or the coordinator by name.",
        "params": {"to": "str — recipient name", "content": "str"},
    },
    "check_messages": {
        "description": "Check for new messages from other workers or the coordinator.",
        "params": {},
    },
    "ask_human": {
        "description": "Ask the human a question. Your work pauses until they respond. "
                       "Use sparingly — only when you truly need guidance.",
        "params": {
            "question": "str",
            "channel": "str (optional) — cli | webhook | email (default: cli)",
        },
    },

    # --- File I/O (scoped) ---
    "read_file": {
        "description": "Read a file. You can read: your node's scratch/ and _spec.md, "
                       "any node's published/ directory, your own worker files, "
                       "the run's _plan.md.",
        "params": {"path": "str — relative to the run root (runs/{run_id}/)"},
    },
    "write_file": {
        "description": "Write a file. You can write to: your node's scratch/ directory, "
                       "your own worker files (notebook.md, memory.md).",
        "params": {"path": "str", "content": "str"},
    },
    "list_files": {
        "description": "List files in a directory.",
        "params": {"path": "str — relative to the run root"},
    },
    "read_ref": {
        "description": "Read a referenced upstream node's published output by ref name.",
        "params": {"ref_name": "str — key from _refs.json"},
    },

    # --- Execution ---
    "bash": {
        "description": "Execute a shell command. Use for running code, installing packages, "
                       "git operations, or any CLI task.",
        "params": {
            "command": "str",
            "timeout": "int (optional, seconds, default 120)",
        },
    },

    # --- Research ---
    "web_search": {
        "description": "Search the web. Returns a list of results with titles, URLs, and snippets.",
        "params": {"query": "str"},
    },
    "web_fetch": {
        "description": "Fetch a webpage and return its content as markdown.",
        "params": {"url": "str"},
    },

    # --- Memory ---
    "memory_write": {
        "description": "Write to your long-term memory. Survives across sessions.",
        "params": {"path": "str — relative to memory/", "content": "str"},
    },
    "memory_read": {
        "description": "Read from your long-term memory.",
        "params": {"path": "str — relative to memory/"},
    },
    "memory_search": {
        "description": "Search your memory for relevant notes. Semantic search.",
        "params": {"query": "str"},
    },

    # --- Scheduling ---
    "schedule": {
        "description": "Schedule a future action. Use this to set reminders, "
                       "recurring tasks, delayed follow-ups, or timed alarms.",
        "params": {
            "type": "str — delayed | at_time | scheduled | heartbeat",
            "config": "dict — {delay_seconds} | {at: ISO8601} | {cron: str} | {interval_seconds}",
            "action": "str — task description for when the trigger fires",
        },
    },
    "list_triggers": {
        "description": "List all your active scheduled triggers.",
        "params": {},
    },
    "cancel_trigger": {
        "description": "Cancel a scheduled trigger.",
        "params": {"trigger_id": "str"},
    },

    # --- Suggestions ---
    "suggest_next": {
        "description": "Suggest a follow-up work node to the coordinator. "
                       "Use when you discover something that needs further work "
                       "beyond your current spec. The coordinator decides whether to act on it.",
        "params": {
            "suggestion": "str — what work should be done and why",
        },
    },
}
```

### 4.2 Coordinator-Only Tools

```python
COORDINATOR_TOOLS = {
    "assign_worker": {
        "description": "Assign a specific worker to a work node.",
        "params": {"node_id": "str", "worker_id": "str"},
    },
    "spawn_worker": {
        "description": "Create a new worker. Can be harnessed (API) or autonomous (external agent).",
        "params": {
            "name": "str",
            "type": "str — harnessed | autonomous",
            "model": "str (optional) — e.g. anthropic/claude-sonnet-4-5",
            "agent_command": "str (optional) — for autonomous workers",
            "tools": "list[str] (optional) — tool names to enable",
            "memory": "dict (optional) — prepared context for the worker",
        },
    },
    "check_board": {
        "description": "View all work nodes and their current status.",
        "params": {},
    },
    "reconvene": {
        "description": "End the current stage. Read outputs and plan next stage.",
        "params": {"assessment": "str — your analysis of current progress"},
    },
}
```

### 4.3 Tool Implementation Sketch

```python
def impl_bash(context: ToolContext, command: str, timeout: int = 120) -> str:
    """Execute shell command with timeout. Cwd is the worker's workspace dir."""
    try:
        result = subprocess.run(
            command, shell=True,
            capture_output=True, text=True,
            timeout=timeout,
            cwd=context.workspace_dir
        )
        output = result.stdout + result.stderr
        return output[:10000]  # truncate large output
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"

def impl_ask_human(context: ToolContext, question: str, channel: str = "cli") -> str:
    """Pause and surface question to human. Block until response."""
    context.worker.status = "waiting_for_human"
    event = HumanQuestionEvent(
        agent_id=context.agent.id,
        worker_id=context.worker.id,
        question=question,
        channel=channel,
        ts=time.time()
    )
    context.event_bus.emit(event)
    # Block until human responds (or timeout)
    response = context.human_response_queue.get(timeout=context.human_timeout)
    context.worker.status = "busy"
    return response

def impl_web_search(context: ToolContext, query: str) -> str:
    """Web search via configured provider (Brave, Serper, etc.)."""
    results = context.search_provider.search(query, max_results=5)
    formatted = []
    for r in results:
        formatted.append(f"**{r.title}**\n{r.url}\n{r.snippet}\n")
    return "\n---\n".join(formatted)

def impl_web_fetch(context: ToolContext, url: str) -> str:
    """Fetch URL and convert to markdown."""
    html = httpx.get(url, timeout=30).text
    markdown = html_to_markdown(html)
    return markdown[:15000]  # truncate
```

---

## 5. Provider Adapter Layer

### 5.1 Two Layers: Schema vs Guidance

Tool handling has two distinct layers that must be separated:

**Layer 1: Tool Schema (per-provider, structured)**
The formal definition of each tool — name, parameters, types. This is what the model uses to know which tools exist and how to call them. Format varies by provider.

**Layer 2: Tool Guidance (universal, in the prompt)**
The "how to use this tool well" runbook — when to use it, tips, patterns, common mistakes. This is always natural language text in the system prompt. Same for all providers.

```
┌──────────────────────────────────────────────────────────┐
│  SYSTEM PROMPT                                            │
│                                                           │
│  [Identity + Goal + Memory + Operating Rules]             │
│                                                           │
│  [Tool Guidance]  ← universal, always text               │
│  "bash: Run shell commands. Tips: check output, set       │
│   timeouts, chain with &&..."                             │
│  "web_search: Search the web. Tips: be specific..."       │
│                                                           │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│  TOOL SCHEMAS (passed via API, format varies)            │
│                                                           │
│  Anthropic: {"name": "bash", "input_schema": {...}}      │
│  OpenAI:    {"type": "function", "function": {...}}      │
│  Gemini:    {"function_declarations": [{...}]}           │
│  Text mode: injected into prompt as structured text      │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### 5.2 Canonical Tool Definition

We define tools once in a canonical format. Adapters translate it.

```python
@dataclass
class ToolDef:
    name: str
    description: str                    # short, for the schema
    parameters: dict                    # JSON Schema
    guidance: str                       # long, for the prompt (tips, patterns, when to use)

# Example
BASH_TOOL = ToolDef(
    name="bash",
    description="Execute a shell command.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to run"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 120},
        },
        "required": ["command"],
    },
    guidance="""
Run shell commands. Use for: running code, installing packages, git operations, CLI tools.

Tips:
- Always check command output. Don't assume success.
- Set reasonable timeouts for long-running commands.
- If a command fails, READ the error. Fix the issue. Don't retry the same command.
- Chain with && so later steps don't run if earlier ones fail.
- Don't run destructive commands (rm -rf) without thinking twice.
""",
)
```

### 5.3 Provider Adapter

Each adapter handles three things:

```python
class ProviderAdapter(ABC):
    @abstractmethod
    def format_tools(self, tools: list[ToolDef]) -> Any:
        """Convert canonical tool defs to provider's API format.
        For native tool-calling models: returns structured schema.
        For text-fallback models: returns None (tools go in prompt instead)."""
        pass

    @abstractmethod
    def format_tool_prompt(self, tools: list[ToolDef]) -> str:
        """Generate the tool guidance text for the system prompt.
        For native models: just the guidance (tips, patterns).
        For text models: guidance + full schema + call format instructions."""
        pass

    @abstractmethod
    def parse_response(self, raw_response: Any) -> ModelResponse:
        """Extract text and tool calls from provider response.
        For native models: parse structured tool_call objects.
        For text models: parse <tool_call> tags from text output."""
        pass
```

### 5.4 Native Tool-Calling Adapters

**Anthropic (Claude):**
```python
class AnthropicAdapter(ProviderAdapter):
    def format_tools(self, tools: list[ToolDef]) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    def format_tool_prompt(self, tools: list[ToolDef]) -> str:
        # Native tool calling: only include guidance, not schema
        # (schema goes via API, guidance goes in prompt)
        lines = ["## Tool Usage Guide\n"]
        for t in tools:
            lines.append(f"### {t.name}\n{t.guidance}\n")
        return "\n".join(lines)

    def parse_response(self, raw) -> ModelResponse:
        tool_calls = []
        text_parts = []
        for block in raw.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(
                    name=block.name,
                    args=block.input,
                    id=block.id,
                ))
            elif block.type == "text":
                text_parts.append(block.text)
        return ModelResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            usage=TokenUsage(raw.usage.input_tokens, raw.usage.output_tokens),
        )
```

**OpenAI (GPT-4, o3):**
```python
class OpenAIAdapter(ProviderAdapter):
    def format_tools(self, tools: list[ToolDef]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def format_tool_prompt(self, tools: list[ToolDef]) -> str:
        # Same as Anthropic: guidance only
        lines = ["## Tool Usage Guide\n"]
        for t in tools:
            lines.append(f"### {t.name}\n{t.guidance}\n")
        return "\n".join(lines)

    def parse_response(self, raw) -> ModelResponse:
        msg = raw.choices[0].message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    args=json.loads(tc.function.arguments),
                    id=tc.id,
                ))
        return ModelResponse(
            text=msg.content,
            tool_calls=tool_calls,
            usage=TokenUsage(raw.usage.prompt_tokens, raw.usage.completion_tokens),
        )
```

### 5.5 Text Fallback Adapter

For models without native tool calling. Tools go entirely in the prompt. Responses are parsed from text markers.

```python
class TextFallbackAdapter(ProviderAdapter):
    def format_tools(self, tools: list[ToolDef]) -> None:
        # No structured tools — everything goes in the prompt
        return None

    def format_tool_prompt(self, tools: list[ToolDef]) -> str:
        # Full schema + guidance + call format instructions
        lines = ["## Available Tools\n"]
        lines.append("To call a tool, output EXACTLY this format:")
        lines.append("```")
        lines.append('<tool_call>{"name": "tool_name", "arguments": {"key": "value"}}</tool_call>')
        lines.append("```\n")
        lines.append("You can make multiple tool calls in one response.\n")

        for t in tools:
            lines.append(f"### {t.name}")
            lines.append(f"**Description:** {t.description}")
            lines.append(f"**Parameters:** ```json\n{json.dumps(t.parameters, indent=2)}\n```")
            lines.append(f"\n{t.guidance}\n")

        return "\n".join(lines)

    def parse_response(self, raw) -> ModelResponse:
        text = raw  # raw text output
        tool_calls = []
        # Parse <tool_call>...</tool_call> tags
        for match in re.finditer(r'<tool_call>(.*?)</tool_call>', text, re.DOTALL):
            try:
                parsed = json.loads(match.group(1))
                tool_calls.append(ToolCall(
                    name=parsed["name"],
                    args=parsed.get("arguments", {}),
                    id=f"tc_{uuid4().hex[:8]}",
                ))
            except (json.JSONDecodeError, KeyError):
                pass  # malformed tool call, skip
        # Remove tool_call tags from display text
        clean_text = re.sub(r'<tool_call>.*?</tool_call>', '', text, flags=re.DOTALL).strip()
        return ModelResponse(
            text=clean_text or None,
            tool_calls=tool_calls,
            usage=TokenUsage(0, 0),  # no usage data from text-only models
        )
```

### 5.6 Unified Interface

The worker loop doesn't care which adapter is in use:

```python
class ModelProvider:
    def __init__(self, model: str):
        self.client = create_client(model)           # API client
        self.adapter = get_adapter(model)             # picks the right adapter

    async def generate(
        self,
        messages: list[dict],
        tools: list[ToolDef] | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        # 1. Format tools for this provider
        api_tools = self.adapter.format_tools(tools) if tools else None

        # 2. Build system prompt with tool guidance
        if tools and system:
            tool_prompt = self.adapter.format_tool_prompt(tools)
            system = system + "\n\n" + tool_prompt

        # 3. Call the model
        raw = await self.client.call(
            messages=messages,
            tools=api_tools,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # 4. Parse response into unified format
        return self.adapter.parse_response(raw)
```

### 5.7 Provider Summary

| Provider | Tool schema | Tool guidance | Response parsing |
|---|---|---|---|
| Anthropic (Claude) | via API (`input_schema`) | in prompt (guidance only) | parse `content[].tool_use` |
| OpenAI (GPT-4, o3) | via API (`function`) | in prompt (guidance only) | parse `tool_calls[]` |
| Google (Gemini) | via API (`function_declarations`) | in prompt (guidance only) | parse `function_call` parts |
| OpenRouter | via API (OpenAI format) | in prompt (guidance only) | parse OpenAI format |
| Text fallback | in prompt (full schema) | in prompt (schema + guidance) | parse `<tool_call>` tags |

**Key insight:** The tool **guidance** (the runbook from v2-A-prompts.md) is always text in the system prompt, regardless of provider. The tool **schema** (the formal definition) goes via API for native models or into the prompt for text-fallback models. The guidance is what teaches the model to use tools _well_. The schema is what teaches it to use tools _correctly_.

---

## 6. Scheduler

The scheduler manages the work board and assigns nodes to workers.

```python
class Scheduler:
    def __init__(self, board: WorkBoard, workers: dict[str, Worker]):
        self.board = board
        self.workers = workers

    def tick(self):
        """Called periodically. Assigns ready nodes to idle workers."""
        ready_nodes = [n for n in self.board.nodes
                       if n.status == "pending"
                       and all(self.board.get(d).status == "completed"
                               for d in n.dependencies)]

        idle_workers = [w for w in self.workers.values()
                        if w.status == "idle"]

        for node, worker in zip(ready_nodes, idle_workers):
            self.assign(node, worker)

    def assign(self, node: WorkNode, worker: Worker):
        node.status = "assigned"
        node.assigned_worker = worker.id
        worker.status = "busy"
        # Launch execution in thread/task
        asyncio.create_task(self.execute(node, worker))

    async def execute(self, node: WorkNode, worker: Worker):
        try:
            node.status = "running"
            result = await worker.execute(node)
            node.status = "completed"
            node.result = result
        except Exception as e:
            node.status = "failed"
            node.result = str(e)
        finally:
            worker.status = "idle"
            self.tick()  # check if new nodes are ready
```

---
