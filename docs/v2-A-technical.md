# Agiraph v2-A — Technical Design

**Companion to:** [v2-A-plan.md](./v2-A-plan.md)
**Date:** 2026-02-11

---

## 0. The Core Idea — Emergent Graphs, Not Predetermined Plans

**The graph is NOT planned upfront. It grows as work happens.**

There is no planner that generates a full DAG before execution. The coordinator starts with a goal, creates the first node or two, assigns workers, and waits. Based on results, the coordinator (or a worker) decides what comes next. The graph emerges from work — it's discovered, not designed.

### How the Graph Grows

```
Time 0: Goal arrives
         ┌────────────┐
         │ Coordinator │ "Hmm, I need to research this first."
         └──────┬──────┘
                │ creates
                ▼
         ┌────────────┐
         │  Node A    │ "Research the topic"
         │  (running) │
         └──────┬──────┘
                │ result comes back
                ▼
Time 1: Coordinator reads Node A's output.
        "OK, there are 3 sub-areas. I need to go deeper."
                │ creates
         ┌──────┼──────┐
         ▼      ▼      ▼
       Node B  Node C  Node D    (parallel)
       (running)(running)(running)
                │
                ▼
Time 2: Node C's worker says "I found something unexpected.
        We should also look at X."
        Worker → Coordinator: "Suggest adding a node for X."
        Coordinator: "Good idea."
                │ creates
                ▼
              Node E    (added mid-stage)

Time 3: Nodes B, C, D, E complete.
        Coordinator reconvenes.
        "Node D's result is thin. Node E revealed a new angle.
        I need one more node to synthesize."
                │ creates
                ▼
              Node F    "Synthesize all findings"
                │
                ▼
Time 4: Node F completes. Coordinator finishes.
```

**No step of this was predetermined.** Node E didn't exist until a worker suggested it. Node F was created after seeing all results. The graph has 6 nodes but the coordinator never "planned 6 nodes" — it planned one at a time, based on what it learned.

### Multi-Level ReAct Loops

There are ReAct loops at every level. Loops inside loops.

```
LEVEL 0: AGENT LOOP (the coordinator)
┌────────────────────────────────────────────────────────┐
│  while goal not met:                                    │
│    assess current state                                 │
│    decide: create nodes? assign workers? reconvene?     │
│    act (create nodes, send messages, read outputs)      │
│    observe results                                      │
│    repeat                                               │
│                                                         │
│    LEVEL 1: WORKER LOOP (per node)                     │
│    ┌──────────────────────────────────────────────┐    │
│    │  while node not done:                         │    │
│    │    check messages                             │    │
│    │    think (LLM call)                           │    │
│    │    act (tool call: bash, search, write, etc.) │    │
│    │    observe result                             │    │
│    │    repeat or publish                          │    │
│    │                                               │    │
│    │    LEVEL 2: SUB-SPAWN (worker creates nodes) │    │
│    │    ┌─────────────────────────────────────┐   │    │
│    │    │  worker decides task is too big       │   │    │
│    │    │  creates sub-nodes                   │   │    │
│    │    │  waits for sub-workers to finish     │   │    │
│    │    │  integrates results                  │   │    │
│    │    │  publishes                           │   │    │
│    │    └─────────────────────────────────────┘   │    │
│    └──────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────┘
```

### Coordinator Strategies

The coordinator adapts its strategy based on model strength and task complexity:

**Strategy 1: Micro-manage (weak workers)**
Coordinator creates many small, specific nodes. Each worker does one narrow thing. Coordinator synthesizes.
```
Coordinator creates: "Search for NVIDIA H100 specs" → single-inference worker
Coordinator creates: "Search for AMD MI300X specs" → single-inference worker
Coordinator creates: "Compare the two" → single-inference worker
(coordinator does all the thinking, workers are cheap hands)
```

**Strategy 2: Delegate (strong workers)**
Coordinator creates a few big nodes. Each worker is a strong model running a full ReAct loop. Workers decide how to break down the work themselves.
```
Coordinator creates: "Research NVIDIA AI hardware comprehensively" → strong model, 20-iteration loop
(worker searches, reads, writes, iterates on its own until context fills up)
```

**Strategy 3: Hire and let go (autonomous workers)**
Coordinator launches an autonomous agent (Claude Code) with a big task. The agent runs its own loop entirely. Coordinator just waits for the result.
```
Coordinator creates: "Build a REST API for todos with tests" → Claude Code subprocess
(Claude Code runs for 10 minutes, writes code, tests, exits)
```

**Strategy 4: Mixed**
Real tasks use all three. The coordinator picks the right strategy per node.
```
Node A: "Research market data" → strong model, ReAct loop (strategy 2)
Node B: "Write the backend" → Claude Code (strategy 3)
Node C: "Format the data into a table" → cheap model, single inference (strategy 1)
```

### Workers Can Suggest Next Steps

Workers don't just execute — they can observe patterns and suggest what the coordinator should do next:

```python
# Worker tools include:
"suggest_next": {
    "description": "Suggest a follow-up work node to the coordinator. "
                   "The coordinator decides whether to create it.",
    "params": {
        "suggestion": "str — what work should be done next and why",
    },
}
```

The coordinator receives the suggestion as a message and decides whether to act on it. This makes the graph growth bottom-up AND top-down:
- **Top-down:** Coordinator creates nodes based on its plan
- **Bottom-up:** Workers suggest nodes based on what they discover

### Context Window as Natural Boundary

A worker's iteration limit isn't just a safety valve — it's a **natural scoping mechanism**. A worker runs until either:
1. It finishes the task (calls `publish()`)
2. It runs out of iterations (max turns)
3. Its context window fills up (triggers compaction or handoff)

When context fills up, the worker has a choice:
- **Compact and continue:** Flush to files, compress conversation, keep going
- **Publish partial results and hand off:** Write what you have, publish, let the coordinator assign a follow-up node for someone else to continue

This means a single big task naturally fragments into manageable pieces based on model context limits. The coordinator doesn't need to know how big each piece should be — the worker figures it out.

---

## 1. Data Scopes — What Lives Where

Before anything else, let's define the data boundaries clearly. There are four distinct scopes. Nothing is called "workspace" — that word was doing too many jobs.

### 1.0 The Four Scopes

```
/agents/{agent_id}/                    ← AGENT HOME (permanent, survives across runs)
├── SOUL.md                             │ Agent identity
├── GOAL.md                             │ The big objective
├── MEMORY.md                           │ Agent-level curated long-term memory
├── memory/                             │ Agent-level knowledge store
├── conversation.jsonl                  │ Persistent conversation with human
│
├── runs/{run_id}/                     ← RUN (one execution toward the goal)
│   ├── _plan.md                        │ Collaboration plan (shared state)
│   ├── _messages/                      │ Message log (shared state)
│   │
│   ├── nodes/{node_id}/              ← NODE DATA (one unit of work)
│   │   ├── _spec.md                    │ What to do
│   │   ├── _refs.json                  │ Pointers to other nodes' published/
│   │   ├── scratch/                    │ WIP (worker writes here)
│   │   ├── published/                  │ Final outputs (immutable, readable by others)
│   │   └── log.jsonl                   │ Execution trace
│   │
│   └── workers/{worker_id}/          ← WORKER DATA (one executor's personal files)
│       ├── identity.md                 │ Who I am, my role
│       ├── memory.md                   │ What I've learned (from this run's nodes)
│       ├── notebook.md                 │ Personal scratchpad
│       └── conversation.jsonl          │ LLM conversation (compactable)
│
├── events.jsonl                        │ All events (append-only)
└── triggers.json                       │ Scheduled triggers
```

### Scope Rules

| Scope | Who owns it | Who can read | Who can write | Lifetime |
|---|---|---|---|---|
| **Agent home** | The agent | Agent + human | Agent (coordinator) | Permanent |
| **Run** (shared state) | Coordinator | Everyone in the run | Coordinator | One run |
| **Node data** | The node | Anyone (published/) | Assigned worker only | One run |
| **Worker data** | The worker | The worker itself | The worker itself | One run (but worker can write to agent memory for permanence) |

### What's shared, what's private

**Agent memory (`/agents/{id}/MEMORY.md`, `/agents/{id}/memory/`):**
- Belongs to the **agent** (the coordinator). NOT shared with workers.
- Loaded into the coordinator's system prompt at start.
- Workers do NOT see agent memory directly. The coordinator can choose to share relevant bits via node specs or messages.
- Think of it like: the CEO's notes. Workers get briefs, not the CEO's notebook.

**Worker memory (`runs/{run}/workers/{id}/memory.md`):**
- Belongs to that **specific worker**. Private.
- Carries across node assignments within the same run (worker finishes Node A, picks up Node B, still has their memory).
- Does NOT survive across runs. But a worker can write lasting insights to the agent's memory via a tool call, if the coordinator allows it.
- Think of it like: an employee's personal notes. They keep them while they're working.

**Node published data (`runs/{run}/nodes/{id}/published/`):**
- Readable by anyone. This is the node's "deliverable" — its output to the world.
- Immutable once published.
- Other nodes reference this via `_refs.json`.
- Think of it like: a finished report sitting on a shared drive.

**Node scratch data (`runs/{run}/nodes/{id}/scratch/`):**
- Private to the assigned worker while they're working.
- This is the workbench — drafts, intermediate results.
- Moves to published/ when the worker calls `publish()`.
- Think of it like: papers on your desk while you're working on something.

**Run shared state (`runs/{run}/_plan.md`, `_messages/`):**
- Written by the coordinator, readable by everyone.
- The plan, the message log, coordination artifacts.

### Why This Matters

With clear scopes:
- A worker can't accidentally read another worker's private notes
- Published data is the only contract between nodes — clean interfaces
- Agent memory is the coordinator's strategic context, not leaked to every worker
- Workers are disposable (retire, replace) without losing the agent's knowledge
- Runs are isolated — a failed run doesn't corrupt the agent's permanent state

---

## 1.1 The Conversational Agent

An agent is a **long-lived conversational entity**. It has a persistent conversation thread — you talk to it, it talks back, and in between it does work. The conversation is infinite (compacted when needed, never lost). Think of it like texting a coworker who happens to be an AI.

### Agent Identity (Soul)

Inspired by OpenClaw. Each agent gets identity files loaded into its system prompt at session start:

```
/agents/{agent_id}/
├── SOUL.md          # Who you are — persona, tone, boundaries
├── GOAL.md          # What you're working on — the big objective
├── MEMORY.md        # Curated long-term memory (coordinator only)
├── memory/          # Daily logs + topical knowledge files
│   ├── 2026-02-11.md
│   ├── knowledge/   # Domain facts accumulated over time
│   └── experiences/ # What worked, what didn't
└── conversation.jsonl  # Persistent conversation with human
```

### 1.2 System Prompt Construction

At each turn, the system prompt is assembled from:

```python
def build_system_prompt(agent: Agent) -> str:
    sections = []
    sections.append(read_file(agent.path / "SOUL.md"))        # identity
    sections.append(read_file(agent.path / "GOAL.md"))         # mission
    sections.append(f"Today is {date.today()}")
    sections.append(format_tool_descriptions(agent.tools))     # available tools
    sections.append(read_file(agent.path / "MEMORY.md"))       # long-term memory
    sections.append(read_recent_memory(agent.path / "memory")) # last 2 days
    sections.append(OPERATING_RULES)                           # see below
    return "\n\n---\n\n".join(sections)
```

**Operating rules** (hardcoded, like OpenClaw's AGENTS.md):

```
OPERATING RULES:
- You are a persistent agent. Your conversation continues across sessions.
- Write important findings to files. Your conversation may be compacted —
  anything not written to a file may be forgotten.
- Check MEMORY.md at session start. Update it with lasting insights.
- You can spawn sub-agents for parallel or specialized work.
- You can ask your human for guidance when stuck.
- For finite goals: work until done, then call finish().
- For ongoing goals: work in cycles, checkpoint between them.
```

### 1.3 Conversation Thread

The agent maintains one continuous conversation (`conversation.jsonl`). Each line is a message:

```jsonl
{"role": "system", "content": "...", "ts": 1707600000}
{"role": "user", "content": "Build a REST API for todos", "ts": 1707600001}
{"role": "assistant", "content": "I'll start by...", "ts": 1707600002, "tool_calls": [...]}
{"role": "tool", "name": "bash", "content": "...", "ts": 1707600003}
```

**Compaction:** When token count approaches the model's limit, compact:
1. Trigger a memory flush — agent writes durable notes to files (like OpenClaw)
2. Rebuild context: system prompt + workspace file summaries + last N turns
3. Replace conversation with compacted version
4. Old conversation archived (never deleted)

The human can talk to the agent at any time. New messages are appended to the thread. The agent responds in the same thread. It feels like a chat.

---

## 2. Work Nodes vs Workers (Decoupled)

A **work node** is a workpiece. A **worker** is a human. They have independent data and lifecycles — like a machinist and the part on the lathe. The part has its own spec sheet and folder of drawings. The machinist has their own brain, notebook, and years of experience. When the machinist picks up a part, they bring their knowledge to it. When they put it down, both retain their own state.

### 2.1 Work Node (The Workpiece)

A work node is a unit of work with its own **folder of truth** — all data about this piece of work lives there.

```python
@dataclass
class WorkNode:
    id: str
    task: str                    # what to do (the spec)
    dependencies: list[str]      # node IDs that must complete first
    status: str                  # pending | assigned | running | completed | failed
    assigned_worker: str | None  # worker ID, if assigned
    parent_node: str | None      # node that spawned this one
    children: list[str]          # nodes spawned by this one
    data_dir: Path               # this node's folder of truth
```

**Node data directory — the folder of truth:**

```
workspace/nodes/{node_id}/
├── _spec.md                  # Task description, acceptance criteria
├── _status.md                # Current status + summary
├── _refs.json                # Pointers to other nodes' published data
│                              # e.g. {"input_from": ["node_a/published/research.md"]}
├── scratch/                  # Work-in-progress (worker writes here while working)
│   ├── notes.md
│   └── draft.py
├── published/                # Final outputs (immutable once node completes)
│   ├── report.md
│   └── data.json
└── log.jsonl                 # Execution trace (tool calls, messages)
```

**Key rules:**
- `_spec.md` — written by the coordinator or parent node. The worker reads it.
- `_refs.json` — pointers to upstream nodes' `published/` directories. The worker reads those.
- `scratch/` — worker's work-in-progress on this node. Discardable after completion.
- `published/` — the node's output. Other nodes reference this. Immutable once status=completed.
- Any node can **read** another node's `published/` directory. Nobody writes to another node's folder.

**Node lifecycle:**
```
created → _spec.md written, _refs.json populated
assigned → worker picks it up
running → worker reads spec + refs, writes to scratch/
completed → worker promotes scratch → published, writes _status.md
```

### 2.2 Worker (The Human)

A worker has its own **memory and identity** — independent from any work node. A worker can pick up many nodes over its lifetime and carry knowledge across them.

```python
@dataclass
class Worker:
    id: str
    name: str                    # "Alice", "Bob"
    type: str                    # "harnessed" | "autonomous"
    model: str | None            # for harnessed: which model to call
    agent_command: str | None    # for autonomous: CLI command to launch
    status: str                  # idle | busy | waiting_for_human | stopped
    capabilities: list[str]      # what tools this worker has access to
    worker_dir: Path             # this worker's personal directory
```

**Worker directory — the worker's own brain:**

```
workspace/workers/{worker_id}/
├── identity.md               # Who I am, what I'm good at (like SOUL.md)
├── memory.md                 # Accumulated knowledge from past work nodes
├── notebook.md               # Personal work notes, scratchpad
├── history.json              # List of work nodes I've completed
└── conversation.jsonl        # My conversation history (compactable)
```

**Key rules:**
- `identity.md` — set at spawn time. Describes the worker's role and expertise.
- `memory.md` — the worker updates this after finishing each work node. Carries forward.
- `notebook.md` — running scratchpad. The worker uses this for thinking across nodes.
- `history.json` — which nodes this worker has done. Useful for context.
- `conversation.jsonl` — the worker's LLM conversation. Compacted as needed.

**A worker is reusable.** After finishing Node A, the worker can pick up Node B. They carry their memory and notebook. A worker spawned to research NVIDIA chips remembers what it learned when assigned to research AMD chips next.

### 2.3 How They Connect

When a worker is assigned to a node, the runtime connects them:

```python
def assign_worker_to_node(worker: Worker, node: WorkNode):
    node.assigned_worker = worker.id
    node.status = "assigned"
    worker.status = "busy"

    # Build the worker's context for this node
    context = WorkContext(
        # From the node (the workpiece)
        spec=read_file(node.data_dir / "_spec.md"),
        refs=load_refs(node.data_dir / "_refs.json"),      # read upstream published data
        scratch_dir=node.data_dir / "scratch",              # where to write WIP

        # From the worker (personal knowledge)
        identity=read_file(worker.worker_dir / "identity.md"),
        memory=read_file(worker.worker_dir / "memory.md"),
        notebook=read_file(worker.worker_dir / "notebook.md"),
    )
```

The worker's system prompt includes both:

```
You are {worker.name}. {worker.identity}

YOUR MEMORY (from past work):
{worker.memory}

---

CURRENT ASSIGNMENT:
{node.spec}

INPUT DATA (from upstream nodes):
{formatted refs — file contents or summaries}

YOUR SCRATCH DIRECTORY: {node.scratch_dir}
Write work-in-progress here. When done, call publish() to finalize outputs.

RULES:
- Read the spec carefully.
- Use ref data from upstream nodes.
- Write your outputs to scratch/ as you work.
- Call publish() when done — this moves your outputs to published/.
- Update your notebook with anything worth remembering.
```

### 2.4 Decoupling Diagram

```
WORK BOARD (workpieces)                    WORKER POOL (humans)
┌────────────────────────┐                 ┌────────────────────┐
│                        │                 │                    │
│  Node A [research]     │    assigned     │  Worker 1 (sonnet) │
│  ├── _spec.md          │◄──────────────►│  ├── identity.md   │
│  ├── scratch/          │                 │  ├── memory.md     │
│  └── published/        │                 │  └── notebook.md   │
│       └── findings.md  │                 │                    │
│                        │                 │  Worker 2 (gpt-4o) │
│  Node B [code]         │    assigned     │  ├── identity.md   │
│  ├── _spec.md          │◄──────────────►│  ├── memory.md     │
│  ├── _refs.json ──────►│ Node A/published│  └── notebook.md   │
│  ├── scratch/          │                 │                    │
│  └── published/        │                 │  Worker 3 (claude) │
│                        │                 │  ├── identity.md   │
│  Node C [write]        │    pending      │  ├── memory.md     │
│  ├── _spec.md          │  (unassigned)   │  └── notebook.md   │
│  └── _refs.json ──────►│ Node A,B/pub    │                    │
│                        │                 │                    │
└────────────────────────┘                 └────────────────────┘

Nodes reference each other's published/ data.
Workers carry their own memory across assignments.
```

### 2.5 Publish Flow

When a worker finishes a node:

```python
def impl_publish(context: WorkContext, summary: str) -> str:
    """Move scratch outputs to published/. Finalize the node."""
    node = context.node
    worker = context.worker

    # 1. Move scratch → published
    for f in (node.data_dir / "scratch").iterdir():
        shutil.move(f, node.data_dir / "published" / f.name)

    # 2. Write status
    write_file(node.data_dir / "_status.md", f"COMPLETED\n\n{summary}")
    node.status = "completed"

    # 3. Worker updates personal memory
    # (prompted: "What did you learn from this work node?")
    worker_reflection = prompt_worker_reflection(worker, node, summary)
    append_file(worker.worker_dir / "memory.md", worker_reflection)
    append_file(worker.worker_dir / "history.json", {
        "node_id": node.id, "task": node.task, "summary": summary
    })

    # 4. Worker is now idle — ready for next assignment
    worker.status = "idle"
    return "Published. Node complete."
```

### 2.6 Harnessed Worker

We manage the loop. The model is a dumb API call.

```python
class HarnessedWorker:
    def execute(self, node: WorkNode, tools: list[Tool]) -> str:
        # Build context from BOTH node data and worker memory
        context = build_work_context(self, node)
        conversation = [
            {"role": "system", "content": context.system_prompt},
            {"role": "user", "content": context.spec}
        ]

        for i in range(self.max_iterations):
            response = self.provider.generate(
                messages=conversation,
                tools=tools
            )
            conversation.append({"role": "assistant", "content": response})

            if response.tool_calls:
                for tc in response.tool_calls:
                    if tc.name == "publish":
                        return self.publish(node, tc.args["summary"])
                    result = self.dispatch_tool(tc)
                    conversation.append({"role": "tool", "name": tc.name, "content": result})

                    if self.needs_compaction(conversation):
                        conversation = self.compact(conversation, node)
            else:
                pass

        raise MaxIterationsError(node.id)
```

**Single-inference mode:** Set `max_iterations=1` and don't provide tools. The model gets one shot. Cheapest possible execution.

**Multi-turn mode:** Full ReAct loop with tools, iteration limit, and compaction.

### 2.5 Autonomous Worker

An external agent we launch as a subprocess. We give it a task, it does its thing, we wait for the result.

```python
class AutonomousWorker:
    def execute(self, node: WorkNode) -> str:
        # Write task to the node's workspace
        task_dir = self.workspace / node.id
        task_dir.mkdir(exist_ok=True)
        write_file(task_dir / "_task.md", node.task)
        write_file(task_dir / "_context.json", json.dumps(node.context))
        write_file(task_dir / "_inbox.md", "")
        write_file(task_dir / "_outbox.md", "")

        # Launch external agent
        process = subprocess.Popen(
            self.build_command(node, task_dir),
            cwd=task_dir
        )

        # Monitor
        while process.poll() is None:
            self.bridge_messages(node, task_dir)
            if (task_dir / "_result.md").exists():
                process.terminate()
                return read_file(task_dir / "_result.md")
            time.sleep(POLL_INTERVAL)

        # Process exited — check for result
        if (task_dir / "_result.md").exists():
            return read_file(task_dir / "_result.md")
        raise WorkerError(f"Autonomous worker exited without result: {node.id}")
```

**Claude Code example:**
```python
def build_command(self, node, task_dir):
    return [
        "claude", "-p", node.task,
        "--output-dir", str(task_dir),
        "--allowedTools", "bash,read,write,edit"
    ]
```

The key: any CLI agent that can accept a task as input and produce files as output can be a worker. Claude Code, Codex CLI, Aider, a custom script — doesn't matter.

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

## 7. Memory System

### 7.1 Structure

```
/agents/{agent_id}/memory/
├── index.md                # Self-maintained: what's stored and where
├── knowledge/              # Domain facts
│   ├── ai-chips.md
│   └── python-asyncio.md
├── experiences/            # Procedural: what worked, what didn't
│   ├── coding-patterns.md
│   └── research-strategies.md
├── preferences/            # Human's preferences, communication style
│   └── human-notes.md
└── 2026-02-11.md           # Daily log (append-only)
```

### 7.2 Memory Lifecycle

**During work:** Agent writes findings/artifacts to workspace files. These are working memory — scoped to the current run.

**At checkpoint/reconvene:** Agent is prompted: *"Reflect on what you learned. Write lasting insights to memory/."*

**At compaction:** Before context is compacted, agent gets a memory flush turn (like OpenClaw): *"Session nearing compaction. Store durable memories now."*

**At session start:** Agent reads MEMORY.md + last 2 days of daily logs + index.md. For specific tasks, it can `memory_search` for relevant older notes.

**Periodic maintenance:** Agent reviews daily logs, distills into long-term memory, prunes outdated info. Can be triggered by a heartbeat/cron mechanism.

### 7.3 Memory Search

Keep it simple. Two modes:

**Mode 1: Load all.** If total memory files are small enough (< token budget), just load everything into context. The model searches by reading. This is the default for agents with modest memory.

**Mode 2: Grep by section.** For larger memory stores, grep for keywords and return whole sections (chunks delimited by markdown headers). Memory files are expected to be sectioned with small titles — each section is a self-contained chunk.

```python
def impl_memory_search(context: ToolContext, query: str) -> str:
    """Search memory files. Returns matching sections."""
    memory_dir = context.agent.path / "memory"

    # If total memory is small, just return everything
    all_files = list(memory_dir.rglob("*.md"))
    total_size = sum(f.stat().st_size for f in all_files)
    if total_size < MAX_MEMORY_INLINE:  # e.g. 20KB
        return "\n\n---\n\n".join(
            f"**{f.relative_to(memory_dir)}**\n{f.read_text()}"
            for f in all_files
        )

    # Otherwise: grep for keywords, return matching sections
    keywords = query.lower().split()
    results = []
    for md_file in all_files:
        sections = split_by_headers(md_file.read_text())  # split on ## or ###
        for section in sections:
            if any(kw in section.lower() for kw in keywords):
                results.append((md_file.relative_to(memory_dir), section))

    if not results:
        return "No matching memory found."
    return "\n\n---\n\n".join(
        f"**{path}**\n{section}" for path, section in results[:10]
    )

def split_by_headers(text: str) -> list[str]:
    """Split markdown into sections at ## or ### headers.
    Each section includes its header line + body until the next header."""
    sections = []
    current = []
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
```

Vector search can come later. Grep + section chunking is good enough for v1 memory.

---

## 8. Human as a Node

The human is not an external entity — they're a **special node on the message bus**, just like any worker. They have their own inbox, can send messages to anyone, and can be talked to by anyone. Human messages go to the **coordinator by default** — the coordinator is the receptionist.

### 8.1 The Human Node

```python
class HumanNode:
    """The human is just another participant on the message bus."""
    id: str = "human"
    name: str = "Human"
    inbox: MessageQueue               # messages FROM agents TO human
    status: str = "available"         # available | away
    default_recipient: str = "coordinator"  # human messages go here by default

    # The human's inbox is surfaced via multiple channels
    channels: list[Channel]           # cli, web_ui, slack, discord, email, etc.
```

**Default routing:** When the human sends a message without specifying a recipient, it goes to the coordinator. The coordinator is the always-live front desk — it's the agent's "face" to the human.

```
         ┌──────────┐
         │  Human   │ ← messages go to coordinator by default
         │  (inbox) │
         └────┬─────┘
              │  default route
              ▼
    ┌──────────────────────────────────┐
    │   ┌──────────────┐               │
    │   │  Message Bus │               │
    │   └──────────────┘               │
    │     ▲    ▲    ▲                  │
    │     │    │    │                  │
    │  ┌──┴────┴─┐ ┌┴──┐ ┌┴───────┐  │
    │  │Coordina │ │W:A│ │W:Bob   │  │
    │  │tor      │ │lic│ │        │  │
    │  │(always  │ │e  │ │        │  │
    │  │ live)   │ │   │ │        │  │
    │  └─────────┘ └───┘ └────────┘  │
    └──────────────────────────────────┘
```

### 8.2 Node Responsiveness — The Yield Point

Every node loop has a **yield point** — a moment where it checks for incoming messages before continuing. This is like `await` in asyncio: it gives the event loop a chance to deliver messages, so nodes are never stuck deaf inside a long computation.

```python
class NodeLoop:
    """The core execution loop. Both coordinator and workers use this."""

    async def run(self):
        while not self.done:
            # ──── YIELD POINT ────────────────────────────────────
            # Check for incoming messages BEFORE each thinking step.
            # This is the "await" moment — the node is responsive here.
            await self.yield_point()
            # ─────────────────────────────────────────────────────

            # Think (LLM call)
            response = await self.provider.generate(
                messages=self.conversation,
                tools=self.tools
            )
            self.conversation.append(response)

            # Act (tool calls)
            if response.tool_calls:
                for tc in response.tool_calls:
                    # ──── YIELD POINT (between tool calls) ────────
                    await self.yield_point()
                    # ─────────────────────────────────────────────

                    result = await self.dispatch_tool(tc)
                    self.conversation.append(tool_result(tc, result))

                    if tc.name == "publish":
                        return

    async def yield_point(self):
        """The node's 'await' moment. Check inbox, process urgent messages."""
        # 1. Drain inbox
        messages = self.message_bus.receive(self.node_id)
        if messages:
            for msg in messages:
                self.conversation.append({
                    "role": "user",
                    "content": f"[Message from {msg.from_id}]: {msg.content}"
                })

        # 2. Let the event loop breathe (other coroutines can run)
        await asyncio.sleep(0)
```

**Why this matters:**

Without yield points, a worker deep in a 10-turn ReAct loop is deaf for the entire duration. If the human sends "stop what you're doing", the worker won't see it until it finishes.

With yield points between every LLM call and every tool call, the node checks its inbox frequently. A human message or coordinator instruction gets picked up within seconds.

### 8.3 Coordinator Is Always Live

The coordinator is special: it's the **always-live** node that never fully sleeps. Even when all workers are busy and no stage is actively reconvening, the coordinator has a background loop checking for human input.

```python
class Coordinator:
    async def run(self):
        """Coordinator main loop. Always responsive to human."""
        while not self.finished:
            # Phase 1: Plan and launch a stage
            await self.plan_stage()
            await self.launch_stage()

            # Phase 2: Monitor stage — but stay responsive
            while not self.stage_complete():
                # ──── YIELD POINT ────────────────────────
                # Check for human messages, worker messages
                await self.yield_point()
                # ─────────────────────────────────────────

                # Process any human messages immediately
                human_msgs = [m for m in self.pending_messages
                              if m.from_id == "human"]
                if human_msgs:
                    await self.handle_human_messages(human_msgs)

                # Check worker status
                await self.check_workers()

                # Short sleep before next check
                await asyncio.sleep(1)

            # Phase 3: Reconvene
            await self.reconvene()

    async def handle_human_messages(self, messages: list[Message]):
        """Process human input immediately. The coordinator is always listening."""
        for msg in messages:
            # Add to coordinator's conversation
            self.conversation.append({
                "role": "user",
                "content": f"[Human]: {msg.content}"
            })

        # Get coordinator's response (LLM call)
        response = await self.think_and_respond()

        # Coordinator might:
        # - Reply to human (logged to conversation)
        # - Forward instruction to a worker
        # - Adjust the current plan
        # - Create new work nodes
```

**The key insight:** The coordinator's monitoring loop runs continuously with 1-second ticks. At each tick it checks for human messages and worker updates. The human never waits more than ~1 second + LLM response time to get a reply from the coordinator.

### 8.4 Message Routing

**Human → Agent (default: coordinator):**
```python
# API endpoint
@app.post("/agents/{agent_id}/send")
async def send_message(agent_id: str, req: SendRequest):
    agent = agent_registry[agent_id]
    to = req.to or "coordinator"         # DEFAULT: goes to coordinator

    if to == "*":
        agent.message_bus.broadcast("human", req.content)
    else:
        agent.message_bus.send("human", to, req.content)

    # Log to conversation thread
    agent.conversation.append({
        "role": "human", "to": to, "content": req.content
    })
```

**Agent → Human:**
Any agent can message the human. Non-blocking unless using `ask_human` (which blocks the sender).

```python
# Worker sends a message to the human
send_message(to="Human", content="Should I use PostgreSQL or SQLite for this project?")

# Coordinator broadcasts status to the human
send_message(to="Human", content="Stage 1 complete. Starting synthesis.")
```

**Human → specific worker (explicit addressing):**
```python
# Human can address a specific worker
POST /agents/{id}/send
{ "to": "Alice", "content": "Focus on data center GPUs only" }
```

**Human → broadcast:**
```python
POST /agents/{id}/send
{ "to": "*", "content": "Deadline moved up. Wrap up and publish what you have." }
```

### 8.5 Human Inbox

The human's inbox collects all messages from all agents. Surfaced via configured channels:

```python
class HumanInbox:
    def receive_all(self) -> list[Message]:
        """All unread messages from any agent."""
        return self.message_bus.receive("human")

    def surface(self, message: Message):
        """Push to configured channels."""
        for channel in self.channels:
            if channel.matches(message):
                channel.deliver(message)
```

**Channels:**
- **CLI** — prints to terminal
- **Web UI** — appears in conversation panel + notification badge
- **Webhook** — posts to Slack/Discord/email

The human reads at their own pace. If a worker sent a question 2 hours ago, the human can still respond — the worker is parked, waiting, and will resume when the response arrives.

### 8.6 Conversational Thread

The persistent conversation between human and coordinator:

```python
class AgentConversation:
    """The persistent chat between human and coordinator."""
    def __init__(self, agent: Agent):
        self.agent = agent
        self.history_file = agent.path / "conversation.jsonl"

    async def human_says(self, message: str, to: str = "coordinator") -> str:
        """Human sends a message. Routes to the right recipient."""
        self.append({"role": "human", "to": to, "content": message})

        if to == "coordinator" or to == "*":
            # Coordinator picks it up at next yield point (< 1 second)
            # and responds via its normal loop
            self.agent.message_bus.send("human", "coordinator", message)
            if to == "*":
                self.agent.message_bus.broadcast("human", message)
            # Response comes async — coordinator will call agent_says()
            return None  # streamed back via events
        else:
            self.agent.message_bus.send("human", to, message)
            return f"Message delivered to {to}."

    def agent_says(self, from_id: str, message: str):
        """Agent/worker sends a message to human. Logged to conversation."""
        self.append({"role": from_id, "to": "human", "content": message})
        self.agent.human_inbox.surface(
            Message(from_id=from_id, to_id="human", content=message)
        )
```

### 8.7 Responsiveness Summary

```
┌──────────────────────────────────────────────────────┐
│  WHO          │ RESPONSIVE?  │ HOW                    │
├──────────────────────────────────────────────────────┤
│ Coordinator   │ Always       │ 1s monitoring loop     │
│               │              │ with yield_point()     │
│               │              │                        │
│ Worker        │ Between      │ yield_point() before   │
│ (harnessed)   │ turns        │ each LLM call and      │
│               │              │ between tool calls     │
│               │              │                        │
│ Worker        │ Polling      │ File-based inbox       │
│ (autonomous)  │              │ checked by runtime     │
│               │              │ bridge every Ns        │
│               │              │                        │
│ Human         │ Async        │ Reads inbox at own     │
│               │              │ pace via channels      │
└──────────────────────────────────────────────────────┘
```

The coordinator is the most responsive — it's always checking. Workers are responsive between turns. Autonomous workers are the least responsive (polled). The human is fully async.

### 8.8 Example Flow

```
Human → (default: Coordinator): "Research AI chip companies and write a report"
  Coordinator picks up within ~1s at next yield_point()
Coordinator → Human: "On it. Setting up 3 researchers for NVIDIA, AMD, Intel."
  (coordinator spawns workers, assigns nodes, enters monitoring loop)

  ... workers are running ...

Human → (default: Coordinator): "Also include Qualcomm"
  Coordinator picks up at next 1s tick
Coordinator → Human: "Got it. Adding a 4th researcher for Qualcomm."
  (coordinator creates new node + worker mid-stage)

Alice → Human: "Should I focus on data center or consumer GPUs?"
  (human sees this in their inbox — from Alice, not the coordinator)
Human → Alice: "Data center only."
  (Alice picks up at next yield_point() between tool calls, resumes)

Bob → Coordinator: "AMD MI300X benchmarks are hard to find."
  Coordinator picks up at next tick
Coordinator → Human: "Bob says AMD benchmarks are scarce. MLPerf data OK?"
Human → Coordinator: "Yes, MLPerf is fine. Also try anandtech.com."
Coordinator → Bob: "Human says MLPerf is fine. Also try anandtech.com."
  Bob picks up at next yield_point()

  (Stage 1 completes)
Coordinator → Human: "Stage 1 done. NVIDIA dominates training, AMD competitive on inference. Starting synthesis."

Human → broadcast (*): "Make sure the report includes pricing data too."
  (all workers + coordinator receive this at their next yield_point())
```

---

## 9. Event System

All runtime activity emits events. Useful for UI, logging, and debugging.

```python
@dataclass
class Event:
    type: str          # see below
    agent_id: str
    ts: float
    data: dict

# Event types:
# agent.created, agent.started, agent.paused, agent.resumed, agent.completed
# node.created, node.assigned, node.started, node.completed, node.failed
# worker.spawned, worker.idle, worker.busy, worker.stopped
# message.sent, message.received
# tool.called, tool.result
# human.question, human.response, human.nudge
# stage.started, stage.reconvened, stage.completed
# memory.written, memory.compacted
```

Events are written to an append-only log and can be streamed via WebSocket.

---

## 9.5. Trigger & Scheduling System

Agents can't be "on" all the time — they wake up, do work, and go back to sleep. The trigger system gives agents temporal agency: the ability to schedule future actions, just like a human sets alarms, reminders, and recurring calendar events.

### Trigger Types

```python
@dataclass
class Trigger:
    id: str
    agent_id: str
    type: str              # see below
    action: TriggerAction  # what to do when triggered
    status: str            # active | paused | expired | fired
    created_at: float
    metadata: dict         # type-specific config

@dataclass
class TriggerAction:
    type: str              # "wake_agent" | "run_node" | "send_message" | "run_callback"
    payload: dict          # action-specific data
```

**Six trigger types:**

#### 1. Scheduled (Cron-like)
Periodic recurring trigger. Like a cron job.

```python
# "Check HN every 2 hours"
schedule_trigger(
    type="scheduled",
    cron="0 */2 * * *",           # every 2 hours
    action={"type": "wake_agent", "payload": {"task": "Check HN for new AI posts"}}
)
```

Use for: monitoring tasks, periodic reports, data refresh cycles.

#### 2. Delayed (One-shot Timer)
Fire once after a delay. Like setting a reminder.

```python
# "Remind me to check the build in 30 minutes"
schedule_trigger(
    type="delayed",
    delay_seconds=1800,            # 30 minutes
    action={"type": "send_message", "payload": {"to": "Human", "content": "Build should be done. Want me to check?"}}
)
```

Use for: follow-ups, timeouts, deferred work.

#### 3. Time-based (Alarm Clock)
Fire at a specific wall-clock time. Like setting an alarm.

```python
# "Start the analysis at 9am Monday"
schedule_trigger(
    type="at_time",
    at="2026-02-12T09:00:00",
    action={"type": "wake_agent", "payload": {"task": "Run weekly competitive analysis"}}
)
```

Use for: deadline-driven work, scheduled reports, timed actions.

#### 4. Heartbeat (Periodic Check-in)
A lightweight periodic pulse. The agent wakes briefly, checks if anything needs attention, and goes back to sleep if not. Inspired by OpenClaw's heartbeat system.

```python
# "Check in every 30 minutes, see if anything needs my attention"
schedule_trigger(
    type="heartbeat",
    interval_seconds=1800,         # every 30 minutes
    action={"type": "wake_agent", "payload": {"task": "HEARTBEAT: Check inbox, review status, do background maintenance. If nothing needs attention, go back to sleep."}}
)
```

The heartbeat is different from a scheduled trigger: it's expected that the agent often does nothing ("HEARTBEAT_OK") and goes back to sleep. It's a check-in, not a task.

Use for: inbox monitoring, status checks, memory maintenance, proactive background work.

#### 5. Event-driven (Watch for Condition)
Fire when a specific event occurs in the system. Like a webhook.

```python
# "When node_a completes, start the synthesis"
schedule_trigger(
    type="on_event",
    event_pattern="node.completed",
    filter={"node_id": "node_a"},
    action={"type": "run_node", "payload": {"node_id": "synthesis_node"}}
)

# "When any worker messages me, wake up"
schedule_trigger(
    type="on_event",
    event_pattern="message.received",
    filter={"to": "coordinator"},
    action={"type": "wake_agent", "payload": {"task": "Process incoming message"}}
)
```

Use for: reactive workflows, dependency chaining, notification handling.

#### 6. Idle-triggered (Dead Man's Switch)
Fire if the agent has been idle (no activity) for a specified duration. Like a dead man's switch.

```python
# "If I haven't done anything for 1 hour, check in"
schedule_trigger(
    type="on_idle",
    idle_seconds=3600,             # 1 hour
    action={"type": "wake_agent", "payload": {"task": "I've been idle for an hour. Check if there's work to do or if I should report status to the human."}}
)
```

Use for: long-running infinite agents, watchdog behavior, "don't forget about me" patterns.

### Trigger Scheduler Implementation

```python
class TriggerScheduler:
    """Manages all triggers for all agents. Runs in the server process."""

    def __init__(self):
        self.triggers: dict[str, Trigger] = {}
        self._timer_tasks: dict[str, asyncio.Task] = {}

    def register(self, trigger: Trigger):
        self.triggers[trigger.id] = trigger
        self._schedule(trigger)

    def _schedule(self, trigger: Trigger):
        match trigger.type:
            case "scheduled":
                self._timer_tasks[trigger.id] = asyncio.create_task(
                    self._run_cron(trigger))
            case "delayed":
                self._timer_tasks[trigger.id] = asyncio.create_task(
                    self._run_delayed(trigger))
            case "at_time":
                delay = trigger.metadata["at"] - time.time()
                self._timer_tasks[trigger.id] = asyncio.create_task(
                    self._run_delayed(trigger, delay_override=delay))
            case "heartbeat":
                self._timer_tasks[trigger.id] = asyncio.create_task(
                    self._run_heartbeat(trigger))
            case "on_event":
                # Register with event bus
                event_bus.subscribe(
                    trigger.metadata["event_pattern"],
                    lambda e: self._fire(trigger) if matches_filter(e, trigger.metadata.get("filter")) else None
                )
            case "on_idle":
                self._timer_tasks[trigger.id] = asyncio.create_task(
                    self._run_idle_watch(trigger))

    async def _run_cron(self, trigger: Trigger):
        while trigger.status == "active":
            next_time = cron_next(trigger.metadata["cron"])
            await asyncio.sleep(next_time - time.time())
            await self._fire(trigger)

    async def _run_heartbeat(self, trigger: Trigger):
        while trigger.status == "active":
            await asyncio.sleep(trigger.metadata["interval_seconds"])
            await self._fire(trigger)

    async def _run_delayed(self, trigger: Trigger, delay_override=None):
        delay = delay_override or trigger.metadata["delay_seconds"]
        await asyncio.sleep(delay)
        await self._fire(trigger)
        trigger.status = "expired"

    async def _run_idle_watch(self, trigger: Trigger):
        while trigger.status == "active":
            agent = get_agent(trigger.agent_id)
            idle_time = time.time() - agent.last_activity
            if idle_time >= trigger.metadata["idle_seconds"]:
                await self._fire(trigger)
                # Reset idle timer
                agent.last_activity = time.time()
            await asyncio.sleep(60)  # check every minute

    async def _fire(self, trigger: Trigger):
        action = trigger.action
        agent = get_agent(trigger.agent_id)
        match action.type:
            case "wake_agent":
                await agent.wake(action.payload.get("task", "Triggered wake"))
            case "run_node":
                agent.scheduler.activate_node(action.payload["node_id"])
            case "send_message":
                agent.message_bus.send(
                    from_id="system",
                    to_id=action.payload["to"],
                    content=action.payload["content"])
            case "run_callback":
                await action.payload["callback"]()
```

### Tools for Agents

Agents can create and manage their own triggers:

```python
TRIGGER_TOOLS = {
    "schedule": {
        "description": "Schedule a future action. Types: 'delayed' (fire once after N seconds), "
                       "'at_time' (fire at a specific time), 'scheduled' (recurring cron), "
                       "'heartbeat' (periodic check-in).",
        "params": {
            "type": "str — delayed | at_time | scheduled | heartbeat",
            "config": "dict — type-specific: {delay_seconds, at, cron, interval_seconds}",
            "action": "str — what to do when triggered (task description)",
        },
    },
    "list_triggers": {
        "description": "List all your active triggers.",
        "params": {},
    },
    "cancel_trigger": {
        "description": "Cancel a scheduled trigger by ID.",
        "params": {"trigger_id": "str"},
    },
}
```

**Example usage by an agent:**
```
# Coordinator sets up monitoring for an infinite game
schedule(type="heartbeat", config={"interval_seconds": 1800},
         action="Check inbox for messages. Review worker status. If any workers are stuck, intervene.")

schedule(type="scheduled", config={"cron": "0 9 * * MON"},
         action="Generate weekly summary report and send to Human.")

schedule(type="delayed", config={"delay_seconds": 3600},
         action="Check if the coding task is still running. If stuck, abort and reassign.")
```

### Persistence

Triggers are persisted to `agents/{agent_id}/triggers.json` so they survive server restarts. On startup, the scheduler loads all active triggers and re-registers them.

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
