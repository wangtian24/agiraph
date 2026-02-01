# API Reference

Complete reference for backend API endpoints and data structures.

## Base URL

- **Development**: `http://localhost:8000`
- **Frontend Proxy**: `/api/*` routes proxy to backend

## Authentication

Currently no authentication required. API keys configured via environment variables.

## Endpoints

### Providers

#### `GET /api/providers`

Get list of available providers and their default models.

**Response**:
```json
{
  "providers": ["openai", "anthropic", "gemini"],
  "default_models": {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5",
    "gemini": "gemini-3-flash-preview",
    "minimax": "MiniMax-M2.1"
  }
}
```

### Planning

#### `POST /api/plan`

Create an execution plan from a user prompt.

**Request**:
```json
{
  "prompt": "Create a web scraper for news articles",
  "provider": "openai",
  "model": "gpt-4o-mini"
}
```

**Response**:
```json
{
  "plan_id": "uuid-string",
  "user_prompt": "Create a web scraper...",
  "title": "Web Scraper Creation",
  "nodes": [
    {
      "id": "node_1",
      "name": "Design Scraper Architecture",
      "description": "Design the overall architecture...",
      "provider": "openai",
      "model": "gpt-4o-mini",
      "input_description": "No inputs needed",
      "output_description": "Architecture design document",
      "dependencies": [],
      "status": "pending"
    },
    {
      "id": "node_2",
      "name": "Implement Scraper",
      "description": "Implement the scraper code...",
      "provider": "openai",
      "model": "gpt-4o-mini",
      "input_description": "Architecture design",
      "output_description": "Python scraper code",
      "dependencies": ["node_1"],
      "status": "pending"
    }
  ],
  "edges": [
    {"from": "node_1", "to": "node_2"}
  ],
  "status": "draft"
}
```

**Errors**:
- `500`: Planning failed (invalid response, provider error, etc.)

### Execution

#### `POST /api/execute`

Create a new execution for a plan.

**Request**:
```json
{
  "plan_id": "uuid-string"
}
```

**Response**:
```json
{
  "execution_id": "uuid-string",
  "plan_id": "uuid-string"
}
```

**Errors**:
- `404`: Plan not found

#### `POST /api/execute/{execution_id}/start`

Start executing a plan (runs asynchronously).

**Response**:
```json
{
  "status": "started",
  "execution_id": "uuid-string"
}
```

**Errors**:
- `404`: Execution or plan not found

#### `GET /api/execution/{execution_id}/status`

Get current execution status.

**Response**:
```json
{
  "execution_id": "uuid-string",
  "plan_id": "uuid-string",
  "status": "executing",
  "node_states": {
    "node_1": "completed",
    "node_2": "running",
    "node_3": "pending"
  },
  "logs": [
    "Starting execution of plan...",
    "Starting node node_1: Design Scraper Architecture",
    "Completed node node_1 (took 2.34s)"
  ]
}
```

**Status Values**:
- `starting` - Execution created but not started
- `executing` - Currently running
- `completed` - All nodes completed successfully
- `failed` - Execution failed

**Errors**:
- `404`: Execution not found

#### `GET /api/execution/{execution_id}/result`

Get final execution results.

**Response**:
```json
{
  "execution_id": "uuid-string",
  "plan_id": "uuid-string",
  "status": "completed",
  "node_results": [
    {
      "node_id": "node_1",
      "name": "Design Scraper Architecture",
      "status": "completed",
      "result": "Here is the architecture design...",
      "error": null,
      "execution_time": 2.34
    },
    {
      "node_id": "node_2",
      "name": "Implement Scraper",
      "status": "completed",
      "result": "Here is the Python code...",
      "error": null,
      "execution_time": 3.45
    }
  ],
  "execution_logs": [
    "Starting execution of plan...",
    "Executing 1 nodes in parallel: ['node_1']",
    "Starting node node_1: Design Scraper Architecture",
    "Completed node node_1: Design Scraper Architecture (took 2.34s)",
    "Executing 1 nodes in parallel: ['node_2']",
    "Starting node node_2: Implement Scraper",
    "Completed node node_2: Implement Scraper (took 3.45s)",
    "Execution completed. Status: completed"
  ],
  "started_at": "2024-01-01T12:00:00",
  "completed_at": "2024-01-01T12:00:05"
}
```

**Errors**:
- `404`: Execution or plan not found

### Storage

#### `GET /api/executions`

List all saved executions.

**Response**:
```json
{
  "executions": [
    {
      "execution_id": "uuid-1",
      "plan_id": "uuid-1",
      "title": "Web Scraper Creation",
      "user_prompt": "Create a web scraper...",
      "timestamp": "2024-01-01T12:00:00",
      "status": "completed"
    },
    {
      "execution_id": "uuid-2",
      "plan_id": "uuid-2",
      "title": "Data Analysis Pipeline",
      "user_prompt": "Build a data analysis pipeline...",
      "timestamp": "2024-01-01T11:00:00",
      "status": "completed"
    }
  ]
}
```

**Note**: Returns up to 50 most recent executions.

#### `GET /api/execution/{execution_id}/load`

Load a saved execution result (full data).

**Response**: Same as `GET /api/execution/{execution_id}/result`, but loaded from storage file.

**Errors**:
- `404`: Execution not found in storage

## WebSocket

### `WS /ws/{execution_id}`

Real-time execution status updates.

**Connection**:
```
ws://localhost:8000/ws/{execution_id}
```

**Messages Sent** (every 1 second while execution active):
```json
{
  "status": "executing",
  "node_states": {
    "node_1": "completed",
    "node_2": "running",
    "node_3": "pending"
  },
  "logs": [
    "Last 10 log messages..."
  ]
}
```

**Connection Lifecycle**:
- Client connects with execution_id
- Server sends updates every second
- Connection closes when execution completes or client disconnects

## Data Models

### Node

```typescript
interface Node {
  id: string;
  name: string;
  description: string;
  provider: string;  // "openai", "anthropic", "gemini", "minimax"
  model: string;
  input_description: string;  // Natural language
  output_description: string;  // Natural language
  dependencies: string[];  // Array of node IDs
  status: "pending" | "ready" | "running" | "completed" | "failed";
  result?: string;  // Natural language result
  error?: string;
  execution_time?: number;  // Seconds
}
```

### Plan

```typescript
interface Plan {
  plan_id: string;
  user_prompt: string;
  title?: string;
  nodes: Node[];
  edges: Array<{from: string, to: string}>;
  status: "draft" | "executing" | "completed" | "failed";
}
```

### Execution Status

```typescript
interface ExecutionStatus {
  execution_id: string;
  plan_id: string;
  status: "starting" | "executing" | "completed" | "failed";
  node_states: Record<string, string>;  // node_id -> status
  logs: string[];
}
```

### Execution Result

```typescript
interface ExecutionResult {
  execution_id: string;
  plan_id: string;
  status: string;
  node_results: Array<{
    node_id: string;
    name: string;
    status: string;
    result?: string;
    error?: string;
    execution_time?: number;
  }>;
  execution_logs: string[];
  started_at: string;  // ISO timestamp
  completed_at?: string;  // ISO timestamp
}
```

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message here"
}
```

**HTTP Status Codes**:
- `200` - Success
- `404` - Resource not found
- `500` - Server error

## Usage Examples

### Complete Flow

```typescript
// 1. Get available providers
const providers = await axios.get('/api/providers');

// 2. Create plan
const plan = await axios.post('/api/plan', {
  prompt: "Create a web scraper",
  provider: "openai",
  model: "gpt-4o-mini"
});

// 3. Execute plan
const execution = await axios.post('/api/execute', {
  plan_id: plan.data.plan_id
});

// 4. Start execution
await axios.post(`/api/execute/${execution.data.execution_id}/start`);

// 5. Connect WebSocket for real-time updates
const ws = new WebSocket(`ws://localhost:8000/ws/${execution.data.execution_id}`);
ws.onmessage = (event) => {
  const status = JSON.parse(event.data);
  console.log('Status:', status);
};

// 6. Poll for results (or wait for WebSocket)
const result = await axios.get(`/api/execution/${execution.data.execution_id}/result`);
console.log('Results:', result.data);
```

### Loading Saved Execution

```typescript
// List executions
const executions = await axios.get('/api/executions');

// Load specific execution
const execution = await axios.get(`/api/execution/${executionId}/load`);
```

## Rate Limiting

Currently no rate limiting implemented. Consider adding for production use.

## CORS

CORS enabled for all origins in development. Configure appropriately for production.
