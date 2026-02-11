# Agiraph v2-A — Technical Design: Part 4 — Implementation

**Part 4 of 4** | [Part 1: Core Concepts](./v2-A-technical-1-core.md) | [Part 2: Runtime](./v2-A-technical-2-runtime.md) | [Part 3: Memory & Human](./v2-A-technical-3-memory-human.md)
**Date:** 2026-02-11

_Covers: Data structures, test scenarios, file structure, API server, web UI, timeline._

---
## 10. Data Structures Summary

```python
@dataclass
class Agent:
    id: str
    path: Path                      # /agents/{id}/
    goal: str                       # the big objective
    mode: str                       # "finite" | "infinite"
    coordinator_model: str          # model for the coordinator
    status: str                     # idle | working | waiting_for_human | paused | completed
    board: WorkBoard                # all work nodes
    worker_pool: WorkerPool         # all workers
    message_bus: MessageBus
    event_log: EventLog
    conversation: AgentConversation

@dataclass
class WorkBoard:
    nodes: dict[str, WorkNode]
    stages: list[Stage]
    current_stage: int

@dataclass
class WorkNode:
    """The workpiece. Has its own folder of truth."""
    id: str
    task: str                       # the spec (also written to _spec.md)
    dependencies: list[str]         # node IDs that must complete first
    refs: dict[str, str]            # pointers to upstream nodes' published data
    status: str                     # pending | assigned | running | completed | failed
    assigned_worker: str | None
    parent_node: str | None
    children: list[str]
    data_dir: Path                  # workspace/nodes/{id}/

    # data_dir layout:
    # _spec.md          — task description
    # _refs.json        — pointers to upstream published/ dirs
    # _status.md        — current status + summary
    # scratch/          — WIP (worker writes here)
    # published/        — final outputs (immutable once completed)
    # log.jsonl         — execution trace

@dataclass
class Worker:
    """The human. Has its own memory and identity."""
    id: str
    name: str
    type: str                       # harnessed | autonomous
    model: str | None
    agent_command: str | None
    status: str                     # idle | busy | waiting_for_human | stopped
    capabilities: list[str]         # which tools this worker can use
    worker_dir: Path                # workspace/workers/{id}/

    # worker_dir layout:
    # identity.md       — who I am, expertise, role
    # memory.md         — accumulated knowledge from past nodes
    # notebook.md       — personal scratchpad
    # history.json      — list of completed work nodes
    # conversation.jsonl — LLM conversation (compactable)

@dataclass
class WorkerPool:
    workers: dict[str, Worker]
    max_concurrent: int = 4

    def idle_workers(self) -> list[Worker]:
        return [w for w in self.workers.values() if w.status == "idle"]

@dataclass
class Stage:
    name: str
    nodes: list[str]
    contract: StageContract
    status: str                     # planning | running | reconvening | completed

@dataclass
class StageContract:
    max_iterations_per_node: int
    timeout_seconds: int
    checkpoint_policy: str

@dataclass
class Message:
    from_id: str
    to_id: str
    content: str
    ts: float
```

### Full Directory Layout

_(See Section 1.0 for scope rules and access control.)_

```
/agents/{agent_id}/                          # AGENT HOME — permanent
├── SOUL.md                                   # Identity
├── GOAL.md                                   # The big objective
├── MEMORY.md                                 # Coordinator's curated long-term memory
├── memory/                                   # Coordinator's knowledge store
│   ├── index.md                              #   self-maintained index
│   ├── knowledge/                            #   domain facts
│   └── 2026-02-11.md                         #   daily log
├── conversation.jsonl                        # Persistent conversation with human
├── events.jsonl                              # All events (append-only)
├── triggers.json                             # Scheduled triggers
│
└── runs/{run_id}/                            # RUN — one execution
    ├── _plan.md                              # Collaboration plan (coordinator writes)
    ├── _messages/                            # Message log (coordinator + workers)
    │
    ├── nodes/                                # NODES — each a unit of work
    │   ├── node_a/
    │   │   ├── _spec.md                      #   what to do (coordinator writes)
    │   │   ├── _refs.json                    #   pointers to upstream published/
    │   │   ├── _status.md                    #   status + summary
    │   │   ├── scratch/                      #   WIP (assigned worker only)
    │   │   ├── published/                    #   final outputs (anyone can read)
    │   │   │   └── findings.md
    │   │   └── log.jsonl                     #   execution trace
    │   ├── node_b/
    │   │   ├── _spec.md
    │   │   ├── _refs.json ──► node_a/published/
    │   │   └── ...
    │   └── node_c/
    │       └── ...
    │
    └── workers/                              # WORKERS — each an executor
        ├── alice/
        │   ├── identity.md                   #   "I am Alice, a market analyst"
        │   ├── memory.md                     #   personal knowledge (private)
        │   ├── notebook.md                   #   scratchpad (private)
        │   ├── history.json                  #   nodes I've completed
        │   └── conversation.jsonl            #   LLM history (compactable)
        ├── bob/
        │   └── ...
        └── claude_code_1/
            └── ...
```

---

## 11. Test Scenarios

### Test 1: Single Agent, Simple Task (Smoke Test)

**Goal:** Verify basic agent loop works end-to-end.

**Setup:**
- Create agent with goal: "What are the top 3 programming languages in 2026?"
- Model: any available (claude-sonnet, gpt-4o)
- Mode: finite
- Tools: web_search, write_file, finish

**Expected flow:**
1. Agent reads goal
2. Calls web_search("top programming languages 2026")
3. Writes findings to workspace/research.md
4. Calls finish() with summary

**Assertions:**
- Agent status transitions: idle → working → completed
- workspace/research.md exists and contains content
- finish() result is a coherent answer
- conversation.jsonl has full trace
- Runs in < 60 seconds

---

### Test 2: Multi-Turn with Tools (Harnessed Loop)

**Goal:** Verify multi-turn ReAct loop with bash and file tools.

**Setup:**
- Agent goal: "Create a Python script that fetches the current Bitcoin price from a public API, and run it to verify it works."
- Model: claude-sonnet
- Tools: bash, write_file, read_file, finish

**Expected flow:**
1. Agent writes a Python script to workspace
2. Calls bash("python workspace/btc_price.py")
3. Reads output, verifies it looks right
4. Maybe iterates if there's an error
5. Finishes with the price

**Assertions:**
- workspace/ contains a .py file
- bash was called at least once
- Agent handled any errors (import issues, API changes) by iterating
- Final result includes a price number

---

### Test 3: Multi-Agent Collaboration (Deep Research)

**Goal:** Coordinator spawns workers for a research task.

**Setup:**
- Agent goal: "Research the current state of AI hardware — compare NVIDIA, AMD, and Intel's latest AI chips. Produce a structured report with technical specs, market position, and recommendation."
- Coordinator model: claude-sonnet (or opus for smarter coordination)
- Worker models: mix of claude-sonnet and gpt-4o (test model mixing)
- Tools: web_search, web_fetch, write_file, send_message, check_messages, finish

**Expected flow:**
1. Coordinator reads goal, creates work nodes:
   - Node A: "Research NVIDIA AI chips" → assigned to Worker 1 (sonnet)
   - Node B: "Research AMD AI chips" → assigned to Worker 2 (gpt-4o)
   - Node C: "Research Intel AI chips" → assigned to Worker 3 (sonnet)
2. Workers execute in parallel (each does web search, writes findings)
3. Workers checkpoint
4. Coordinator reconvenes, reads all outputs
5. Coordinator creates Stage 2:
   - Node D: "Synthesize findings into comparison report" → assigned to Worker 4
6. Worker 4 reads all workspace files, writes final report
7. Coordinator reviews, finishes

**Assertions:**
- 3+ workers ran in parallel
- Each worker's workspace directory has research files
- Messages were exchanged (at least coordinator → workers)
- Final report references all three companies
- Stage reconvene happened at least once
- Different models were used for different workers

---

### Test 4: Recursive Spawning

**Goal:** A worker spawns sub-workers.

**Setup:**
- Agent goal: "Create a full-stack todo app: REST API in Python (FastAPI) + frontend in React + Docker setup."
- Coordinator model: claude-sonnet

**Expected flow:**
1. Coordinator creates Node A: "Build the todo app" → Worker 1
2. Worker 1 realizes this is big, spawns sub-nodes:
   - Node A1: "Build FastAPI backend" → Sub-worker (autonomous: claude-code)
   - Node A2: "Build React frontend" → Sub-worker (autonomous: claude-code)
   - Node A3: "Write Docker config" → Sub-worker (harnessed: sonnet, single-inference)
3. Sub-workers execute in parallel
4. Worker 1 collects results, integrates, tests
5. Agent finishes

**Assertions:**
- Work node tree is at least 2 levels deep
- At least one autonomous worker was used
- At least one single-inference node was used
- workspace/ contains backend/, frontend/, and docker files

---

### Test 5: Human-in-the-Loop

**Goal:** Agent asks human a question mid-work.

**Setup:**
- Agent goal: "Set up a database for our project."
- Tools: ask_human, bash, write_file, finish

**Expected flow:**
1. Agent starts working
2. Calls ask_human("Should I use PostgreSQL or SQLite? What's the use case?")
3. Agent status → waiting_for_human
4. (Test harness simulates human response: "PostgreSQL, it's for a production web app")
5. Agent continues, sets up PostgreSQL
6. Finishes

**Assertions:**
- ask_human event was emitted
- Agent paused and resumed correctly
- Human response was incorporated (agent chose PostgreSQL)
- conversation.jsonl shows the Q&A

---

### Test 6: Memory Persistence Across Runs

**Goal:** Agent remembers things from a previous run.

**Setup:**
- Run 1: Agent goal: "Research Python async patterns. Write what you learn to memory."
  - Agent does research, writes to memory/knowledge/python-asyncio.md
  - Agent finishes
- Run 2: Same agent, new goal: "Write an async web scraper in Python."
  - Agent should find and use its previous research

**Expected flow (Run 2):**
1. Agent loads MEMORY.md + recent daily logs at start
2. Calls memory_search("python async") and finds previous notes
3. Uses that knowledge to write better code
4. Finishes

**Assertions:**
- memory/knowledge/python-asyncio.md exists after Run 1
- Run 2 conversation references or uses content from that file
- Agent didn't re-research what it already knew

---

### Test 7: Long-Running Agent with Context Compaction

**Goal:** Agent works long enough to trigger compaction.

**Setup:**
- Agent goal: "Do a comprehensive analysis of the top 10 AI startups. Research each one individually."
- Model with small context window (or artificially limit to test compaction)
- Tools: web_search, write_file, memory_write, finish

**Expected flow:**
1. Agent researches companies one by one
2. After ~5 companies, conversation hits token limit
3. Memory flush triggered: agent writes durable notes
4. Conversation compacted: system prompt + workspace summaries + last few turns
5. Agent continues researching remaining companies without losing track
6. Finishes with full analysis

**Assertions:**
- Compaction happened at least once
- Agent didn't lose track of which companies it already researched
- Workspace files contain research for all 10 companies
- memory/ has durable notes written during flush
- Final output covers all 10 companies

---

### Test 8: Autonomous Worker (Claude Code)

**Goal:** Verify external agent (Claude Code CLI) works as a worker.

**Setup:**
- Agent goal: "Write a Python CLI tool that converts CSV to JSON."
- Coordinator assigns to an autonomous worker backed by Claude Code CLI.

**Expected flow:**
1. Coordinator creates work node
2. Runtime spawns Claude Code with task via CLI args
3. Claude Code writes code, tests it
4. _result.md appears in workspace
5. Coordinator reads result, finishes

**Assertions:**
- Claude Code process was launched
- workspace/{node_id}/ contains Python files
- _result.md exists with completion summary
- The generated code actually works (bonus: coordinator runs it to verify)

---

### Test 9: Infinite Game (Long-Running Monitor)

**Goal:** Agent runs in infinite mode, doing periodic work.

**Setup:**
- Agent goal: "Monitor Hacker News front page. Every cycle, check for AI-related posts and update a running summary."
- Mode: infinite
- Cycle interval: 30 seconds (for testing)

**Expected flow:**
1. Cycle 1: Agent fetches HN, finds AI posts, writes summary
2. Agent checkpoints, sleeps
3. Cycle 2: Agent wakes, fetches HN again, finds new posts, updates summary
4. Repeat for 3 cycles, then externally stop the agent

**Assertions:**
- Agent ran 3+ cycles
- workspace/hn_summary.md was updated each cycle
- memory/ has notes from each cycle
- Agent didn't re-report the same posts
- Agent stopped cleanly when asked

---

### Test 10: Mixed Team with Messaging

**Goal:** Workers coordinate via messages to solve a task that requires collaboration.

**Setup:**
- Agent goal: "Create a Python package with a module, tests, and documentation. The code writer and test writer should coordinate."
- Coordinator creates:
  - Worker A (coder): "Write a Python module for string utilities"
  - Worker B (tester): "Write tests for the string utilities module"
  - Worker C (docs): "Write README documentation"
- Workers A and B need to coordinate (B needs to know what A wrote)

**Expected flow:**
1. Worker A writes code, sends message to B: "Module is at workspace/coder/strutils.py"
2. Worker B reads A's code, writes tests
3. Worker B sends message to A: "Found a bug in reverse_words()"
4. Worker A fixes bug, re-messages B
5. Worker C reads both and writes docs
6. All checkpoint

**Assertions:**
- Messages were exchanged between workers
- Worker B's tests import/reference Worker A's code
- At least one back-and-forth message exchange
- Final workspace has code + tests + docs

---

## 12. File Structure

```
agiraph/
├── agiraph/
│   ├── __init__.py
│   ├── agent.py              # Agent, AgentConversation
│   ├── coordinator.py        # Coordinator logic
│   ├── scheduler.py          # WorkBoard, Scheduler
│   ├── worker.py             # HarnessedWorker, AutonomousWorker
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py       # Tool registry + dispatch
│   │   ├── core.py           # finish, checkpoint, create_work_node
│   │   ├── communication.py  # send_message, check_messages, ask_human
│   │   ├── workspace.py      # read_file, write_file, list_files
│   │   ├── execution.py      # bash
│   │   ├── research.py       # web_search, web_fetch
│   │   └── memory.py         # memory_write, memory_read, memory_search
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py           # ModelProvider ABC
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   ├── gemini.py
│   │   ├── openrouter.py
│   │   └── text_fallback.py  # For models without tool calling
│   ├── memory.py             # Memory system
│   ├── events.py             # Event types + EventBus
│   ├── message_bus.py        # MessageBus
│   └── config.py             # Configuration loading
├── tests/
│   ├── test_smoke.py         # Test 1
│   ├── test_multi_turn.py    # Test 2
│   ├── test_collaboration.py # Test 3
│   ├── test_recursive.py     # Test 4
│   ├── test_human_loop.py    # Test 5
│   ├── test_memory.py        # Test 6
│   ├── test_compaction.py    # Test 7
│   ├── test_autonomous.py    # Test 8
│   ├── test_infinite.py      # Test 9
│   └── test_messaging.py     # Test 10
├── agents/                   # Agent data (runtime created)
├── docs/
├── pyproject.toml
└── README.md
```

---

## 13. Implementation Order

Build in this order — each phase produces something testable:

**Week 1: Foundation**
- WorkNode, WorkBoard, Worker data structures
- HarnessedWorker with ReAct loop
- Tool registry + dispatch (finish only)
- Provider adapter (start with Anthropic)
- → Run Test 1 (smoke test)

**Week 2: Tools**
- bash, write_file, read_file, list_files, web_search, web_fetch
- Multi-turn iteration with error recovery
- → Run Test 2 (multi-turn with tools)

**Week 3: Multi-Agent**
- Coordinator logic
- Scheduler (assign nodes to workers)
- MessageBus
- Stage + reconvene
- spawn_worker, create_work_node, check_board tools
- → Run Test 3 (deep research) + Test 10 (messaging)

**Week 4: Recursive + Autonomous**
- Recursive spawning (workers create sub-nodes)
- AutonomousWorker (Claude Code CLI integration)
- → Run Test 4 (recursive) + Test 8 (autonomous)

**Week 5: Human + Memory**
- ask_human tool + event surfacing
- AgentConversation (persistent thread)
- Memory system (write/read/search)
- Context compaction + memory flush
- → Run Test 5 (human loop) + Test 6 (memory) + Test 7 (compaction)

**Week 6: Infinite + Polish**
- Infinite mode (cycle scheduler)
- Additional providers (OpenAI, Gemini, OpenRouter)
- Event system + logging
- → Run Test 9 (infinite game)
- → Run all tests end-to-end

---

## 14. Local API Server

The harness runs as a **FastAPI server** on localhost. Everything goes through this API — the web UI, CLI tools, and external integrations all talk to the same endpoints.

### 14.1 Endpoints

```
# Agent lifecycle
POST   /agents                      Create a new agent (goal, model, mode)
GET    /agents                      List all agents
GET    /agents/{id}                 Get agent status + summary
DELETE /agents/{id}                 Stop and archive agent
POST   /agents/{id}/pause           Pause agent (serializes state)
POST   /agents/{id}/resume          Resume paused agent

# Conversation (the primary interface)
POST   /agents/{id}/send            Send a message to the agent (human → agent)
POST   /agents/{id}/nudge           Inject instruction into running agent
GET    /agents/{id}/conversation    Get conversation thread (paginated)
POST   /agents/{id}/respond         Respond to an ask_human question

# Work board
GET    /agents/{id}/board           Get all work nodes + status
GET    /agents/{id}/board/{node_id} Get single node detail + result

# Workers
GET    /agents/{id}/workers         List active workers + status

# Workspace (file browser)
GET    /agents/{id}/workspace       List workspace root
GET    /agents/{id}/workspace/{path} Read a workspace file

# Memory (file browser)
GET    /agents/{id}/memory          List memory directory
GET    /agents/{id}/memory/{path}   Read a memory file
POST   /agents/{id}/memory/search   Semantic search over memory

# Events (real-time)
WS     /agents/{id}/events          WebSocket stream of all events
GET    /agents/{id}/events          Get recent events (paginated, for polling)
```

### 14.2 Server Implementation

```python
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Agiraph", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# Agent registry — all active agents in this server process
agent_registry: dict[str, Agent] = {}

@app.post("/agents")
async def create_agent(req: CreateAgentRequest) -> AgentSummary:
    agent = Agent(
        id=generate_id(),
        goal=req.goal,
        mode=req.mode,                     # finite | infinite
        coordinator_model=req.model,
    )
    agent_registry[agent.id] = agent
    asyncio.create_task(agent.start())     # kicks off the coordinator loop
    return agent.summary()

@app.post("/agents/{agent_id}/send")
async def send_message(agent_id: str, req: SendRequest) -> ConversationMessage:
    agent = agent_registry[agent_id]
    response = await agent.conversation.send(req.message)
    return response

@app.post("/agents/{agent_id}/respond")
async def respond_to_question(agent_id: str, req: RespondRequest) -> dict:
    """Human responds to an ask_human question."""
    agent = agent_registry[agent_id]
    agent.human_response_queue.put(req.response)
    return {"status": "delivered"}

@app.get("/agents/{agent_id}/board")
async def get_board(agent_id: str) -> BoardView:
    agent = agent_registry[agent_id]
    return BoardView(
        nodes=[node_view(n) for n in agent.board.nodes.values()],
        stages=[stage_view(s) for s in agent.board.stages],
        current_stage=agent.board.current_stage,
    )

@app.get("/agents/{agent_id}/workspace/{path:path}")
async def read_workspace_file(agent_id: str, path: str) -> FileContent:
    agent = agent_registry[agent_id]
    full_path = agent.workspace / path
    # Security: ensure path doesn't escape workspace
    assert full_path.resolve().is_relative_to(agent.workspace.resolve())
    return FileContent(path=path, content=full_path.read_text())

@app.websocket("/agents/{agent_id}/events")
async def event_stream(websocket: WebSocket, agent_id: str):
    await websocket.accept()
    agent = agent_registry[agent_id]
    async for event in agent.event_log.subscribe():
        await websocket.send_json(event.to_dict())
```

### 14.3 Request/Response Models

```python
class CreateAgentRequest(BaseModel):
    goal: str
    model: str = "anthropic/claude-sonnet-4-5"
    mode: str = "finite"                    # finite | infinite
    tools: list[str] | None = None          # override default tool set

class SendRequest(BaseModel):
    message: str

class RespondRequest(BaseModel):
    response: str
    question_id: str | None = None          # ties back to specific ask_human

class AgentSummary(BaseModel):
    id: str
    goal: str
    mode: str
    status: str                             # idle | working | waiting_for_human | paused | completed
    current_stage: str | None
    node_count: int
    worker_count: int
    created_at: float
    updated_at: float

class BoardView(BaseModel):
    nodes: list[NodeView]
    stages: list[StageView]
    current_stage: int

class NodeView(BaseModel):
    id: str
    task: str
    status: str
    assigned_worker: str | None
    parent_node: str | None
    children: list[str]
    result_preview: str | None              # first 200 chars of result

class FileContent(BaseModel):
    path: str
    content: str
```

---

## 15. Web UI — Slack-Like Entity View

The primary view is **entity-forward** — like Slack, where each intelligent entity (coordinator, workers) is a "channel" you can see and talk to. The work graph is secondary, in a separate tab.

### 15.1 Layout

```
┌────────────────────┬─────────────────────────────────────┐
│  SIDEBAR           │  MAIN PANEL                         │
│                    │                                     │
│  ▼ AI Chip Research│  ┌─ Coordinator ──────────────────┐ │
│    ★ Coordinator   │  │                                │ │
│    ● Alice (Market)│  │ You: Research AI chip landscape │ │
│    ● Bob (Tech)    │  │                                │ │
│    ○ Carol (Writer)│  │ Coordinator: Setting up a team │ │
│    ─────────────── │  │ of 3 researchers. Alice will   │ │
│    [Work Board]    │  │ cover NVIDIA, Bob handles AMD, │ │
│    [Files]         │  │ Carol takes Intel.             │ │
│    [Memory]        │  │                                │ │
│                    │  │ Coordinator: All workers are   │ │
│  ▼ HN Monitor      │  │ running. Alice found that      │ │
│    ★ Coordinator   │  │ NVIDIA holds 80% of training   │ │
│    ● Scanner       │  │ market.                        │ │
│                    │  │                                │ │
│  [+ New Agent]     │  │ > You: Also include Qualcomm   │ │
│                    │  │                                │ │
│                    │  │ Coordinator: Got it. Spawning   │ │
│                    │  │ a 4th researcher for Qualcomm. │ │
│                    │  │                                │ │
│                    │  │ ┌────────────────────────────┐ │ │
│                    │  │ │ Type a message...     [Send]│ │ │
│                    │  │ └────────────────────────────┘ │ │
│                    │  └────────────────────────────────┘ │
└────────────────────┴─────────────────────────────────────┘
```

### 15.2 Sidebar — Entity List

Each agent is a collapsible group. Under it, every living entity:

- **★ Coordinator** — always present, always first. This is where the human chats by default.
- **● Workers** — appear as they're spawned, disappear when retired. Color dot = status:
  - Green = idle/done
  - Blue = working
  - Yellow = waiting for human
  - Gray = retired
- **Tabs** at the bottom of each agent group:
  - [Work Board] — switch main panel to node/graph view
  - [Files] — switch to workspace file browser
  - [Memory] — switch to memory file browser

Clicking any entity opens their **conversation/activity view** in the main panel.

### 15.3 Main Panel — Entity View (Default)

When you click on an entity (coordinator or worker), the main panel shows:

**For Coordinator:**
- Chat thread with the human (the primary conversation)
- System events inline (stage started, workers spawned, reconvene decisions)
- Tool calls collapsed by default, expandable
- Human can type messages at the bottom — goes to coordinator

**For Worker:**
- The worker's activity stream: what they're doing, tool calls, messages sent/received
- The human can type here too — message goes directly to that worker
- Shows the worker's current node assignment, status, and progress
- Worker's published outputs inline (or link to file browser)

```
┌─ Alice (Market Analyst) ─────────── sonnet ── ● working ─┐
│                                                            │
│  CURRENT NODE: nvidia_research                            │
│  SPEC: Research NVIDIA AI chips — market share, H100...   │
│                                                            │
│  [14:02] web_search("NVIDIA H100 market share 2025 2026") │
│  [14:02] → 5 results found                                │
│  [14:03] web_fetch("https://...")                          │
│  [14:03] → Fetched 12KB                                   │
│  [14:04] write_file("scratch/nvidia_findings.md")         │
│  [14:05] → Alice to Coordinator: "NVIDIA holds ~80%       │
│            of training GPU market. H100 still dominant     │
│            but B200 ramping up."                           │
│  [14:06] → Alice to Human: "Should I include gaming GPUs  │
│            or just data center?"                           │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ Type a message to Alice...                     [Send]│ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

### 15.4 Work Board Tab (Secondary)

When clicking [Work Board] in the sidebar, main panel switches to the node/graph view:

```
┌─ Work Board ─────────────────────────────────────────────┐
│                                                           │
│  Stage 1: Research                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ NVIDIA       │  │ AMD          │  │ Intel        │  │
│  │ research     │  │ research     │  │ research     │  │
│  │ ────────── │  │ ────────── │  │ ────────── │  │
│  │ Alice       │  │ Bob          │  │ Carol        │  │
│  │ ● done      │  │ ◐ running    │  │ ○ pending    │  │
│  │             │  │              │  │              │  │
│  │ [view data] │  │ [view data]  │  │              │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                 │           │
│         └────────────┬────┘─────────────────┘           │
│                      ▼                                   │
│              ┌──────────────┐                           │
│              │ Synthesis    │  Stage 2 (blocked)        │
│              │ ○ pending    │                           │
│              └──────────────┘                           │
│                                                         │
│  Click a node to see: spec, refs, scratch/, published/  │
└─────────────────────────────────────────────────────────┘
```

Each node is clickable → expands to show _spec.md, _refs.json, scratch/ files, published/ files, and the execution log.

### 15.5 Files & Memory Tabs

Simple file browser panels (same as before). Click a file to preview markdown/code.

### 15.6 Notifications

When a worker or coordinator sends a message to the human:
- **Badge** on the entity in the sidebar (unread count)
- **Toast notification** for ask_human questions (needs response)
- **Inline highlight** in the conversation thread

### 15.7 Real-Time

WebSocket to `/agents/{id}/events`. Updates everything live:
- New entities appear in sidebar as workers spawn
- Activity streams update as workers call tools
- Badges increment on new messages
- Node status changes on work board

### 15.8 Implementation

```
frontend/
├── app/
│   ├── page.tsx                    # Agent list (home)
│   ├── agents/[id]/
│   │   ├── page.tsx                # Agent shell (sidebar + main panel)
│   │   └── layout.tsx
│   └── layout.tsx
├── components/
│   ├── Sidebar/
│   │   ├── AgentGroup.tsx          # Collapsible agent with entity list
│   │   ├── EntityItem.tsx          # Worker/coordinator row with status dot
│   │   └── TabLinks.tsx            # Work Board / Files / Memory tabs
│   ├── MainPanel/
│   │   ├── CoordinatorChat.tsx     # Chat thread with human
│   │   ├── WorkerActivity.tsx      # Worker activity stream
│   │   ├── WorkBoard.tsx           # Node graph / stage view
│   │   ├── FileBrowser.tsx         # Workspace file tree + preview
│   │   └── MemoryBrowser.tsx       # Memory file tree + preview
│   ├── Shared/
│   │   ├── MessageInput.tsx        # Chat input bar
│   │   ├── ToolCallBlock.tsx       # Collapsible tool call display
│   │   ├── FilePreview.tsx         # Markdown/code renderer
│   │   ├── NodeDetail.tsx          # Expanded node view (spec, files)
│   │   └── Notification.tsx        # Toast + badge
├── hooks/
│   ├── useAgent.ts                 # Agent state
│   ├── useEntities.ts              # Workers + coordinator
│   ├── useEvents.ts                # WebSocket event stream
│   └── useConversation.ts          # Chat state
└── lib/
    └── api.ts                      # API client
```

---

## 16. Updated Implementation Order

**Week 1: Foundation**
- Data structures (WorkNode, WorkBoard, Worker, Agent)
- HarnessedWorker with ReAct loop
- Tool registry + dispatch (finish only)
- Provider adapter (Anthropic)
- **→ Test 1 (smoke)**

**Week 2: Tools + Conversation**
- All core tools (bash, file I/O, web_search, web_fetch)
- AgentConversation (persistent thread, conversation.jsonl)
- FastAPI server with basic endpoints (create agent, send message, get status)
- **→ Test 2 (multi-turn with tools)**

**Week 3: Multi-Agent + Board**
- Coordinator logic + scheduler
- MessageBus + send_message/check_messages
- Stage + reconvene
- Work board endpoints (GET /board, /workers)
- **→ Test 3 (deep research) + Test 10 (messaging)**

**Week 4: Recursive + Autonomous**
- Recursive spawning
- AutonomousWorker (Claude Code CLI)
- **→ Test 4 (recursive) + Test 8 (autonomous)**

**Week 5: Human + Memory**
- ask_human + respond endpoints
- Memory system (write/read/search)
- Context compaction + memory flush
- Memory/workspace browser endpoints
- **→ Test 5 (human loop) + Test 6 (memory) + Test 7 (compaction)**

**Week 6: Web UI**
- Agent list page
- Agent detail: conversation panel
- Agent detail: work board panel
- Agent detail: file browsers (workspace + memory)
- WebSocket event streaming
- **→ All tests end-to-end via UI**

**Week 7: Infinite + Polish**
- Infinite mode (cycle scheduler)
- Additional providers (OpenAI, Gemini, OpenRouter)
- Event log UI
- **→ Test 9 (infinite game)**

---

*End of Technical Design*
