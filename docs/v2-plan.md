# Agiraph v2 — Overall Plan

**Date:** 2026-02-11

---

## What Agiraph Is

An **agent orchestration runtime** where you spin up AI workers — each one a persistent, interactive agent backed by a graph-based execution engine. Think OpenAI Frontier's "AI coworkers" concept, but open, self-hosted, and model-agnostic.

Each agent is a lightweight loop we manage: think, act, observe, repeat. Agents can interact with humans for guidance, persist their state and memory across sessions, and collaborate with other agents.

---

## Top-Level Concepts

### 1. Agents as Spawnable Workers
- **Spawn an agent** with a name, role, and prompt — it starts working immediately
- Each agent run is a **graph execution** under the hood (our core primitive)
- Agents are cheap to create — spin up 1 or 100, each runs its own loop
- Mixed models per agent (Claude for reasoning, GPT for grunt work, local for cost)

### 2. Lightweight Agent Loop (Our Harness)
- We manage the ReAct loop: check messages → think → act (tool call) → observe → repeat
- Built-in tools: file I/O, web search, messaging, checkpoint, spawn sub-agents
- MCP integration for external tools (databases, APIs, custom servers)
- Context compaction when conversation grows long — workspace files are durable memory

### 3. Human-in-the-Loop Interaction
- Agents can **ask humans** for clarification, approval, or new instructions mid-run
- `ask_human(question)` tool pauses the agent and surfaces the question via API/UI
- Human responses injected back into the agent's conversation
- Agents can also be **nudged** — humans push new instructions into a running agent
- Support async interaction: agent parks, human responds hours later, agent resumes

### 4. Persistent Agents with Memory
- Agent state is **serializable**: conversation history, workspace files, tool state
- **Pause and resume** — stop an agent, persist to disk/DB, bring it back later
- **Durable memory** — each agent has a memory store (files + structured KV) that survives across sessions
- An agent can be re-activated days later with full context: "pick up where you left off"
- Memory compaction: summarize old context, keep recent turns fresh

### 5. Multi-Agent Collaboration
- Agents communicate via **named messaging** ("send a message to Alice")
- **Coordinator pattern**: a lead agent assembles a team, assigns roles, manages stages
- **Stages and reconvene**: parallel work → checkpoint → coordinator assesses → next stage
- Shared workspace on filesystem — each agent has its own directory, can read others'
- Agents can **spawn sub-agents** for delegation

### 6. Identity and Permissions
- Each agent has an **identity**: name, role title, capabilities, allowed tools
- **Permission boundaries**: which files an agent can write, which tools it can call, which APIs it can access
- Audit trail: all tool calls, messages, and state transitions are logged

---

## Architecture (Simplified)

```
                    ┌─────────────────────────────┐
                    │        HUMAN / API           │
                    │  spawn, nudge, respond, view │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │       AGENT MANAGER          │
                    │  spawn / pause / resume /    │
                    │  persist / list / destroy    │
                    └─────────────┬───────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
        ┌───────────┐      ┌───────────┐      ┌───────────┐
        │  Agent A  │      │  Agent B  │      │  Agent C  │
        │  (API)    │◄────►│  (API)    │◄────►│ (Agentic) │
        └─────┬─────┘      └─────┬─────┘      └─────┬─────┘
              │                  │                   │
              └──────────────────┼───────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │    SHARED WORKSPACE     │
                    │  + Agent Memory Stores  │
                    └─────────────────────────┘
                         │             │
                    ┌────▼────┐  ┌─────▼──────┐
                    │ Models  │  │ MCP / Tools │
                    │ (any)   │  │ (external)  │
                    └─────────┘  └────────────┘
```

---

## Agent Lifecycle

```
spawn(name, role, prompt)
    │
    ▼
 RUNNING ◄──── resume(agent_id)
    │               ▲
    ├── working      │
    ├── waiting_for_human ──► human responds ──► RUNNING
    ├── checkpoint (stage done)
    │
    ▼
 PAUSED ───► persist to disk/DB
    │
    ▼
 COMPLETED / RETIRED
    │
    ▼
 Memory persists (reusable by future agents or same agent re-spawned)
```

---

## Key APIs

```python
from agiraph import AgentManager

mgr = AgentManager()

# Spawn an agent
agent = mgr.spawn(
    name="Alice",
    role="Market Analyst",
    model="anthropic/claude-sonnet-4-5",
    prompt="Research AI chip market and write a report.",
    tools=["web_search", "web_fetch", "file_io"],
)

# Agent runs autonomously, can ask human questions
# Poll or subscribe to events:
for event in agent.events():
    if event.type == "ask_human":
        answer = input(event.question)
        agent.respond(answer)
    elif event.type == "completed":
        print(agent.result)

# Nudge a running agent
agent.nudge("Also look into Qualcomm's AI chips.")

# Pause and persist
agent.pause()
state = agent.serialize()  # → JSON/bytes, saveable to DB

# Later: resume
agent = mgr.resume(state)

# Multi-agent collaboration
team = mgr.spawn_team(
    coordinator_model="anthropic/claude-opus-4-6",
    prompt="Analyze AI chip competitive landscape",
    # coordinator decides roles, stages, etc.
)
```

---

## Implementation Phases

### Phase 1: Core Agent Loop
- Single agent with ReAct loop (think → act → observe)
- Tool registry + provider adapters (Anthropic, OpenAI)
- File-based workspace
- `checkpoint()` and `finish()` tools

### Phase 2: Human Interaction
- `ask_human()` tool — pauses agent, surfaces question
- `nudge()` API — inject instructions into running agent
- Event stream API for external consumers

### Phase 3: Persistence
- Serialize/deserialize agent state (conversation + workspace + metadata)
- Pause/resume lifecycle
- Agent memory store (persists across sessions)

### Phase 4: Multi-Agent Collaboration
- Message queue between agents
- Coordinator pattern: stages, reconvene, re-plan
- `spawn_agent()` tool for delegation
- Shared workspace with per-agent directories

### Phase 5: Agentic Nodes
- Launch external agents (Claude Code, etc.) as subprocesses
- File-based inbox/outbox bridging
- Mixed teams: API nodes + agentic nodes

### Phase 6: Context Management + Robustness
- Token counting and conversation compaction
- Text fallback adapter for models without tool calling
- Error handling, retries, timeouts, deadlock detection
- Cost tracking per agent

### Phase 7: Frontend + Observability
- Agent dashboard: list agents, status, memory usage
- Live event stream visualization
- Message log viewer
- Human interaction panel (respond to agent questions)

---

## What Makes This Different

| | Agiraph | OpenAI Frontier | LangGraph | CrewAI |
|---|---|---|---|---|
| **Model lock-in** | Any model | OpenAI only | Any (via LangChain) | Any |
| **Self-hosted** | Yes | No (SaaS) | Yes | Yes |
| **Persistent agents** | Yes | Yes | Checkpointing | No |
| **Human-in-loop** | Native | Via platform | Manual | Limited |
| **Agent collaboration** | Named roles + messaging | Platform-managed | Graph edges | Role-based |
| **External agent support** | Yes (Claude Code, etc.) | Third-party agents | No | No |
| **Runtime weight** | Lightweight Python | Enterprise platform | Framework | Framework |

---

## Design Principles

1. **Agents are workers, not functions.** They have identity, memory, and can be talked to.
2. **The runtime is thin.** Coordination + tool dispatch. All heavy compute is remote LLM calls.
3. **Files are truth.** Workspace = durable state. Conversation = disposable working memory.
4. **Humans are in the loop, not in the way.** Agents ask when stuck, humans nudge when needed. Async by default.
5. **Persistence is first-class.** An agent you spawned today should be resumable next week.
6. **Model-agnostic.** Pick the right model for each agent's job. No vendor lock-in.

---

*Previous design docs (v2-design.md, v2-autonomous-design.md, v2-autonomous-detailed.md) are subsumed by this plan. They remain as reference for detailed implementation specifics.*
