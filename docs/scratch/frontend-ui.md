# Frontend UI Design Notes

## Layout

```
+--sidebar(200px)--+------right content area------+
| Agiraph          |                               |
| <- Back          |                               |
| * Working...     |   Tab content (Chat/Team/     |
|                  |   Files) fills this area      |
| [Chat]           |                               |
|  [Team]          |                               |
|    🧑‍💼 Alice coord|                               |
|    ● Bob Researcher                              |
|    ○ Charlie idle|                               |
| [Files]          |                               |
|                  |                               |
| Model: ...       |   [cog][input bar][Send][Stop]|
+------------------+-------------------------------+
```

## Tabs

1. **Chat** - Unified event log (dark terminal theme, gray-900 bg)
   - Merges conversation[] + events[] into LogEntry[], sorted by timestamp
   - Groups consecutive entries from same source into GroupBlock with colored left border
   - Human (green), Coordinator (indigo), Workers (cyan), System (yellow), Errors (red)
   - Assistant messages rendered with ReactMarkdown (prose-invert)
   - Coordinator shows as "🧑‍💼 Name (Coordinator)" in chat headers
   - Workers show as "Name (ShortRole)" — role truncated to max 20 chars
   - Input bar at bottom with @mention dropdown
   - Stop button (red) visible when agent is running
   - Cog icon toggles results-only mode

2. **Team** - Coordinator + workers with human names
   - humanName(id) generates deterministic name from ID hash
   - Coordinator has 🧑‍💼 emoji prefix
   - Cards with status dot, name, role badge, model
   - Worker roles shown as short form (shortRole() truncates to 1-2 words)
   - Clicking navigates to Files tab

3. **Files** - Two sub-tabs: Workspace Files + Agent Memory
   - Recursive tree auto-expanded on load (buildTree fetches all dirs)
   - File content preview on click
   - Workspace = run directory; Memory = agent/memory directory

## Sidebar Team Members

The left sidebar shows team members as an indented subsection under the "Team" tab:
- Coordinator: 🧑‍💼 emoji + human name + "Coordinator" role + model
- Workers: human name + short role + status + model
- Spinning icon when busy (animated SVG spinner)
- Static dot when idle/completed
- Global spinner in status area when any worker is busy

## @Mention in Chat

- Type `@` in the textarea to see a dropdown of team members
- Dropdown shows above the input bar with name + role
- Filters as you type (e.g., `@Al` matches "Alice")
- Arrow keys to navigate, Tab/Enter to select, Escape to close
- Inserts `@Name ` into the message text
- When sending, first `@mention` determines the `to` target
- If no @mention, message goes to coordinator (default)
- Messages route to the entity's message bus queue

## Results-Only Mode (Cog Toggle)

When cog icon is toggled to results-only:

**Shows:**
- Human messages (user input)
- Assistant text (actual LLM-generated answers)
- Errors and questions needing human attention
- System banners (agent started/completed)
- Node completion results (final work output)
- Compact worker status lines at bottom (Claude Code style)

**Hides:**
- Tool calls (tool.called events)
- Tool results (tool.result events)
- Internal events (node.created, node.assigned, worker.spawned, etc.)
- File write events
- Inter-entity messages

**Worker Status Lines** (Claude Code style):
```
● Alice (Researcher) — working... · 12 tool calls
○ Bob (Programmer) — idle · 5 tool calls
```
Each worker shows: spinner/dot + name + role + status + tool call count.

## Model Selection (Home Page)

Home page has a visual button grid for model selection:
- Title: "New Task" (not "New Agent")
- Button: "Go" (not "Create Agent")
- All models from all providers listed as pill buttons
- Selected model highlighted in blue
- Includes Claude Code variants (claude-code/sonnet, opus, haiku)

## Human Names

Deterministic mapping from agent/worker ID to a friendly name:
```typescript
const HUMAN_NAMES = ["Alice", "Bob", "Charlie", ...];
function humanName(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = ((hash << 5) - hash + id.charCodeAt(i)) | 0;
  }
  return HUMAN_NAMES[Math.abs(hash) % HUMAN_NAMES.length];
}
```

## Short Role Helper

```typescript
function shortRole(role: string): string {
  if (role.length <= 20) return role;
  const words = role.split(/\s+/);
  let result = words[0];
  if (words.length > 1 && (result.length + words[1].length + 1) <= 20) {
    result += " " + words[1];
  }
  return result;
}
```

## Dependencies
- react-markdown ^10.1.0 for rendering LLM markdown output
- Next.js 16.1.6
- React 19.2.3
- Tailwind CSS 4
