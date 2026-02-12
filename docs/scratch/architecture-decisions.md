# Architecture Decisions

## Provider System

The provider system uses a `provider/model` string format:
- `anthropic/claude-sonnet-4-5` - Anthropic API
- `openai/gpt-4o` - OpenAI API
- `claude-code/opus` - Claude Code CLI as inference

Each provider implements `ProviderAdapter` (base.py) with `generate()`, `format_tools()`, etc.

**Claude Code is special**: It's not a standard LLM provider. It handles its own tool dispatch internally (Read, Write, Bash, etc.). When used as coordinator or worker, the system spawns a `claude -p --output-format stream-json` subprocess instead of running the ReAct loop. Events from its NDJSON output are forwarded to the EventBus.

## Coordinator Modes

1. **Standard mode** (Anthropic/OpenAI): ReAct loop with tool dispatch. Coordinator calls LLM, gets tool_calls, dispatches them, appends results, loops.
2. **Claude Code mode**: Single subprocess invocation. Claude Code handles everything internally. Events streamed via stream-json.

## Worker Types

- `harnessed`: Standard ReAct loop with tool dispatch (WorkerExecutor)
- `autonomous`: External process with file-based communication (_task.md, _result.md, _inbox.md, _outbox.md)
- `claude_code`: Claude Code CLI subprocess with stream-json events (ClaudeCodeWorkerExecutor)

## Claude Code CLI Key Flags

```bash
claude -p \
  --output-format stream-json \
  --verbose \
  --model <opus|sonnet|haiku> \
  --dangerously-skip-permissions \
  --system-prompt "..." \
  "Your task here"
```

Stream-json output is NDJSON with 3 event types:
- `system` (init) - session metadata, tools, model info
- `assistant` (per-turn) - wraps raw Anthropic API message with content blocks (text, tool_use)
- `result` (final) - result text, cost, duration, usage stats

## Tool Dispatch

- 25 built-in tools across 6 categories
- Coordinator tools: create_work_node, spawn_worker, assign_worker, check_board, reconvene, finish, etc.
- Worker tools: read_file, write_file, list_files, web_search, web_fetch, publish, checkpoint, etc.
- Tools are dispatched via ToolRegistry.dispatch(tool_call, context)
- ToolContext carries agent_id, paths, node/worker refs, message_bus, event_bus

## Event System

- EventBus: append-only log, in-memory + WebSocket broadcast
- Events: type, agent_id, ts, data dict
- WebSocket at /agents/{id}/events for real-time streaming
- HTTP GET /agents/{id}/events?limit=N for polling/backfill
- Frontend deduplicates between WebSocket and HTTP using `${type}:${ts}` key

## Frontend Architecture

- Next.js 16 + React 19 + Tailwind CSS
- Single agent detail page with 3 tabs: Chat, Team, Files
- Chat tab: unified event flow (events + conversation merged into timeline)
- Team tab: coordinator + workers with human names
- Files tab: recursive tree browser for workspace + memory
- useAgent hook: polls agent/board/workers/conversation + WebSocket for events

## Native Web Search

Models that support native server-side web search use the provider's own tool:

- **Anthropic** (all models): `web_search_20250305` tool, added automatically to every API call
  - `max_uses: 5` per inference call (configurable via AGIRAPH_SEARCH_MAX_USES env var)
  - Response includes `server_tool_use`, `web_search_tool_result`, and `text` blocks with citations
  - Raw content blocks are stored as `_content_blocks` on the conversation message for multi-turn fidelity
  - Encrypted search results must be passed back as-is for follow-up turns
- **OpenAI**: Would require Responses API (not Chat Completions) — not yet supported
- **Claude Code**: Has its own built-in search

Config: `MODEL_NATIVE_SEARCH` dict in config.py tracks which models support native search.

## Coordinator Stop/Resume

STOP does NOT kill the coordinator. It:
1. Cancels all worker tasks
2. Sets `coordinator._stopped = True`
3. Coordinator injects a context summary (board state, workers) into its conversation
4. Waits for human input
5. When human sends a message, clears `_stopped` and resumes normally

This way the coordinator retains full conversation context across stop/resume.

## Worker Failure Handling

When a worker's API call fails after one retry:
1. Saves `failure_notes.md` in the node's data_dir (full conversation history)
2. Messages the coordinator via message_bus with failure details + notes
3. Emits `node.failed` event
4. Sets worker to idle, node to failed

CancelledError (from STOP) is handled gracefully at every level.

## Key Bug Fixes

1. **OpenAI 400 error**: Tool results must immediately follow assistant tool_calls message. Fixed by deferring _yield_point() to after all tool results are appended.
2. **Events not showing**: useAgent only got WebSocket events. Fixed by adding HTTP backfill with getEvents() on initial load + dedup.
3. **.env loading**: config.py used load_dotenv() which only checks cwd. Fixed by explicitly loading from project root.
4. **Duplicate messages**: Conversation messages AND message.sent events both appeared. Fixed by filtering out `message.sent` where `from_id === "human"`.
5. **Double human messages**: `agent.send_message()` logged to conversation_log, then coordinator's `_yield_point()` re-logged the same message from the message bus. Fixed by skipping `from_id == "human"` in coordinator's re-logging.
6. **Coordinator duplicate output**: Tight loop calling LLM repeatedly with same state. Fixed by `_wait_for_activity()` that blocks until workers complete or human message arrives.
