# Agiraph v2-A — Technical Design: Part 3 — Memory & Human

**Part 3 of 4** | [Part 1: Core Concepts](./v2-A-technical-1-core.md) | [Part 2: Runtime](./v2-A-technical-2-runtime.md) | [Part 4: Implementation](./v2-A-technical-4-implementation.md)
**Date:** 2026-02-11

_Covers: Memory system, human as a node, event system, trigger & scheduling._

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
