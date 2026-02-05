# Agiraph v2 — Design Document

**Status:** Draft  
**Author:** Tsuki + Tian  
**Date:** 2026-02-05  
**Version:** 2.0.0-alpha

---

## 1. Overview

Agiraph v2 is a **model-agnostic agent orchestration runtime** that supports both traditional DAG-based workflows and autonomous multi-agent collaboration. Unlike v1's static planning approach, v2 treats the execution graph as a **living structure** that can grow dynamically as agents decide to spawn new tasks, delegate work, or coordinate through messaging.

### Key Goals

1. **Hybrid Planning:** Support both upfront DAG generation (like v1) AND dynamic on-the-fly task creation
2. **Autonomous Nodes:** Each node is a self-contained agent with its own ReAct loop, not just a single inference
3. **Inter-Agent Communication:** Nodes can send messages to each other, enabling coordination beyond the DAG structure
4. **Model Agnostic:** Works with any LLM provider (OpenAI, Anthropic, Google, local models)
5. **Tool Integration:** Native MCP (Model Context Protocol) support for tool use
6. **Error Resilience:** Each node's execution loop captures and handles errors

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Agiraph Runtime                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │   Planner    │───▶│  Scheduler   │                  │
│  │  (optional)  │    │              │                  │
│  └──────────────┘    └──────┬───────┘                  │
│                              │                           │
│                              ▼                           │
│                     ┌─────────────────┐                 │
│                     │   Executor      │                 │
│                     │   (Thread Pool) │                 │
│                     └────────┬────────┘                 │
│                              │                           │
│              ┌───────────────┼───────────────┐          │
│              ▼               ▼               ▼          │
│         ┌─────────┐    ┌─────────┐    ┌─────────┐     │
│         │ Node A  │    │ Node B  │    │ Node C  │     │
│         │ (Agent) │    │ (Agent) │    │ (Agent) │     │
│         └────┬────┘    └────┬────┘    └────┬────┘     │
│              │              │              │            │
│              └──────────────┼──────────────┘            │
│                             ▼                            │
│                    ┌──────────────────┐                 │
│                    │   Message Bus    │                 │
│                    └──────────────────┘                 │
│                             ▲                            │
│                             │                            │
│                    ┌────────┴─────────┐                 │
│                    │  Shared Context  │                 │
│                    │   (Team Memory)  │                 │
│                    └──────────────────┘                 │
│                                                          │
└─────────────────────────────────────────────────────────┘
           │                           │
           ▼                           ▼
   ┌──────────────┐          ┌─────────────────┐
   │ Model Layer  │          │  MCP Servers    │
   │ (Any Provider│          │  (Tool Layer)   │
   └──────────────┘          └─────────────────┘
```

---

## 3. Core Components

### 3.1 Node (Agent)

A **Node** is an autonomous agent that executes a task through a self-contained ReAct loop.

**Properties:**
- `id`: Unique identifier
- `role`: `"manager"` | `"worker"` (determines prompt framing)
- `task`: The high-level goal (user-facing description)
- `state`: `"pending"` | `"running"` | `"blocked"` | `"completed"` | `"failed"`
- `dependencies`: List of node IDs that must complete before this runs
- `children`: List of node IDs spawned by this node
- `max_iterations`: Max ReAct loop cycles (default: 10)

**Execution Lifecycle:**
```python
while not done and iterations < max_iterations:
    1. Check message queue
    2. Think (generate next action plan)
    3. Act (call tool: spawn_agent | send_message | read_context | finish)
    4. Observe (receive tool result)
    5. Decide (continue or finish?)
```

**Built-in Tools:**
- `spawn_agent(task: str, role: str) -> agent_id`
- `send_message(to: agent_id, content: str)`
- `check_messages() -> List[Message]`
- `read_context(key: str) -> Any`
- `write_context(key: str, value: Any)`
- `finish(result: str)`

**MCP Tools:** (Optional) If MCP servers are configured, nodes also have access to external tools like filesystem, web browser, database, etc.

---

### 3.2 Scheduler

The **Scheduler** determines which nodes can run based on the current graph state.

**Responsibilities:**
1. Identify "ready" nodes (dependencies met, state=pending)
2. Submit ready nodes to Executor
3. Handle node state transitions
4. Detect deadlocks (circular dependencies)

**Dynamic Graph Updates:**
- When a node calls `spawn_agent()`, the Scheduler injects new nodes into the graph
- New nodes are linked to the spawning node as children
- Spawning node is marked `blocked` until children complete

---

### 3.3 Executor

The **Executor** runs nodes in parallel using a thread pool.

**Responsibilities:**
1. Execute node's ReAct loop
2. Handle tool calls (spawn, message, context, MCP)
3. Catch and log errors (bubble up to node state: `failed`)
4. Stream execution logs to UI

**Concurrency Model:**
- Max concurrent nodes: Configurable (default: 4)
- Each node runs in its own thread
- Thread-safe access to MessageBus and SharedContext

---

### 3.4 Message Bus

The **Message Bus** is a centralized queue for inter-node communication.

**API:**
```python
class MessageBus:
    def send(from_id: str, to_id: str, content: str)
    def receive(node_id: str) -> List[Message]
    def broadcast(from_id: str, content: str)  # Send to all nodes
```

**Message Structure:**
```python
@dataclass
class Message:
    from_id: str
    to_id: str
    content: str
    timestamp: float
```

**Delivery:**
- Messages are injected into the target node's next ReAct turn
- Format: `System: [Message from {sender_id}] {content}`

---

### 3.5 Shared Context (Team Memory)

A **key-value store** accessible to all nodes for sharing state.

**API:**
```python
class SharedContext:
    def read(key: str) -> Any
    def write(key: str, value: Any)
    def append(key: str, item: Any)  # For lists
    def keys() -> List[str]
```

**Use Cases:**
- Manager writes `task_status` that workers read
- Workers write findings that manager synthesizes
- Nodes coordinate through shared "plan" document

**Thread Safety:** All operations are atomic (mutex-protected).

---

## 4. Planning Modes

Agiraph v2 supports **two planning paradigms**, chosen at runtime.

### 4.1 Static Planning (v1 Compatibility)

**Flow:**
1. User provides high-level task
2. **Planner Agent** generates a complete DAG (JSON)
3. Runtime loads the DAG and executes nodes

**Pros:**
- Predictable execution
- Easy to visualize upfront
- Deterministic for testing

**Cons:**
- Brittle (can't adapt to unexpected results)
- Planner must hallucinate all steps

**Example DAG:**
```json
{
  "nodes": [
    {"id": "n1", "task": "Research Company A", "role": "worker"},
    {"id": "n2", "task": "Research Company B", "role": "worker"},
    {"id": "n3", "task": "Synthesize findings", "role": "manager", "deps": ["n1", "n2"]}
  ]
}
```

---

### 4.2 Dynamic Planning (Autonomous)

**Flow:**
1. User provides high-level task
2. Runtime creates a single **root manager node**
3. Manager decides to spawn workers using `spawn_agent()` tool
4. Graph grows as nodes spawn children

**Pros:**
- Adaptive (nodes react to results)
- No upfront hallucination
- Handles unknown-unknowns

**Cons:**
- Harder to visualize (graph emerges over time)
- Non-deterministic

**Example Execution:**
```
[Root Manager]
  ├─ spawn_agent("Research Company A") → Worker1
  ├─ spawn_agent("Research Company B") → Worker2
  └─ [waits for Worker1, Worker2]

[Worker1]
  ├─ spawn_agent("Analyze financials") → SubWorker1a
  └─ finish("Found revenue: $10M")

[Worker2]
  └─ finish("Company B acquired last year")

[Root Manager]
  └─ finish("Summary: ...")
```

---

### 4.3 Hybrid Planning

Combine both modes:
- Start with a **skeleton DAG** (high-level phases)
- Each phase is a manager node that spawns dynamic sub-agents

**Example:**
```json
{
  "nodes": [
    {"id": "research", "task": "Research phase", "role": "manager"},
    {"id": "analysis", "task": "Analysis phase", "role": "manager", "deps": ["research"]},
    {"id": "report", "task": "Write report", "role": "worker", "deps": ["analysis"]}
  ]
}
```

Each manager node internally uses `spawn_agent()` to create workers.

---

## 5. Node Execution Model (ReAct Loop)

Each node runs its own **multi-turn reasoning loop**, inspired by Clawdbot's architecture.

### 5.1 Execution Flow

```python
def execute_node(node: Node, context: SharedContext, bus: MessageBus):
    iteration = 0
    messages = []  # Conversation history
    
    while iteration < node.max_iterations:
        # Step 1: Check for incoming messages
        new_messages = bus.receive(node.id)
        if new_messages:
            for msg in new_messages:
                messages.append({
                    "role": "system",
                    "content": f"[Message from {msg.from_id}] {msg.content}"
                })
        
        # Step 2: Think (LLM inference)
        response = model.generate(
            messages=messages,
            tools=[spawn_agent, send_message, read_context, write_context, finish],
            system_prompt=build_node_prompt(node)
        )
        
        # Step 3: Act (tool call)
        if response.tool_calls:
            for tool_call in response.tool_calls:
                result = execute_tool(tool_call, node, context, bus)
                
                if tool_call.name == "finish":
                    return result
                elif tool_call.name == "spawn_agent":
                    # Runtime injects new node into graph
                    scheduler.add_node(result)
                    node.state = "blocked"  # Wait for children
                    return "BLOCKED"
                
                messages.append({
                    "role": "tool",
                    "content": str(result)
                })
        
        # Step 4: Observe (wait for next iteration)
        iteration += 1
    
    # Max iterations reached
    raise MaxIterationsError()
```

### 5.2 System Prompt Template

```
You are a {role} agent in a multi-agent system.

TASK: {task}

AVAILABLE TOOLS:
- spawn_agent(task, role): Create a new agent to handle a subtask
- send_message(to, content): Send a message to another agent
- check_messages(): Check for messages from other agents
- read_context(key): Read from shared team memory
- write_context(key, value): Write to shared team memory
- finish(result): Mark your task as complete

TEAM CONTEXT KEYS: {context.keys()}

EXECUTION RULES:
1. You run in a loop: think → act → observe
2. Use tools to coordinate with other agents
3. Call finish() when your task is done
4. Max iterations: {max_iterations}

Begin.
```

---

## 6. Inter-Node Communication

### 6.1 Messaging Protocol

Nodes communicate via the **MessageBus**. The protocol is **not predefined** — nodes negotiate it themselves.

**Example Coordination:**

**Manager → Worker:**
```
Manager: send_message("worker_1", "Research Company X. Focus on financials.")
Worker1: [receives message]
Worker1: send_message("manager", "Found revenue: $10M, profit margin: 15%")
```

**Worker ↔ Worker:**
```
Worker1: send_message("worker_2", "I'm analyzing the tech stack. Can you handle market research?")
Worker2: send_message("worker_1", "Sure, starting on it now.")
```

### 6.2 Manager-Controlled Protocol (Optional)

For stricter coordination, a **manager node can define the protocol upfront**:

```
Manager: write_context("protocol", {
    "workers_report_to": "manager",
    "format": "JSON with keys: findings, confidence"
})
```

Workers read the protocol and follow it:
```
Worker: protocol = read_context("protocol")
Worker: send_message("manager", json.dumps({"findings": "...", "confidence": 0.9}))
```

---

## 7. Model Abstraction Layer

Agiraph v2 works with **any LLM provider** through a unified interface.

### 7.1 Provider Interface

```python
class ModelProvider(ABC):
    @abstractmethod
    def generate(
        self,
        messages: List[Message],
        tools: List[Tool],
        system_prompt: str,
        **kwargs
    ) -> Response:
        pass
```

### 7.2 Tool Format Translation

Each provider has different tool/function calling formats. The abstraction layer translates:

**Anthropic:**
```json
{
  "name": "spawn_agent",
  "description": "Create a new agent",
  "input_schema": {
    "type": "object",
    "properties": {"task": {"type": "string"}},
    "required": ["task"]
  }
}
```

**OpenAI:**
```json
{
  "type": "function",
  "function": {
    "name": "spawn_agent",
    "description": "Create a new agent",
    "parameters": {
      "type": "object",
      "properties": {"task": {"type": "string"}},
      "required": ["task"]
    }
  }
}
```

### 7.3 Supported Providers

- **Anthropic** (Claude)
- **OpenAI** (GPT-4, o3)
- **Google** (Gemini)
- **Moonshot** (Kimi)
- **MiniMax** (M2.1)
- **Local models** (via OpenAI-compatible API)

### 7.4 Mixed-Model Teams

Different nodes can use different models:
```python
{
  "nodes": [
    {"id": "manager", "model": "anthropic/claude-opus-4-5"},
    {"id": "worker1", "model": "openai/gpt-4"},
    {"id": "worker2", "model": "minimax/MiniMax-M2.1"}  # Cheap for grunt work
  ]
}
```

---

## 8. MCP Integration

**MCP (Model Context Protocol)** enables agents to use external tools (filesystem, web, databases, etc.).

### 8.1 What is MCP?

MCP is an open protocol for connecting LLMs to tools. Instead of hardcoding tool definitions, we connect to **MCP servers** that expose tool schemas dynamically.

**Example MCP Servers:**
- `filesystem` — read/write files
- `brave-search` — web search
- `postgres` — database queries
- `github` — repo operations

### 8.2 Integration Architecture

```
┌─────────────┐
│  Agiraph    │
│  Runtime    │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  MCP Client     │ ──┐
│  (in Agiraph)   │   │
└─────────────────┘   │
                      │ stdio/HTTP
       ┌──────────────┘
       │
       ▼
┌─────────────────┐
│  MCP Server     │ (filesystem, search, etc.)
│  (External)     │
└─────────────────┘
```

### 8.3 Tool Discovery

When a node is created, the runtime:
1. Queries all configured MCP servers for available tools
2. Merges MCP tools with built-in tools (spawn_agent, send_message, etc.)
3. Passes full tool list to the model

**Example:**
```python
# Built-in tools
builtin_tools = [spawn_agent, send_message, finish]

# MCP tools (from filesystem server)
mcp_tools = mcp_client.list_tools()  # → [read_file, write_file, list_directory]

# Combined
all_tools = builtin_tools + mcp_tools
```

### 8.4 Tool Execution

When a node calls an MCP tool:
1. Runtime identifies the tool's source MCP server
2. Sends tool call to that server
3. Returns result to the node

**Example:**
```python
# Node calls: read_file(path="/docs/README.md")
result = mcp_client.call_tool(
    server="filesystem",
    tool="read_file",
    arguments={"path": "/docs/README.md"}
)
# result = "# Agiraph\n\nAgent orchestration runtime..."
```

### 8.5 Configuration

MCP servers are configured in `agiraph.yaml`:
```yaml
mcp:
  servers:
    filesystem:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
    
    brave_search:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-brave-search"]
      env:
        BRAVE_API_KEY: "${BRAVE_API_KEY}"
```

### 8.6 Security

- **Sandboxing:** MCP servers can be run in Docker containers
- **Permission Model:** Nodes declare which MCP servers they need access to
- **Audit Logging:** All MCP tool calls are logged

---

## 9. Error Handling

Errors can occur at multiple levels. The system handles them gracefully.

### 9.1 Node-Level Errors

**Scenario:** Node's ReAct loop throws an exception (e.g., model API timeout, tool failure)

**Handling:**
1. Catch exception
2. Set node state to `"failed"`
3. Store error in node result: `{"error": "...", "stack_trace": "..."}`
4. Unblock parent node (if any)
5. Parent decides how to handle (retry child, report partial results, fail upwards)

**Example:**
```python
try:
    result = execute_node(node, context, bus)
except Exception as e:
    node.state = "failed"
    node.result = {"error": str(e)}
    scheduler.notify_parent(node.id, "child_failed")
```

### 9.2 Deadlock Detection

**Scenario:** Circular dependencies (Node A waits for Node B, Node B waits for Node A)

**Handling:**
1. Scheduler runs a periodic deadlock check (every 10 seconds)
2. If detected, raise `DeadlockError` and abort execution
3. Log the cycle for debugging

### 9.3 Timeout

**Scenario:** A node runs for too long (infinite loop, stuck waiting for message)

**Handling:**
1. Each node has a configurable timeout (default: 5 minutes)
2. If exceeded, executor kills the thread
3. Node state set to `"failed"` with `"timeout"` error

### 9.4 Max Iterations

**Scenario:** Node's ReAct loop exceeds `max_iterations` without calling `finish()`

**Handling:**
1. Loop terminates
2. Node state set to `"failed"` with `"max_iterations_exceeded"` error
3. Log the conversation history for debugging

---

## 10. API Surface

### 10.1 High-Level API (User-Facing)

```python
from agiraph import Runtime, Task

# Create runtime
runtime = Runtime(
    model_provider="anthropic/claude-sonnet-4-5",
    planning_mode="dynamic",  # or "static"
    mcp_servers=["filesystem", "brave_search"]
)

# Define task
task = Task(
    prompt="Research the top 3 AI companies and create a comparison report",
    output_format="markdown"
)

# Execute
result = runtime.run(task)

# Access results
print(result.output)
print(result.graph)  # Final DAG structure
print(result.logs)   # Execution trace
```

### 10.2 Low-Level API (Advanced)

```python
from agiraph import Graph, Node, Scheduler, Executor

# Manual graph construction (static planning)
graph = Graph()
graph.add_node(Node(id="n1", task="Research Company A", role="worker"))
graph.add_node(Node(id="n2", task="Research Company B", role="worker"))
graph.add_node(Node(id="n3", task="Synthesize", role="manager", deps=["n1", "n2"]))

# Execute
scheduler = Scheduler(graph)
executor = Executor(model_provider="openai/gpt-4")
result = executor.run(scheduler)
```

### 10.3 Streaming API

```python
# Stream execution events
for event in runtime.run_stream(task):
    if event.type == "node_start":
        print(f"Node {event.node_id} started")
    elif event.type == "node_complete":
        print(f"Node {event.node_id} finished: {event.result}")
    elif event.type == "message":
        print(f"Message: {event.from_id} → {event.to_id}: {event.content}")
```

---

## 11. Implementation Phases

### Phase 1: Core Runtime (Recursive Delegation)
**Goal:** Nodes can spawn children, graph grows dynamically

**Deliverables:**
- `Node`, `Graph`, `Scheduler`, `Executor` classes
- `spawn_agent()` tool
- `finish()` tool
- Basic ReAct loop (max 1 iteration for now)

**Test:** Manager spawns 2 workers, workers complete, manager synthesizes

---

### Phase 2: Self-Agentic Loop
**Goal:** Each node runs multi-turn ReAct (not just single inference)

**Deliverables:**
- Extend ReAct loop to max N iterations
- Add error handling (timeout, max iterations)
- Add `read_context()`, `write_context()` tools

**Test:** Single node uses tools across 5 turns to complete task

---

### Phase 3: Inter-Node Messaging
**Goal:** Nodes can coordinate via messages

**Deliverables:**
- `MessageBus` class
- `send_message()`, `check_messages()` tools
- Message injection into ReAct loop

**Test:** 3 nodes coordinate via messaging to complete shared task

---

### Phase 4: Model Abstraction
**Goal:** Works with any LLM provider

**Deliverables:**
- `ModelProvider` interface
- Implementations for Anthropic, OpenAI, Google, MiniMax
- Tool format translation layer

**Test:** Same workflow runs with Claude, GPT-4, Gemini

---

### Phase 5: MCP Integration
**Goal:** Nodes can use external tools via MCP

**Deliverables:**
- MCP client integration
- Tool discovery from MCP servers
- Tool execution routing

**Test:** Node uses filesystem MCP server to read/write files

---

### Phase 6: UI & Observability
**Goal:** Visualize dynamic graph + execution logs

**Deliverables:**
- WebSocket streaming of events
- Live graph visualization (nodes + edges + messages)
- Execution timeline view

**Test:** Run complex workflow, watch it build in real-time

---

## 12. Open Questions

1. **Termination Logic:** How does a manager know when all children are done? Explicit signal vs polling?
2. **Resource Limits:** Max total nodes in graph? Max messages in queue?
3. **Persistence:** Should the graph state be saved to disk for resumability?
4. **Cost Tracking:** Track token usage per node? Per team?
5. **Human-in-Loop:** How to pause execution for human approval/input?

---

## 13. Success Metrics

**Functionality:**
- ✅ Can execute static DAGs (v1 compatibility)
- ✅ Can execute dynamic workflows (nodes spawn children)
- ✅ Nodes can communicate via messages
- ✅ Works with 3+ model providers
- ✅ MCP tools accessible to nodes

**Performance:**
- Target: 10+ nodes running concurrently without degradation
- Max latency per node iteration: <5 seconds (for GPT-4 class models)

**Reliability:**
- Handles node failures gracefully (no cascading crashes)
- Detects deadlocks within 10 seconds
- Logs all tool calls and messages for debugging

---

## 14. Next Steps

1. **Review this design doc** with Tian
2. **Refine API surface** based on feedback
3. **Create Phase 1 implementation plan** (detailed task breakdown)
4. **Set up repo structure** (`/runtime`, `/models`, `/mcp`, `/ui`)
5. **Write Phase 1 code** (Core Runtime + Recursive Delegation)

---

*End of Design Document*
