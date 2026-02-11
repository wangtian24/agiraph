# Agiraph v2-A — Technical Design: Part 1 — Core Concepts

**Part 1 of 4** | [Part 2: Runtime](./v2-A-technical-2-runtime.md) | [Part 3: Memory & Human](./v2-A-technical-3-memory-human.md) | [Part 4: Implementation](./v2-A-technical-4-implementation.md)
**Date:** 2026-02-11

_Covers: Emergent graphs, data scopes, the conversational agent, work nodes vs workers._

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

