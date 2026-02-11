# Agiraph v2 — Test Handbook

## Quick Start

### Prerequisites
```bash
# Python deps (should already be installed)
pip install fastapi uvicorn httpx markdownify anthropic openai pydantic python-dotenv websockets pytest

# Frontend deps
cd frontend && npm install && cd ..
```

### Run Unit Tests (No API keys needed)
```bash
python -m pytest tests/ -v
```

All 40 unit tests should pass. These test:
- Core data structures (models, board, workers)
- Message bus (send, receive, broadcast, peek)
- Event bus (emit, recent, pagination)
- Tool definitions and registry (25 tools)
- Provider factory and adapter format functions
- Path resolution and security (traversal prevention)
- API endpoints (create, list, get, delete agents + all sub-resources)

---

## Integration Testing (Requires API Keys)

### Setup `.env`
```bash
# Required for any LLM-powered test
ANTHROPIC_API_KEY=sk-ant-...

# Optional: OpenAI provider
OPENAI_API_KEY=sk-...

# Optional: Web search (needed for research tasks)
BRAVE_API_KEY=...        # or
SERPER_API_KEY=...
```

### Test 1: Smoke Test (Single Agent, Simple Task)
```bash
# Start the server
python -m agiraph.server &

# Create a simple agent
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{"goal": "What are the top 3 programming languages in 2026? Write your answer to a file.", "model": "anthropic/claude-sonnet-4-5"}'

# Watch it work (poll status)
curl http://localhost:8000/agents  # check status
curl http://localhost:8000/agents/{id}/events  # see events
curl http://localhost:8000/agents/{id}/conversation  # see chat
```

**Expected:** Agent calls write_file and finish within 2-3 turns.

### Test 2: Multi-Turn with Tools
```bash
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{"goal": "Write a Python script that prints the Fibonacci sequence up to 100, save it to a file, and run it with bash to verify it works."}'
```

**Expected:** Agent writes code, runs it with bash, iterates if errors, finishes.

### Test 3: Multi-Agent Collaboration (Deep Research)
Requires: `BRAVE_API_KEY` or `SERPER_API_KEY`

```bash
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{"goal": "Research the current state of AI hardware — compare NVIDIA, AMD, and Intel. Spawn workers for parallel research, then synthesize into a report."}'
```

**Expected:** Coordinator spawns 3 workers, assigns research nodes, reconvenes, possibly creates synthesis node.

### Test 4: Human-in-the-Loop
```bash
# Create agent that will need human input
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{"goal": "Set up a database for our project. Ask the human which database to use."}'

# Watch for ask_human event
curl http://localhost:8000/agents/{id}/events

# Respond when asked
curl -X POST http://localhost:8000/agents/{id}/respond \
  -H "Content-Type: application/json" \
  -d '{"response": "Use PostgreSQL, it is for a production web app"}'
```

**Expected:** Agent asks human, pauses, receives response, continues.

### Test 5: Nudge (Human Sends Message Mid-Work)
```bash
# Create a research agent
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{"goal": "Research Python web frameworks and write a comparison"}'

# While it's working, send a nudge
curl -X POST http://localhost:8000/agents/{id}/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Focus specifically on FastAPI vs Django, ignore Flask"}'
```

**Expected:** Coordinator receives the message at next yield point and adjusts.

---

## Frontend Testing

### Start Both Servers
```bash
# Terminal 1: Backend
python -m agiraph.server

# Terminal 2: Frontend
cd frontend && npm run dev
```

### Manual UI Test Checklist
- [ ] Home page shows agent list (empty initially)
- [ ] Create agent form works (goal, model, mode selectors)
- [ ] After creating, auto-navigates to agent detail
- [ ] Sidebar shows Coordinator, workers appear as they spawn
- [ ] Chat panel shows conversation messages
- [ ] Can type and send messages to the agent
- [ ] Work Board tab shows nodes with status icons
- [ ] Files tab browses workspace directories
- [ ] Memory tab browses memory directory
- [ ] Events tab shows live event stream
- [ ] Yellow banner appears for ask_human questions
- [ ] Can respond to questions via the response input
- [ ] Worker status dots change color (blue=working, green=done)
- [ ] Agent status updates in real-time
- [ ] Delete agent works from home page

---

## What Needs Human Help (Morning Setup)

### Required API Keys
1. **ANTHROPIC_API_KEY** — Required for any LLM-powered agent. Get from https://console.anthropic.com/
2. **BRAVE_API_KEY** or **SERPER_API_KEY** — Required for web search tool. Without this, agents can't search the web.
   - Brave: https://brave.com/search/api/
   - Serper: https://serper.dev/

### Optional
3. **OPENAI_API_KEY** — Only if testing OpenAI models (GPT-4o, o3-mini)

### Create `.env` File
```bash
cat > .env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-your-key-here
BRAVE_API_KEY=your-brave-key-here
# OPENAI_API_KEY=sk-your-key-here
EOF
```

---

## Architecture Notes for Testing

- Agent data stored in `./agents/{id}/` — each agent gets its own directory
- Runs stored in `./agents/{id}/runs/{run_id}/`
- Events logged to `./agents/{id}/events.jsonl`
- All state is files — you can inspect `agents/` directory at any time
- Server is stateful (in-memory agent registry) — restarting loses running agents
- WebSocket at `ws://localhost:8000/agents/{id}/events` for live streaming
