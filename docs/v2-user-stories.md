# Agiraph v2 — User Stories & Progressive API

**Date:** 2026-02-09

---

## Design Goal

One line to start. Thirty lines for full control. Each layer is independently usable. No magic — just functions calling functions.

---

## Story 1: "I just want results" (1 line)

```python
from agiraph import team

result = team("Compare NVIDIA and AMD's AI chip strategies")
print(result)
```

What happens under the hood:
1. Reads `.env` for available API keys
2. Picks the best available model for coordinator
3. Coordinator decides team shape (e.g., 2 researchers + 1 synthesizer)
4. Roles work in parallel in a temp workspace
5. Returns final output as a string

---

## Story 2: "I want to watch it work" (3 lines)

```python
from agiraph import team

for event in team("Research X and write a report", stream=True):
    print(event)
```

Output:
```
[coordinator] Planning team for: "Research X and write a report"
[coordinator] Stage 1: Research — Alice (Researcher), Bob (Researcher)
[alice] Started — researching aspect A
[bob] Started — researching aspect B
[alice → bob] "I'm finding a lot on topic Y, are you covering that?"
[bob → alice] "No, go ahead. I'm focused on Z."
[alice] Checkpointed — findings in alice/research.md
[bob] Checkpointed — findings in bob/research.md
[coordinator] Reconvene — all research complete. Stage 2: Synthesis
[carol] Started — writing report from alice/ and bob/ outputs
[carol] Checkpointed — report in carol/report.md
[coordinator] Done.
```

---

## Story 3: "I want to pick models" (5 lines)

```python
from agiraph import team

result = team(
    "Research X and write a report",
    coordinator_model="anthropic/claude-sonnet-4-5",
    worker_model="openai/gpt-4o-mini",
)
```

Coordinator uses a smart model. Workers use a cheap one. Mix and match.

---

## Story 4: "I want to define the roles" (~15 lines)

```python
from agiraph import team, Role

result = team(
    "Compare NVIDIA and AMD's AI chip strategies",
    roles=[
        Role("Alice", "Market Analyst",
             prompt="Focus on partnerships, go-to-market, and market share.",
             model="anthropic/claude-sonnet-4-5"),
        Role("Bob", "Technical Analyst",
             prompt="Focus on architecture, benchmarks, and specs.",
             model="openai/gpt-4o"),
    ],
    synthesize=True,
)
```

The coordinator still manages stages and reconvene, but uses user-defined roles instead of auto-generating them.

---

## Story 5: "I want a Claude Code node" (~20 lines)

```python
from agiraph import team, Role, AgenticRole

result = team(
    "Scrape AI chip benchmarks and generate comparison charts",
    roles=[
        Role("Alice", "Researcher",
             prompt="Find benchmark data for H100, MI300X, and Gaudi 3"),
        AgenticRole("Bob", "Engineer",
             agent="claude-code",
             prompt="Write Python scripts to process data and generate charts"),
    ],
)

# Bob's workspace has actual .py files he wrote, tested, and ran
```

Bob runs as a full Claude Code subprocess. He has bash, git, file access. The harness just bridges messages and watches for his checkpoint.

---

## Story 6: "I want full control" (~30 lines)

```python
from agiraph import Coordinator, Role, AgenticRole, Stage, Contract

coordinator = Coordinator(model="anthropic/claude-sonnet-4-5")

result = coordinator.run(
    problem="Full competitive analysis of the AI chip market",
    stages=[
        Stage("Research", roles=[
            Role("Alice", "Market Analyst", model="openai/gpt-4o"),
            Role("Bob", "Tech Analyst", model="anthropic/claude-sonnet-4-5"),
            AgenticRole("Carol", "Data Engineer", agent="claude-code"),
        ]),
        Stage("Synthesis", roles=[
            Role("Dave", "Report Writer", model="anthropic/claude-sonnet-4-5"),
        ], persist=["Alice"]),
    ],
    contract=Contract(
        max_stages=3,
        checkpoint_policy="all",
    ),
    workspace="./output",
)
```

Everything explicit. Stages, roles, models, contract, workspace path. The coordinator still reconvenes and can adapt (add a stage, adjust roles), but within user-defined boundaries.

---

## Story 7: "I want custom tools" (~10 extra lines)

```python
from agiraph import team, tool

@tool
def query_database(sql: str) -> str:
    """Run a SQL query against the analytics database."""
    return db.execute(sql)

@tool
def send_slack(channel: str, message: str) -> str:
    """Post a message to a Slack channel."""
    return slack.post(channel, message)

result = team(
    "Analyze last quarter's sales and post summary to #analytics",
    tools=[query_database, send_slack],
)
```

Custom tools are plain Python functions with a decorator. Automatically available to all roles. Schema generated from type hints and docstring.

---

## Story 8: "I want to use it as a CLI" (0 lines of code)

```bash
$ pip install agiraph
$ echo "ANTHROPIC_API_KEY=sk-..." > .env
$ agiraph "Compare NVIDIA and AMD's AI chip strategies"

[coordinator] Planning team...
[coordinator] Stage 1: Research — Alice (Market Analyst), Bob (Tech Analyst)
[alice] Working...
[bob] Working...
...
[coordinator] Done. Output saved to ./agiraph_output/

$ cat ./agiraph_output/_output.md
```

Zero code. Just a CLI command and API keys.

---

## Architecture: How the layers compose

```
CLI (agiraph "prompt")
  └→ team("prompt")                          # Story 1-3
       └→ Coordinator.run(problem, ...)       # Story 6
            ├→ plan (LLM call to decide team)
            ├→ for each stage:
            │    ├→ api_node.run(role, ...)    # Story 4
            │    ├→ agentic_node.run(role, ...)# Story 5
            │    └→ message_queue              # shared
            └→ reconvene (LLM call to re-plan)
```

Each layer is a plain function. `team()` is sugar over `Coordinator`. `Coordinator` uses `api_node` and `agentic_node`. You can use any layer independently.

---

## File structure (Unix philosophy)

```
agiraph/
  __init__.py       # exports: team, Role, AgenticRole, Coordinator, tool
  core.py           # team() — the one-liner entry point, <100 lines
  coordinator.py    # coordinator planning and reconvene loop
  api_node.py       # API node agentic loop (think → act → observe)
  agentic_node.py   # external agent wrapper (launch, bridge, monitor)
  tools.py          # built-in tools + @tool decorator
  providers.py      # model provider adapters (Anthropic, OpenAI, etc.)
  messages.py       # in-memory message queue with file logging
  workspace.py      # workspace directory management
  context.py        # conversation context management and compaction
  cli.py            # CLI entry point
```

~10 files. Each small, each readable, each replaceable. No abstract base classes. No plugin registries. No YAML configs.
