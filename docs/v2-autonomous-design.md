# Agiraph v2 — Autonomous Role-Based Collaboration

**Status:** Design
**Date:** 2026-02-08
**Version:** 2.0.0

---

## 1. Vision

Agiraph v2 replaces the v1 "presplit task" model with **autonomous role-based collaboration**. Instead of a planner breaking work into tasks and assigning them to models, a coordinator assembles a team of named roles — like staffing a company — and lets them work autonomously, coordinating through a shared workspace and message passing.

**v1:** Planner says *"here are 5 things to do, go do them."*
**v2:** Coordinator says *"this problem needs a market analyst, a coder, and a writer. Here are your briefs — figure out what to do."*

---

## 2. Core Concepts

### Roles, not tasks

The unit of work is a **role**, not a task. A role has a name (human name like "Alice"), a domain ("Market Analyst"), and a detailed prompt that gives it enough context to self-direct. The role decides what actions to take — the coordinator doesn't prescribe steps.

### Two node types

| | API Node | Agentic Node |
|---|---|---|
| **Model** | Any LLM via API | Claude Code, or similar |
| **Who runs the loop** | Our harness | The external agent |
| **Tools** | Provided by our runtime | Agent's own (bash, git, etc.) |
| **Good for** | Simple roles, cheap models | Coding, complex research, tool-heavy work |
| **Harness role** | Full orchestration | Launch, monitor, bridge messages |

Both node types look the same to the coordinator: a workspace directory, a message queue, and a checkpoint signal.

### Stages and reconvene

Work proceeds in **stages**. Each stage has a set of active roles working in parallel. A stage ends when all roles call `checkpoint()`. The coordinator then **reconvenes** — reads all outputs, assesses progress, and decides the next stage. Roles can persist across stages or be retired/introduced.

### Shared workspace (filesystem)

All state is files on disk. Each role has its own directory and reads/writes files there. No key-value store, no fixed schema. The coordinator reads everything. Roles can read each other's directories but only write to their own.

### Message passing

Roles communicate by name ("send a message to Alice"). Messages are delivered via in-memory queue for speed, logged to files for observability. Roles check messages in their loop between work steps.

### Collaboration contract

The coordinator defines operating rules upfront: how many stages, checkpoint policy, which roles read/write which areas. This is written to the workspace as `_plan.md` so all roles can read it.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────┐
│  COORDINATOR (persists across stages, smarter model)     │
│                                                          │
│  Stage 1: Plan → launch roles → wait for checkpoints    │
│  Reconvene: Read outputs → decide next stage            │
│  Stage 2: Adjust roles → launch → wait                  │
│  ...                                                     │
│  Final: Produce output                                   │
└──────────────────┬───────────────────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ Alice   │  │ Bob     │  │ Carol   │
│ Market  │  │ Engineer│  │ Writer  │
│ Analyst │  │         │  │         │
│ (API)   │  │(Agentic)│  │ (API)   │
└────┬────┘  └────┬────┘  └────┬────┘
     │            │            │
     └────────────┼────────────┘
                  ▼
     ┌─────────────────────────┐
     │  SHARED WORKSPACE       │
     │  /workspace/            │
     │    _plan.md             │
     │    _messages/           │
     │    alice/               │
     │    bob/                 │
     │    carol/               │
     └─────────────────────────┘
```

---

## 4. Runtime

The runtime is a **single lightweight Python process** that makes remote API calls. All heavy compute (LLM inference) is remote. It can run anywhere with internet access and a filesystem.

**Components:**
- **Coordinator loop** — manages stages, reconvenes, re-plans
- **Role launcher** — starts API nodes (internal agentic loop) or Agentic nodes (external agent subprocess)
- **Message broker** — in-memory queue with file logging
- **Tool registry** — defines tools once, adapts to provider format
- **Provider adapter** — handles native tool calling vs. text-prompt fallback
- **Context manager** — tracks token usage per role, triggers compaction

**No checkpointing required** for now — workspace files provide durability, and runs are short enough that crash recovery = re-run.

---

## 5. Tool System

Tools are defined once in a registry with schema + Python implementation. The provider adapter translates schemas to the model's expected format.

**For models with native tool calling** (Claude, GPT-4, Gemini): schemas sent via API, structured tool_call responses parsed.

**For models without native tool calling**: schemas injected into the system prompt as text, tool calls parsed from model output via markers.

**Built-in tools** (available to API nodes):
- `read_file`, `write_file`, `list_files` — workspace access
- `check_messages`, `send_message` — role-to-role communication
- `checkpoint` — signal phase completion
- `web_search`, `web_fetch` — external information

**Agentic nodes** use their own tools (bash, git, github, etc.) and interact with the coordination layer through file-based inbox/outbox.

---

## 6. Context Management

Each API node's agentic loop accumulates conversation history. The workspace serves as **long-term memory** — roles write findings to files as they go. The conversation is **working memory** — compactable.

When token count approaches the model's context limit, the runtime compacts: rebuild context from system prompt + workspace files + recent turns. Nothing important is lost because durable artifacts are on disk.

Roles are prompted: *"Write important findings to your workspace files as you go. Your conversation history may be compacted — anything not written to a file may be forgotten."*

---

## 7. Frontend (MVP)

Text-oriented table UI:
- Current stage and progress
- Role table: name, role type, status (working / checkpointed / retired)
- Expandable: shared workspace files, message log, coordinator reasoning

Full graph visualization deferred to later version.

---

## 8. Design Principles

1. **One line to start, thirty lines for full control.** `team("do X")` is the front door. Everything else is progressive disclosure.
2. **Unix philosophy.** Small files, small functions, no inheritance. ~10 files. Entire codebase readable in 30 minutes.
3. **Roles are autonomous.** The coordinator sets direction, not steps.
4. **Files are truth.** The workspace is the shared state. No hidden in-memory state that matters.
5. **The runtime is thin.** It's a coordination layer, not an execution engine. Heavy work is remote.
6. **Node type is pluggable.** API node, Claude Code, future agents — the coordinator doesn't care how a role does its work.
7. **Model freedom.** Any provider with an API key in `.env`. No provider-specific code in the core.
8. **Humans work this way.** Roles have names, send messages, write documents, check in at meetings. The metaphor is a small team, not a DAG.

---

## 9. Related Documents

- [Detailed Design](./v2-autonomous-detailed.md) — implementation spec, data structures, pseudocode
- [Competitive Landscape](./v2-competitive-landscape.md) — top 10 competitors, positioning, market trends
- [User Stories & Progressive API](./v2-user-stories.md) — from 1-line to full control, file structure
