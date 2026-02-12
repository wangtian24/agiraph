# Claude Code CLI Integration

## Overview

Claude Code CLI (`claude`) can be used as an inference provider for both coordinators and workers. Unlike standard LLM providers (Anthropic API, OpenAI API), Claude Code handles its own tool dispatch internally — it has built-in Read, Write, Bash, Grep, Glob, etc.

## Model String Format

```
claude-code/opus    -> claude -p --model opus
claude-code/sonnet  -> claude -p --model sonnet
claude-code/haiku   -> claude -p --model haiku
claude-code         -> defaults to sonnet
```

## Key CLI Flags

| Flag | Purpose |
|------|---------|
| `-p` / `--print` | Non-interactive mode, print and exit |
| `--output-format stream-json` | NDJSON streaming output |
| `--verbose` | Required for stream-json to work |
| `--dangerously-skip-permissions` | Skip permission prompts (for automation) |
| `--model <model>` | Select sub-model (opus/sonnet/haiku) |
| `--system-prompt <text>` | Custom system prompt |
| `--allowedTools <tools>` | Restrict available tools |
| `--max-budget-usd <amount>` | Cap spending per run |

## Stream-JSON Event Format

Three event types, one per line (NDJSON):

### 1. `system` (init)
```json
{
  "type": "system",
  "subtype": "init",
  "session_id": "...",
  "model": "claude-opus-4-6",
  "tools": ["Bash", "Read", "Write", ...]
}
```

### 2. `assistant` (per turn)
```json
{
  "type": "assistant",
  "message": {
    "content": [
      {"type": "text", "text": "..."},
      {"type": "tool_use", "name": "Write", "input": {...}}
    ],
    "usage": {"input_tokens": N, "output_tokens": N}
  }
}
```

### 3. `result` (final)
```json
{
  "type": "result",
  "subtype": "success",
  "result": "...",
  "total_cost_usd": 0.023,
  "duration_ms": 5100,
  "num_turns": 3
}
```

## Implementation Files

- `agiraph/claude_code.py` — ClaudeCodeRunner class, event parsing
- `agiraph/coordinator.py` — `_run_claude_code()` for coordinator mode
- `agiraph/worker.py` — `ClaudeCodeWorkerExecutor` for worker mode
- `agiraph/providers/factory.py` — Routes `claude-code/*` to text fallback adapter

## Architecture Notes

When using Claude Code as coordinator:
- The system prompt is built the same way (SOUL.md + goal + rules)
- Passed via `--system-prompt` flag
- Claude Code runs in the agent's `current_run_dir` as cwd
- All file operations are relative to that directory
- Events from stdout are forwarded to EventBus
- The ReAct loop is NOT used — Claude Code handles everything

When using Claude Code as worker:
- Runs in the node's `scratch/` directory
- Task description passed as the prompt
- System prompt includes worker identity + capabilities
- Creates `_result.md` file when done (convention)

## Gotcha: stream-json requires --verbose

Without `--verbose`, the `--output-format stream-json` flag silently fails. Always use both together.

## Cost Tracking

The `result` event includes `total_cost_usd`. This should be logged and displayed to the user.
