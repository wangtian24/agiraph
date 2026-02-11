"""All built-in tool definitions (ToolDef) for Agiraph."""

from agiraph.models import ToolDef

# ---------------------------------------------------------------------------
# Work Management
# ---------------------------------------------------------------------------

PUBLISH = ToolDef(
    name="publish",
    description="Finalize your work on this node. Moves scratch/ to published/, marks node complete.",
    parameters={
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Summary of what you produced"},
        },
        "required": ["summary"],
    },
    guidance="Call this when you're genuinely done. Review scratch/ files before publishing.",
)

CHECKPOINT = ToolDef(
    name="checkpoint",
    description="Signal that you've completed this stage of work.",
    parameters={
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Summary of progress so far"},
        },
        "required": ["summary"],
    },
)

CREATE_WORK_NODE = ToolDef(
    name="create_work_node",
    description="Create a sub-task on the work board. It will be picked up by a worker.",
    parameters={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Task description / spec for the new node"},
            "deps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Node IDs that must complete before this node can start",
                "default": [],
            },
            "refs": {
                "type": "object",
                "description": "Pointers to other nodes' published data",
                "default": {},
            },
        },
        "required": ["task"],
    },
)

SUGGEST_NEXT = ToolDef(
    name="suggest_next",
    description="Suggest a follow-up work node to the coordinator. The coordinator decides whether to create it.",
    parameters={
        "type": "object",
        "properties": {
            "suggestion": {"type": "string", "description": "What work should be done and why"},
        },
        "required": ["suggestion"],
    },
)

# ---------------------------------------------------------------------------
# Communication
# ---------------------------------------------------------------------------

SEND_MESSAGE = ToolDef(
    name="send_message",
    description="Send a message to another worker, the coordinator, or the human by name.",
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient name (e.g. 'coordinator', 'Alice', 'Human')"},
            "content": {"type": "string", "description": "Message content"},
        },
        "required": ["to", "content"],
    },
    guidance="Message when you have something useful to share. Don't message to say 'starting' or 'done'.",
)

CHECK_MESSAGES = ToolDef(
    name="check_messages",
    description="Check for new messages from other workers, the coordinator, or the human.",
    parameters={"type": "object", "properties": {}},
    guidance="Check periodically, especially on long tasks. Coordinator messages may contain updated instructions.",
)

ASK_HUMAN = ToolDef(
    name="ask_human",
    description="Ask the human a question. Your work pauses until they respond. Use sparingly.",
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "The question to ask"},
            "channel": {
                "type": "string",
                "description": "Channel: cli | webhook | email",
                "default": "cli",
            },
        },
        "required": ["question"],
    },
    guidance="Only use when genuinely stuck. Try to figure it out yourself first.",
)

# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

READ_FILE = ToolDef(
    name="read_file",
    description="Read a file from the workspace.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to the run root"},
        },
        "required": ["path"],
    },
)

WRITE_FILE = ToolDef(
    name="write_file",
    description="Write a file to your node's scratch/ directory or your worker files.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to the run root"},
            "content": {"type": "string", "description": "File content"},
        },
        "required": ["path", "content"],
    },
    guidance="Write to scratch/ for WIP. Name files descriptively. Keep files focused.",
)

LIST_FILES = ToolDef(
    name="list_files",
    description="List files in a directory.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path relative to the run root"},
        },
        "required": ["path"],
    },
)

READ_REF = ToolDef(
    name="read_ref",
    description="Read a referenced upstream node's published output by ref name.",
    parameters={
        "type": "object",
        "properties": {
            "ref_name": {"type": "string", "description": "Key from _refs.json"},
        },
        "required": ["ref_name"],
    },
)

# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

BASH = ToolDef(
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
    guidance=(
        "Use for running code, installing packages, git operations, CLI tools.\n"
        "Always check output. Don't retry the same failing command.\n"
        "Chain with && so later steps don't run if earlier ones fail."
    ),
)

# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------

WEB_SEARCH = ToolDef(
    name="web_search",
    description="Search the web. Returns titles, URLs, and snippets.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    },
    guidance=(
        "Be specific in queries. Search multiple times with different angles.\n"
        "Don't trust snippets blindly — use web_fetch on promising URLs."
    ),
)

WEB_FETCH = ToolDef(
    name="web_fetch",
    description="Fetch a webpage and return its content as markdown.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
        },
        "required": ["url"],
    },
    guidance="Content truncated at ~15K chars. Extract data and write to scratch/.",
)

# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

MEMORY_WRITE = ToolDef(
    name="memory_write",
    description="Write to your long-term memory. Survives across sessions.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to memory/ directory"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
    guidance="Distill insights, don't dump raw data. Organize by topic.",
)

MEMORY_READ = ToolDef(
    name="memory_read",
    description="Read from your long-term memory.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to memory/ directory"},
        },
        "required": ["path"],
    },
)

MEMORY_SEARCH = ToolDef(
    name="memory_search",
    description="Search your memory for relevant notes.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    },
)

# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

SCHEDULE = ToolDef(
    name="schedule",
    description="Schedule a future action (delayed, at_time, scheduled cron, or heartbeat).",
    parameters={
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["delayed", "at_time", "scheduled", "heartbeat"],
                "description": "Trigger type",
            },
            "config": {
                "type": "object",
                "description": "Type-specific config: {delay_seconds}, {at: ISO8601}, {cron: str}, {interval_seconds}",
            },
            "action": {"type": "string", "description": "Task description for when the trigger fires"},
        },
        "required": ["type", "config", "action"],
    },
)

LIST_TRIGGERS = ToolDef(
    name="list_triggers",
    description="List all your active scheduled triggers.",
    parameters={"type": "object", "properties": {}},
)

CANCEL_TRIGGER = ToolDef(
    name="cancel_trigger",
    description="Cancel a scheduled trigger by ID.",
    parameters={
        "type": "object",
        "properties": {
            "trigger_id": {"type": "string", "description": "Trigger ID to cancel"},
        },
        "required": ["trigger_id"],
    },
)

# ---------------------------------------------------------------------------
# Coordinator-Only
# ---------------------------------------------------------------------------

ASSIGN_WORKER = ToolDef(
    name="assign_worker",
    description="Assign a specific worker to a work node.",
    parameters={
        "type": "object",
        "properties": {
            "node_id": {"type": "string"},
            "worker_id": {"type": "string"},
        },
        "required": ["node_id", "worker_id"],
    },
    coordinator_only=True,
)

SPAWN_WORKER = ToolDef(
    name="spawn_worker",
    description="Create a new worker. Can be harnessed (API-driven) or autonomous (external agent).",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Worker name (e.g. 'Alice')"},
            "role": {"type": "string", "description": "Worker role description"},
            "type": {
                "type": "string",
                "enum": ["harnessed", "autonomous"],
                "default": "harnessed",
            },
            "model": {
                "type": "string",
                "description": "Model for harnessed workers (e.g. 'anthropic/claude-sonnet-4-5')",
            },
            "max_iterations": {
                "type": "integer",
                "description": "Max ReAct loop iterations",
                "default": 20,
            },
        },
        "required": ["name", "role"],
    },
    coordinator_only=True,
)

CHECK_BOARD = ToolDef(
    name="check_board",
    description="View all work nodes and their current status.",
    parameters={"type": "object", "properties": {}},
    coordinator_only=True,
)

RECONVENE = ToolDef(
    name="reconvene",
    description="End the current stage. Read all outputs and plan next steps.",
    parameters={
        "type": "object",
        "properties": {
            "assessment": {"type": "string", "description": "Your analysis of current progress"},
        },
        "required": ["assessment"],
    },
    coordinator_only=True,
)

FINISH = ToolDef(
    name="finish",
    description="Goal achieved. Wrap up and stop the agent.",
    parameters={
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Final summary of what was accomplished"},
        },
        "required": ["summary"],
    },
    coordinator_only=True,
)


# ---------------------------------------------------------------------------
# Collect all
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    PUBLISH, CHECKPOINT, CREATE_WORK_NODE, SUGGEST_NEXT,
    SEND_MESSAGE, CHECK_MESSAGES, ASK_HUMAN,
    READ_FILE, WRITE_FILE, LIST_FILES, READ_REF,
    BASH, WEB_SEARCH, WEB_FETCH,
    MEMORY_WRITE, MEMORY_READ, MEMORY_SEARCH,
    SCHEDULE, LIST_TRIGGERS, CANCEL_TRIGGER,
    ASSIGN_WORKER, SPAWN_WORKER, CHECK_BOARD, RECONVENE, FINISH,
]

WORKER_TOOLS = [t for t in ALL_TOOLS if not t.coordinator_only]
COORDINATOR_TOOLS = ALL_TOOLS
