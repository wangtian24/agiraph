<p align="center">
  <img src="giraffe.png" alt="Agiraph Logo" width="200" />
</p>

# Agiraph

Autonomous AI agent framework with emergent graph collaboration. One agent, one goal — it self-organizes, spawns workers, accumulates knowledge, and only bothers humans when it has to.

## What It Does

Give an agent a goal. It figures out the rest:

- **Simple tasks** — the coordinator works alone, using tools directly
- **Complex tasks** — spawns a team of workers, assigns nodes, reconvenes when they're done
- **Research tasks** — parallel web search, synthesis, structured reports
- **Coding tasks** — can launch autonomous agents (Claude Code CLI) as workers

The graph of work **emerges** as the agent runs — it's not planned upfront.

## Quick Start

### 1. Install (Python backend)

```bash
poetry install
```

### 2. Install (Frontend)

```bash
cd frontend && npm install && cd ..
```

### 3. Configure API Keys

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-your-key-here

# For web search (pick one)
BRAVE_API_KEY=your-brave-key
# SERPER_API_KEY=your-serper-key

# Optional
# OPENAI_API_KEY=sk-your-key
```

### 4. Start the Backend

```bash
poetry run python -m agiraph.server
```

Server runs at `http://localhost:8000`.

### 5. Start the Frontend

```bash
cd frontend && npm run dev
```

UI runs at `http://localhost:3000`.

### 6. Create an Agent

**Via the UI:** Open `http://localhost:3000`, type a goal, pick a model, click Create.

**Via curl:**

```bash
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{"goal": "What are the top 3 AI hardware companies? Research each and produce a short comparison.", "model": "anthropic/claude-sonnet-4-5"}'
```

### 7. Watch It Work

- **UI:** Click into the agent — see the chat, work board, files, and live events
- **API:** Poll `GET /agents/{id}` for status, `/agents/{id}/events` for events, `/agents/{id}/board` for work nodes
- **WebSocket:** Connect to `ws://localhost:8000/agents/{id}/events` for real-time streaming

## Try These

**Simple (single agent, no workers):**
```bash
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{"goal": "Write a Python script that computes the first 20 Fibonacci numbers. Save it to a file and run it to verify."}'
```

**Multi-agent research:**
```bash
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{"goal": "Research the competitive landscape of AI hardware. Spawn 3 researchers for NVIDIA, AMD, and Intel in parallel, then synthesize into a comparison report."}'
```

**Human-in-the-loop:**
```bash
# Create agent that needs human input
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{"goal": "Set up a database for our project. Ask the human which database to use before proceeding."}'

# When the agent asks, respond:
curl -X POST http://localhost:8000/agents/{id}/respond \
  -H "Content-Type: application/json" \
  -d '{"response": "PostgreSQL"}'
```

**Nudge a running agent:**
```bash
curl -X POST http://localhost:8000/agents/{id}/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Also include Qualcomm in the comparison"}'
```

## How It Works

```
Goal → Coordinator (ReAct loop)
          │
          ├── works alone (simple tasks)
          │
          └── spawns workers (complex tasks)
                ├── Worker A (harnessed: API-driven ReAct loop)
                ├── Worker B (harnessed: different model)
                └── Worker C (autonomous: Claude Code subprocess)
                      │
                      └── sub-workers (recursive spawning)
```

**Two node types:**
- **Harnessed** — we manage the loop (prompt → LLM → tool calls → repeat)
- **Autonomous** — external agent (Claude Code CLI) runs its own loop

**Two game modes:**
- **Finite** — bounded task, agent exits when done
- **Infinite** — ongoing purpose, agent runs in cycles

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/agents` | POST | Create a new agent |
| `/agents` | GET | List all agents |
| `/agents/{id}` | GET | Agent status |
| `/agents/{id}` | DELETE | Stop and remove |
| `/agents/{id}/send` | POST | Send message (human → agent) |
| `/agents/{id}/respond` | POST | Respond to ask_human question |
| `/agents/{id}/conversation` | GET | Chat history |
| `/agents/{id}/board` | GET | Work nodes and status |
| `/agents/{id}/board/{node_id}` | GET | Single node detail |
| `/agents/{id}/workers` | GET | Active workers |
| `/agents/{id}/workspace` | GET | Browse workspace files |
| `/agents/{id}/memory` | GET | Browse memory files |
| `/agents/{id}/events` | GET | Recent events (polling) |
| `/agents/{id}/events` | WS | Live event stream |

## Project Structure

```
agiraph/                    # Python package
├── agent.py                # Agent — top-level entity
├── coordinator.py          # Coordinator — always-live ReAct loop
├── worker.py               # Harnessed + Autonomous worker execution
├── scheduler.py            # Work board management, node assignment
├── models.py               # Data structures (WorkNode, Worker, Board, etc.)
├── message_bus.py          # Inter-entity messaging
├── events.py               # Append-only event log + WebSocket
├── server.py               # FastAPI server (15 endpoints)
├── config.py               # Configuration from .env
├── tools/
│   ├── definitions.py      # 25 built-in tool definitions
│   ├── implementations.py  # Tool logic (bash, web_search, publish, etc.)
│   ├── registry.py         # Tool dispatch
│   ├── context.py          # Runtime context for tools
│   └── setup.py            # Wires definitions to implementations
└── providers/
    ├── anthropic_provider.py
    ├── openai_provider.py
    └── text_fallback.py    # For models without native tool calling

frontend/                   # Next.js + TypeScript + Tailwind
├── src/app/page.tsx        # Home — agent list + create form
├── src/app/agents/[id]/    # Agent detail — Slack-like entity view
├── src/hooks/useAgent.ts   # Polling + WebSocket hook
└── src/lib/api.ts          # API client

tests/                      # 40 unit tests
```

## Running Tests

```bash
# Unit tests (no API keys needed)
poetry run pytest tests/ -v

# All 40 should pass
```

See `tests/TEST_HANDBOOK.md` for integration testing steps.

## Supported Models

| Provider | Models |
|---|---|
| Anthropic | claude-sonnet-4-5, claude-opus-4-6, claude-haiku-4-5 |
| OpenAI | gpt-4o, o3-mini |

Use the format `provider/model` when creating agents (e.g., `anthropic/claude-sonnet-4-5`).
