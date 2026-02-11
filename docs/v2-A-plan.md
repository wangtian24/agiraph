# Agiraph v2-A — One Agent, Big Goals

**Date:** 2026-02-11

---

## The Idea

One autonomous agent that can run for a really long time to finish something big. It self-organizes, accumulates knowledge, spawns sub-agents when needed, and only bothers humans when it has to. Model-independent. The runtime is a thin harness — all intelligence is in the models.

Two modes: **finite game** (bounded task, agent exits when done) and **infinite game** (long-running agent with an ongoing purpose, runs until told to stop).

---

## Two Node Types

Every unit of work is a **node**. Nodes come in two flavors:

### Harnessed Node
We manage the loop. The model is a dumb API call — we feed it context, get a response, execute tool calls, repeat. Can be tuned from **single-inference** (one shot, no loop) to **multi-turn** (full ReAct loop with iterations).

Good for: cheap models, simple tasks, structured extraction, summarization, any case where you want control over the loop.

```
[Our Runtime]
    │
    ├─ build prompt (system + context + messages)
    ├─ call model API → get response
    ├─ parse tool calls → execute tools
    ├─ append results → loop or finish
    │
    └─ we control everything: retries, compaction, token limits
```

### Autonomous Node
An external agent that runs itself. We launch it, give it a task (via prompt/files/CLI args), and wait for it to signal completion. The agent has its own tools, its own loop, its own everything. We just bridge messages and watch for the checkpoint signal.

Good for: Claude Code, coding tasks, complex research, anything where an existing agent runtime is better than our harness.

```
[Our Runtime]
    │
    ├─ write task to files / pass as CLI args
    ├─ launch subprocess (claude-code, etc.)
    ├─ bridge messages via inbox/outbox files
    ├─ poll for _checkpoint.md
    │
    └─ we control nothing inside — the agent is fully autonomous
```

A single collaboration can mix both: a harnessed coordinator managing a team of harnessed workers and autonomous Claude Code nodes.

---

## The Agent

An **agent** is a top-level entity you create with a goal. Under the hood, it's a coordinator node that manages a collaboration. But from the outside, it's one thing: give it a goal, it works on it.

```python
agent = agiraph.create(
    goal="Build a production-ready REST API for a todo app with tests and docs",
    model="anthropic/claude-sonnet-4-5",  # coordinator model
    mode="finite",  # or "infinite"
)

agent.run()  # blocks until done, or runs forever for infinite mode
```

The agent decides internally whether to work alone or spawn a team, how many stages to run, when to reconvene, and when it's done.

---

## Collaboration Model

Carried forward from v2 design — this still works.

### Coordinator + Roles
The agent's root node is a **coordinator**. It analyzes the goal, decides team shape, and launches roles. Each role is a node (harnessed or autonomous).

### Stages and Reconvene
Work happens in **stages**. All roles in a stage work in parallel. When all checkpoint, the coordinator reconvenes: reads outputs, assesses progress, plans next stage. Roles can persist, retire, or be introduced across stages.

### Recursive Spawning
Any node can spawn sub-agents. A manager node spawns workers. A worker can spawn its own sub-workers if the task is complex enough. The graph grows recursively. The spawning node blocks until children complete.

### Messaging
Roles communicate by name. Messages are free-form text delivered via in-memory queue (logged to files). Roles check messages between work steps.

### Collaboration Contract
The coordinator defines rules upfront: max stages, checkpoint policy, which roles can read/write where. Written to `_plan.md` in the workspace so all roles can see it.

### Shared Workspace
All state is files on disk. Each role has its own directory. Roles can read each other's directories but only write to their own. The coordinator reads everything.

---

## Memory and Knowledge

This is the new piece. The agent accumulates knowledge over its lifetime.

### Three Layers

**Working memory** — the conversation history in each node's loop. Disposable. Gets compacted when it grows too long. Anything important should be written to files.

**Workspace memory** — files written during the current run. Each role writes findings, artifacts, notes to its workspace directory. Survives context compaction. Scoped to the current collaboration.

**Long-term memory** — persists across runs and sessions. The agent's accumulated knowledge, experiences, lessons learned. Stored in a dedicated memory directory. Self-organized by the agent itself.

```
/agents/{agent_id}/
├── workspace/           # Current run's workspace (roles, outputs, messages)
│   ├── _plan.md
│   ├── alice/
│   ├── bob/
│   └── ...
├── memory/              # Long-term memory (persists across runs)
│   ├── knowledge/       # Facts, research findings, domain knowledge
│   ├── experiences/     # What worked, what didn't, lessons learned
│   ├── preferences/     # How the human likes things done
│   └── index.md         # Self-maintained index of what's stored
└── state.json           # Serialized agent state (for pause/resume)
```

### Self-Organizing Memory

The agent is prompted to manage its own memory:
- After completing a task, reflect: *"What did I learn? What should I remember?"*
- Write to `memory/` with its own chosen structure
- Maintain `memory/index.md` as a table of contents
- At the start of a new run, load relevant memories into context
- Periodically consolidate: merge related notes, prune outdated info

We don't impose a schema on memory. The agent decides how to organize it. We just provide the directory and the tools to read/write it.

### Knowledge Accumulation

Over time, an agent builds up:
- **Domain expertise** — facts and data it has researched
- **Procedural knowledge** — how to do specific tasks well
- **Relationship context** — what the human cares about, communication preferences
- **Meta-knowledge** — which models work best for which tasks, which tools are reliable

This makes long-running (infinite game) agents increasingly effective over time.

---

## Human Access Points

The agent runs autonomously. Humans interact sporadically.

### Agent → Human
- `ask_human(question, channel)` — agent needs input, sends question via specified channel
- Channels: CLI prompt, webhook (Slack/Discord/email), API callback, web UI
- Agent **parks** (pauses that node) while waiting — other nodes can keep working
- If no response within a timeout, agent can proceed with its best guess or escalate

### Human → Agent
- `nudge(message)` — inject new instructions into a running agent
- Message goes to the coordinator, which decides how to act on it
- Can redirect the whole collaboration or just inform a specific role

### Observation
- Event stream: all node starts/stops, messages, tool calls, checkpoints
- Workspace is readable at any time (it's just files)
- Agent can produce periodic status summaries to a channel

The point: humans are **advisors**, not managers. The agent runs the show.

---

## Finite vs Infinite Game

### Finite Game
- Clear goal with a completion condition
- Agent works until goal is met, then exits
- Example: *"Build a REST API with tests"* — done when tests pass
- Workspace archived, memory retained for future agents

### Infinite Game
- Ongoing purpose without a fixed endpoint
- Agent runs continuously (or on a schedule), doing its thing
- Example: *"Monitor our competitors and keep a living report updated"*
- Runs in a loop: wake → check for changes → update outputs → sleep → repeat
- Human can adjust direction over time via nudges
- Memory grows continuously, agent gets better at its job

### Implementation Difference
Minimal. The coordinator's system prompt changes:
- Finite: *"Work until the goal is fully achieved, then conclude."*
- Infinite: *"This is an ongoing mission. After each cycle, assess what's changed and plan your next action. Never conclude — checkpoint and wait for the next cycle."*

The runtime just needs a scheduler for infinite agents (cron-like wake/sleep cycle).

---

## Implementation Phases

### Phase 1: Single Harnessed Agent
- ReAct loop for harnessed nodes (think → act → observe)
- Tool registry + provider adapters (Anthropic, OpenAI)
- Workspace file I/O
- `finish()` to complete
- **Test:** Single agent uses tools across multiple turns to complete a task

### Phase 2: Multi-Agent Collaboration
- Coordinator node that spawns roles
- Stages + checkpoint + reconvene
- Message queue between roles
- Collaboration contract in `_plan.md`
- Recursive spawning (roles spawn sub-roles)
- **Test:** Coordinator creates 3 roles, they work in parallel, coordinator reconvenes and runs stage 2

### Phase 3: Autonomous Nodes
- Launch external agent (Claude Code CLI) as subprocess
- Task via files/CLI args, result via checkpoint file
- Message bridging via inbox/outbox files
- Mixed teams: harnessed + autonomous nodes
- **Test:** Coordinator assigns coding task to Claude Code node, research to harnessed node, synthesizes

### Phase 4: Memory and Persistence
- Long-term memory directory structure
- Agent prompted to self-organize memory
- Memory loading at run start (relevant memories into context)
- Pause/resume: serialize agent state, restore later
- **Test:** Agent runs a task, writes memories. New run loads those memories and benefits from them

### Phase 5: Human Access Points
- `ask_human()` tool with channel support
- `nudge()` API
- Event stream for observation
- Async: agent parks while waiting for human
- **Test:** Agent asks human a question via CLI, receives answer, continues

### Phase 6: Infinite Game Mode
- Scheduler for recurring agent cycles
- Wake/sleep loop
- Continuous memory accumulation
- Status reporting to channels
- **Test:** Agent monitors a topic, updates report daily, improves over a week

### Phase 7: Context Management + Robustness
- Token counting and conversation compaction
- Text fallback for non-tool-calling models
- Error handling, retries, timeouts
- Deadlock detection in multi-agent graphs
- Cost tracking per node

### Phase 8: Frontend
- Agent dashboard: active agents, status, memory size
- Live event stream
- Workspace file browser
- Human interaction panel
- Message log viewer

---

## Design Principles

1. **One agent, one goal.** The agent is the unit of deployment. Give it a goal, it figures out the rest.
2. **Two node types, one interface.** Harnessed or autonomous — the coordinator doesn't care how a role does its work.
3. **Memory is the moat.** An agent that remembers and learns is worth more than one that doesn't. Memory is self-organized, not schema'd.
4. **Autonomy first, humans second.** The agent runs the show. Humans advise when asked or nudge when inspired.
5. **Finite and infinite are the same machine.** The only difference is whether the coordinator concludes or loops.
6. **Files are truth.** Workspace = state. Conversation = disposable. If it matters, write it down.
7. **The runtime is thin.** Loop management, tool dispatch, message routing. That's it. Intelligence is in the models.
