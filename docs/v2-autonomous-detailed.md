# Agiraph v2 — Detailed Design

**Companion to:** [v2-autonomous-design.md](./v2-autonomous-design.md)
**Date:** 2026-02-08

---

## 1. Coordinator Lifecycle

The coordinator is the entry point. It receives the user's prompt, decides team structure, and manages the collaboration through stages.

### 1.1 Planning Phase

The coordinator is an LLM call (using the smartest available model) with a system prompt that instructs it to analyze the problem and produce a collaboration plan.

**Coordinator system prompt (condensed):**
```
You are a team coordinator. Given a problem, decide:
1. Does this need multiple roles, or can one person handle it?
2. If multiple: what roles, what are their briefs?
3. How many stages of work do you expect?
4. What should each role produce?

Output a collaboration plan as JSON.
```

**Coordinator output — the collaboration plan:**
```json
{
  "problem_summary": "Analyze competitive landscape of AI chip companies",
  "stages": [
    {
      "name": "Research",
      "roles": [
        {
          "id": "alice",
          "name": "Alice",
          "title": "Market Analyst",
          "node_type": "api",
          "model": "anthropic/claude-sonnet-4-5",
          "prompt": "You are Alice, a market analyst. Research the market positioning, partnerships, and go-to-market strategy of NVIDIA, AMD, and Intel's AI chip divisions. Write your findings to your workspace as you go.",
          "workspace_reads": ["_plan.md"],
          "workspace_writes": ["alice/"]
        },
        {
          "id": "bob",
          "name": "Bob",
          "title": "Technical Analyst",
          "node_type": "agentic",
          "agent": "claude-code",
          "prompt": "You are Bob, a technical analyst. Research the architecture, benchmarks, and technical specs of the latest AI chips from NVIDIA, AMD, and Intel. Write findings to your workspace.",
          "workspace_reads": ["_plan.md"],
          "workspace_writes": ["bob/"]
        },
        {
          "id": "carol",
          "name": "Carol",
          "title": "Financial Analyst",
          "node_type": "api",
          "model": "openai/gpt-4o",
          "prompt": "You are Carol, a financial analyst. Analyze R&D spending, revenue, and market cap trends for NVIDIA, AMD, and Intel's AI divisions. Write findings to your workspace.",
          "workspace_reads": ["_plan.md"],
          "workspace_writes": ["carol/"]
        }
      ]
    }
  ],
  "contract": {
    "max_stages": 3,
    "checkpoint_policy": "all_must_checkpoint",
    "coordinator_reconvenes": true
  }
}
```

The coordinator writes this plan to `/workspace/_plan.md` in human-readable form so all roles can read it.

**Later stages are planned adaptively.** The coordinator sketches a rough roadmap but re-evaluates at each reconvene. Stage 2 roles may differ from what was initially expected based on Stage 1 outputs.

### 1.2 Stage Execution

1. Coordinator calls `launch_roles(stage)` tool
2. Runtime spins up all roles for this stage (in parallel)
3. Coordinator enters a monitoring loop:
   - Periodically reads role status files (`{role}/status.md`)
   - Checks if all roles have checkpointed
   - Can send messages to roles if needed
4. When all roles checkpoint (or coordinator decides to proceed), stage ends

### 1.3 Reconvene

Between stages, the coordinator:
1. Reads all role workspace outputs
2. Assesses progress against the problem
3. Decides next stage:
   - Which roles persist (keep their conversation context)
   - Which roles are retired (outputs remain in workspace)
   - Which new roles to create
   - Updated prompts for persisting roles
4. Writes updated plan to `_plan.md`
5. Launches next stage

### 1.4 Completion

The coordinator produces final output when:
- All planned stages are done, OR
- The coordinator decides the problem is solved early

Final output is written to `/workspace/_output.md`.

---

## 2. API Node — Internal Agentic Loop

For roles backed by a raw LLM API call, our runtime manages the agentic loop.

### 2.1 Loop Structure

```python
def run_api_node(role: Role, workspace: Path, message_queue: MessageQueue):
    conversation = [build_system_message(role)]

    while True:
        # 1. Check messages
        messages = message_queue.receive(role.name)
        for msg in messages:
            conversation.append({
                "role": "user",
                "content": f"[Message from {msg.from_name}]: {msg.content}"
            })

        # 2. Think + Act (LLM call with tools)
        response = call_model(
            provider=role.model,
            messages=conversation,
            tools=get_tools_for_role(role)
        )
        conversation.append({"role": "assistant", "content": response})

        # 3. Execute tool calls
        if response.tool_calls:
            for tool_call in response.tool_calls:
                result = dispatch_tool(tool_call, role, workspace, message_queue)
                conversation.append({"role": "tool", "content": result})

                if tool_call.name == "checkpoint":
                    write_status(role, "checkpointed", tool_call.args.summary)
                    return  # Exit loop — phase done

        # 4. Context management
        if estimate_tokens(conversation) > token_limit * 0.75:
            conversation = compact(role, conversation, workspace)

        # 5. No tool call = model is just reasoning, continue loop
```

### 2.2 System Prompt Template

```
You are {role.name}, a {role.title}.

{role.prompt}

TEAM CONTEXT:
You are part of a team working on: {problem_summary}
Other team members: {list of other role names and titles}
Current stage: {stage.name}

YOUR WORKSPACE: {role.workspace_dir}/
You can read any file in /workspace/ but only write to your own directory.

TOOLS:
- read_file(path): Read a file from the workspace
- write_file(path, content): Write a file to your workspace directory
- list_files(path): List files in a directory
- send_message(to, content): Send a message to a team member by name
- check_messages(): Check for new messages from team members
- web_search(query): Search the web
- web_fetch(url): Fetch and read a webpage
- checkpoint(summary): Signal that you've completed your work for this phase

IMPORTANT:
- Write findings to files as you go. Your conversation may be compacted.
- Check messages periodically to stay responsive to your team.
- Call checkpoint() when you've completed your work for this phase.
```

### 2.3 Context Compaction

When conversation tokens approach the model's context limit:

1. Read the role's workspace files (its own written artifacts)
2. Rebuild conversation:
   ```
   [system prompt]
   [user: "Here is your work so far, reconstructed from your files:"]
   [user: contents of role's workspace files]
   [last N turns of conversation]
   ```
3. Replace the old conversation with this compacted version

The role's workspace files serve as long-term memory. The conversation is disposable working memory.

---

## 3. Agentic Node — External Agent Wrapper

For roles backed by an already-agentic system (Claude Code, etc.), our runtime acts as a thin wrapper.

### 3.1 Launch

```python
def run_agentic_node(role: Role, workspace: Path, message_queue: MessageQueue):
    # Prepare the role's workspace
    write_file(workspace / role.id / "_inbox.md", "")
    write_file(workspace / role.id / "_outbox.md", "")

    # Build launch prompt
    prompt = f"""
    {role.prompt}

    COORDINATION:
    - Your workspace is {workspace / role.id}/
    - Check _inbox.md periodically for messages from your team.
    - To send messages to teammates, append to _outbox.md in the format:
      TO: <name>
      <message content>
      ---
    - When done with your work for this phase, create a file called
      _checkpoint.md with a summary of what you accomplished.
    - You can read files in the parent /workspace/ directory to see
      team context and other roles' outputs.
    """

    # Launch external agent
    process = launch_agent(
        agent_type=role.agent,  # "claude-code", etc.
        prompt=prompt,
        working_directory=workspace / role.id
    )

    # Monitor loop
    while process.running():
        bridge_messages(role, workspace, message_queue)

        if (workspace / role.id / "_checkpoint.md").exists():
            write_status(role, "checkpointed")
            return

        sleep(POLL_INTERVAL)
```

### 3.2 Message Bridging

The runtime bridges between the in-memory message queue and the file-based inbox/outbox:

```python
def bridge_messages(role, workspace, message_queue):
    # Incoming: queue → file
    messages = message_queue.receive(role.name)
    if messages:
        inbox = workspace / role.id / "_inbox.md"
        append_to_file(inbox, format_messages(messages))

    # Outgoing: file → queue
    outbox = workspace / role.id / "_outbox.md"
    if outbox.exists() and outbox_has_new_content(outbox):
        parsed = parse_outbox(outbox)
        for msg in parsed:
            message_queue.send(from_name=role.name, to_name=msg.to, content=msg.content)
        clear_outbox(outbox)
```

### 3.3 What Agentic Nodes Can Do

Since an Agentic Node (e.g., Claude Code) has its own tools, it can:
- Run bash commands
- Read/write files (beyond just the workspace)
- Access git and GitHub
- Execute code
- Install packages
- Make API calls

The runtime **confines** the node by setting its working directory to the workspace and (in the future) running it in a container. But within that boundary, it has full autonomy.

---

## 4. Tool Registry and Provider Adapter

### 4.1 Tool Registry

Tools are defined once as Python functions with metadata:

```python
TOOL_REGISTRY = {
    "read_file": {
        "function": impl_read_file,
        "schema": {
            "name": "read_file",
            "description": "Read a file from the workspace",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"}
                },
                "required": ["path"]
            }
        }
    },
    "write_file": {
        "function": impl_write_file,
        "schema": {
            "name": "write_file",
            "description": "Write content to a file in your workspace directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to your workspace directory"},
                    "content": {"type": "string", "description": "Content to write"}
                },
                "required": ["path", "content"]
            }
        }
    },
    "send_message": {
        "function": impl_send_message,
        "schema": {
            "name": "send_message",
            "description": "Send a message to a team member by name",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient's name (e.g., 'Alice')"},
                    "content": {"type": "string", "description": "Message content"}
                },
                "required": ["to", "content"]
            }
        }
    },
    "check_messages": {
        "function": impl_check_messages,
        "schema": {
            "name": "check_messages",
            "description": "Check for new messages from team members",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    "checkpoint": {
        "function": impl_checkpoint,
        "schema": {
            "name": "checkpoint",
            "description": "Signal that you have completed your work for this phase",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Summary of what you accomplished"}
                },
                "required": ["summary"]
            }
        }
    },
    "web_search": {
        "function": impl_web_search,
        "schema": {
            "name": "web_search",
            "description": "Search the web for information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    "web_fetch": {
        "function": impl_web_fetch,
        "schema": {
            "name": "web_fetch",
            "description": "Fetch and read a webpage",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"}
                },
                "required": ["url"]
            }
        }
    },
    "list_files": {
        "function": impl_list_files,
        "schema": {
            "name": "list_files",
            "description": "List files in a directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path relative to workspace"}
                },
                "required": ["path"]
            }
        }
    }
}
```

### 4.2 Provider Adapters

Each adapter implements two methods:

```python
class ProviderAdapter(ABC):
    @abstractmethod
    def format_tools(self, tool_schemas: list[dict]) -> provider_specific_format:
        """Convert tool schemas to what this provider's API expects."""
        pass

    @abstractmethod
    def parse_response(self, raw_response) -> ParsedResponse:
        """Extract text and tool calls from provider response.
        Returns unified ParsedResponse regardless of provider."""
        pass
```

**AnthropicAdapter:** Converts schemas to Anthropic's `input_schema` format, parses `content[].type == "tool_use"` blocks.

**OpenAIAdapter:** Converts schemas to OpenAI's `function` format, parses `tool_calls` array.

**GeminiAdapter:** Converts schemas to Gemini's `function_declarations` format, parses `function_call` parts.

**TextFallbackAdapter** (for models without native tool calling):

```python
class TextFallbackAdapter(ProviderAdapter):
    def format_tools(self, tool_schemas):
        # Render tools as text instructions in the prompt
        text = "AVAILABLE TOOLS:\n"
        for tool in tool_schemas:
            text += f"\n{tool['name']}: {tool['description']}\n"
            text += f"  Parameters: {json.dumps(tool['parameters'])}\n"
        text += "\nTo call a tool, output:\n"
        text += "<tool_call>{\"name\": \"...\", \"arguments\": {...}}</tool_call>\n"
        return text  # Appended to system prompt

    def parse_response(self, raw_response):
        # Parse <tool_call>...</tool_call> from text output
        tool_calls = extract_tool_call_tags(raw_response.text)
        return ParsedResponse(text=raw_response.text, tool_calls=tool_calls)
```

### 4.3 Dispatcher

The dispatcher receives a unified `ToolCall` object and executes the corresponding Python function:

```python
def dispatch_tool(tool_call: ToolCall, role: Role, workspace: Path, mq: MessageQueue):
    tool = TOOL_REGISTRY[tool_call.name]

    # Inject context into tool arguments
    context = ToolContext(role=role, workspace=workspace, message_queue=mq)

    return tool["function"](context, **tool_call.arguments)
```

---

## 5. Message Queue

### 5.1 In-Memory Queue

```python
class MessageQueue:
    def __init__(self, log_dir: Path):
        self._queues: dict[str, list[Message]] = defaultdict(list)
        self._lock = threading.Lock()
        self._log_dir = log_dir
        self._msg_counter = 0

    def send(self, from_name: str, to_name: str, content: str):
        msg = Message(from_name=from_name, to_name=to_name,
                      content=content, timestamp=time.time())
        with self._lock:
            self._queues[to_name].append(msg)
            self._msg_counter += 1
            self._log_to_file(msg)

    def receive(self, name: str) -> list[Message]:
        with self._lock:
            messages = self._queues.pop(name, [])
        return messages

    def _log_to_file(self, msg: Message):
        filename = f"{self._msg_counter:04d}_{msg.from_name}_to_{msg.to_name}.md"
        path = self._log_dir / filename
        path.write_text(f"FROM: {msg.from_name}\nTO: {msg.to_name}\n"
                        f"TIME: {msg.timestamp}\n\n{msg.content}\n")
```

### 5.2 Message Format

Messages are free-form text. No enforced schema. Roles communicate naturally:

```
Alice → Bob: "Hey Bob, I found that NVIDIA's H100 dominates the training market.
Can you check if AMD's MI300X benchmarks are competitive?"

Bob → Alice: "Looked into it. MI300X is competitive on inference but not training.
I wrote details to bob/amd_benchmarks.md if you want the specifics."
```

---

## 6. Workspace Layout

```
/workspace/
│
├── _plan.md                        # Collaboration plan (written by coordinator)
├── _output.md                      # Final output (written by coordinator)
├── _messages/                      # Message log (append-only)
│   ├── 0001_alice_to_bob.md
│   ├── 0002_bob_to_alice.md
│   └── ...
│
├── alice/                          # Alice's workspace
│   ├── status.md                   # "working" | "checkpointed" + summary
│   ├── market_analysis.md          # Her work output
│   └── notes.md                    # Her scratchpad
│
├── bob/                            # Bob's workspace (Agentic node)
│   ├── status.md
│   ├── _inbox.md                   # Messages bridged from queue
│   ├── _outbox.md                  # Messages to send (parsed by runtime)
│   ├── _checkpoint.md              # Created when done (signal to runtime)
│   ├── benchmarks.md               # His work output
│   └── src/                        # Code he wrote (Claude Code can do this)
│       └── analysis.py
│
├── carol/                          # Carol's workspace
│   ├── status.md
│   └── financial_report.md
│
└── dave/                           # Introduced in Stage 2
    ├── status.md
    └── draft_report.md
```

---

## 7. Execution Flow — Full Example

**User prompt:** *"Analyze the competitive landscape of AI chip companies and produce a report with market data, technical comparisons, and investment recommendations."*

### Stage 1: Research

```
COORDINATOR:
  "This needs three analysts working in parallel, then a writer to synthesize."

  Creates roles:
    Alice (Market Analyst, API node, claude-sonnet)
    Bob (Technical Analyst, Agentic node, claude-code)
    Carol (Financial Analyst, API node, gpt-4o)

  Writes _plan.md, launches all three.

ALICE (API node, running our harness loop):
  Turn 1: Reads _plan.md, understands her role
  Turn 2: web_search("AI chip market share 2025 2026")
  Turn 3: web_search("NVIDIA AMD Intel AI chip partnerships")
  Turn 4: Writes alice/market_analysis.md with findings
  Turn 5: send_message("Bob", "I found NVIDIA has 80% training market share.
           Can you validate from a technical specs angle?")
  Turn 6: check_messages() → message from Bob: "Confirmed, H100/B200
           dominate on memory bandwidth. See bob/benchmarks.md"
  Turn 7: Updates alice/market_analysis.md with Bob's input
  Turn 8: checkpoint("Completed market analysis for NVIDIA, AMD, Intel")

BOB (Agentic node, Claude Code):
  [Claude Code runs autonomously in bob/ directory]
  Reads _inbox.md → message from Alice
  Runs bash commands to fetch benchmark data
  Writes bob/benchmarks.md, bob/src/analysis.py
  Writes response to _outbox.md → bridged to Alice
  Creates _checkpoint.md → runtime detects completion

CAROL (API node):
  [Similar to Alice, researches financials]
  Writes carol/financial_report.md
  checkpoint("Completed financial analysis")

COORDINATOR (monitoring):
  Sees all three have checkpointed.
  Reads alice/, bob/, carol/ outputs.

  Reconvene decision:
    "Research is solid. Stage 2: bring in a writer.
     Keep Alice to cross-reference. Retire Bob and Carol."
```

### Stage 2: Synthesis

```
COORDINATOR:
  Creates roles:
    Alice (persists, updated prompt: "Cross-reference your market data
           with the technical and financial findings in bob/ and carol/")
    Dave (Report Writer, API node, claude-sonnet, new)

  Launches Stage 2.

ALICE:
  Reads bob/ and carol/ outputs
  Writes alice/cross_reference.md
  send_message("Dave", "Cross-reference is ready at alice/cross_reference.md")
  checkpoint("Completed cross-referencing")

DAVE:
  Reads all workspace outputs (alice/, bob/, carol/)
  Writes dave/draft_report.md
  send_message("Alice", "Draft is ready, can you review the market section?")
  [Alice already checkpointed, message queued for coordinator to handle]
  checkpoint("Draft report complete")

COORDINATOR:
  Reads dave/draft_report.md
  Decides: "Report looks complete. No Stage 3 needed."
  Writes _output.md with final polished report.
  Done.
```

---

## 8. Role Paradigms

The coordinator chooses the team shape based on the problem.

### Diverse Roles
Different specialists for multi-disciplinary problems.
```
Alice: Market Analyst
Bob: Engineer
Carol: Financial Analyst
Dave: Writer
```

### Homogeneous Workers
Same role, split load for embarrassingly parallel tasks.
```
Alice: Researcher (assigned companies: NVIDIA, AMD)
Bob: Researcher (assigned companies: Intel, Qualcomm)
Carol: Researcher (assigned companies: Google TPU, Amazon Trainium)
```
The runtime treats these identically — they're just roles with similar prompts and different assigned scopes.

### Single Agent
Coordinator decides the problem doesn't need a team.
```
Alice: General Analyst (handles everything solo)
```
Degrades gracefully to a single agentic loop.

---

## 9. Coordinator Tools

The coordinator itself is an LLM running in an agentic loop with special tools:

```
- launch_roles(stage_config): Launch a set of roles for a stage
- check_stage_status(): Check which roles have checkpointed
- read_file(path): Read any workspace file
- write_file(path, content): Write to workspace root (_plan.md, _output.md)
- send_message(to, content): Send message to any active role
- conclude(output): End the collaboration and produce final output
```

---

## 10. Implementation Plan

### Phase 1: Single-stage API nodes
- Tool registry + provider adapter (Anthropic, OpenAI)
- API node agentic loop (think → act → observe)
- Workspace file I/O
- Coordinator: plan, launch roles, wait for checkpoints, produce output
- No messages, no multi-stage, no agentic nodes
- **Test:** Coordinator creates 2 researcher roles, they work in parallel, coordinator synthesizes

### Phase 2: Messages + multi-stage
- Message queue (in-memory + file log)
- send_message / check_messages tools
- Multi-stage: coordinator reconvenes, re-plans, launches new stages
- Role persistence across stages
- **Test:** 3 roles coordinate via messages, coordinator runs 2 stages with different roles

### Phase 3: Agentic nodes
- Launch external agent (Claude Code) as subprocess
- File-based inbox/outbox bridging
- Checkpoint detection via file watch
- **Test:** Mixed team: 2 API nodes + 1 Claude Code node collaborating

### Phase 4: Context management + robustness
- Token counting and conversation compaction
- Text fallback adapter for non-native-tool-calling models
- Error handling: role failures, retries, timeouts
- Web search and web fetch tools
- **Test:** Long-running collaboration that triggers compaction

### Phase 5: Frontend
- Simple table UI: roles, status, current stage
- Expandable panels: workspace files, message log, coordinator reasoning
- WebSocket streaming of status updates
- **Test:** Run full collaboration and watch it in the UI

---

## 11. Data Structures

```python
@dataclass
class Role:
    id: str                    # "alice"
    name: str                  # "Alice"
    title: str                 # "Market Analyst"
    node_type: str             # "api" | "agentic"
    model: str | None          # "anthropic/claude-sonnet-4-5" (for api nodes)
    agent: str | None          # "claude-code" (for agentic nodes)
    prompt: str                # Full role prompt
    status: str                # "pending" | "working" | "checkpointed" | "retired"

@dataclass
class Stage:
    name: str                  # "Research"
    roles: list[Role]
    status: str                # "running" | "completed"

@dataclass
class Message:
    from_name: str
    to_name: str
    content: str
    timestamp: float

@dataclass
class CollaborationPlan:
    problem_summary: str
    stages: list[Stage]        # First stage detailed, later stages sketched
    contract: Contract

@dataclass
class Contract:
    max_stages: int
    checkpoint_policy: str     # "all_must_checkpoint"
    coordinator_reconvenes: bool

@dataclass
class Session:
    session_id: str
    workspace: Path
    plan: CollaborationPlan
    message_queue: MessageQueue
    coordinator_history: list[dict]  # Persists across stages
    current_stage: int
```

---

## 12. Open Questions (Deferred)

1. **Container isolation for agentic nodes** — run Claude Code in Docker for safety?
2. **Cost tracking** — token usage per role, per stage, total?
3. **Human-in-the-loop** — pause for human approval at reconvene?
4. **Subteam delegation** — role outsources to a nested collaboration (Model 2)?
5. **MCP integration** — swap hardcoded tools for MCP servers?
6. **Checkpointing for recovery** — serialize conversation state for long runs?
7. **Role-to-role file sharing protocol** — beyond "read each other's directories"?

---

*End of Detailed Design Document*
