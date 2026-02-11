# Component Documentation

Detailed documentation of each major component in the system.

## Backend Components

### Planner (`backend/planner.py`)

**Purpose**: Converts user prompts into executable DAG plans.

**Key Methods**:
- `create_plan(user_prompt, force_provider, force_model) -> Plan`
  - Takes user prompt and optional provider/model constraints
  - Calls AI provider with planning prompts
  - Parses JSON response into `Plan` with `Node` objects
  - Validates provider availability
  - Generates title if missing

**Prompts Used**:
- `planner_system.txt` - System prompt defining planning task
- `planner_user.txt` - User prompt template with task details

**Output Format**:
```json
{
  "title": "Plan title",
  "nodes": [
    {
      "id": "node_1",
      "name": "Task name",
      "description": "What this node does",
      "provider": "openai",
      "model": "gpt-4o-mini",
      "input_description": "What inputs are needed",
      "output_description": "What will be produced",
      "dependencies": ["node_0"]
    }
  ],
  "edges": [{"from": "node_0", "to": "node_1"}]
}
```

**Important Notes**:
- If `force_provider`/`force_model` provided, ALL nodes use those values
- Falls back to first available provider if node specifies unavailable provider
- Handles both old format (`input_contract`/`output_contract`) and new format (`input_description`/`output_description`)

### Executor (`backend/executor.py`)

**Purpose**: Executes DAG plans with proper dependency resolution and parallelization.

**Key Methods**:
- `execute(plan: Plan) -> Dict`
  - Main execution method
  - Builds dependency graph
  - Executes nodes in waves (parallel where possible)
  - Returns execution results and logs

- `_execute_node(node: Node, plan: Plan) -> str`
  - Executes single node
  - Prepares inputs from dependency results (natural language)
  - Calls AI provider
  - Returns natural language result

- `_get_ready_nodes(plan: Plan, completed: Set[str]) -> List[Node]`
  - Finds nodes with all dependencies completed
  - Used to determine which nodes can run in parallel

- `_prepare_node_inputs(node: Node, plan: Plan) -> str`
  - Collects results from dependency nodes
  - Formats as natural language text
  - Raises error if dependency result missing

**Execution Algorithm**:
1. Build dependency graph (which nodes depend on which)
2. Initialize all node results as empty strings
3. Loop until all nodes completed:
   - Find ready nodes (all deps completed)
   - Execute ready nodes in parallel using `asyncio.create_task`
   - Wait for all tasks in wave to complete
   - Store results and mark nodes as completed
4. Return aggregated results

**Prompts Used**:
- `node_execution_system.txt` - System prompt for node execution
- `node_execution_user.txt` - User prompt template with task and inputs

**Error Handling**:
- Failed nodes marked as `FAILED` with error message
- Execution continues with other nodes if possible
- If critical dependency fails, execution stops

### API (`backend/api.py`)

**Purpose**: FastAPI server providing REST endpoints and WebSocket support.

**Key Endpoints**:

- `GET /api/providers` - List available providers and default models
- `POST /api/plan` - Create a plan from user prompt
  - Request: `{prompt, provider, model}`
  - Response: Plan object with nodes and edges
- `POST /api/execute` - Create execution (returns execution_id)
- `POST /api/execute/{execution_id}/start` - Start execution (runs async)
- `GET /api/execution/{execution_id}/status` - Get current status
- `GET /api/execution/{execution_id}/result` - Get final results
- `GET /api/executions` - List saved executions
- `GET /api/execution/{execution_id}/load` - Load saved execution
- `WebSocket /ws/{execution_id}` - Real-time status updates

**State Management**:
- `active_plans: Dict[str, Plan]` - In-memory plan storage
- `active_executions: Dict[str, Dict]` - Execution state tracking

**Storage**:
- Execution results saved to `storage/{execution_id}.json`
- Contains full plan, node results, logs, timestamps

### Providers (`backend/providers/`)

**Base Class** (`base.py`):
```python
class AIProvider(ABC):
    async def generate(prompt, model, system_prompt=None) -> str
    def get_available_models() -> list[str]
```

**Factory** (`factory.py`):
- `create_provider(provider_name: str) -> AIProvider`
- Maps provider names to concrete implementations
- Handles API key retrieval from `Config`

**Implementations**:
- `openai_provider.py` - OpenAI API (GPT models)
- `anthropic_provider.py` - Anthropic API (Claude models)
- `gemini_provider.py` - Google Gemini API
- `minimax_provider.py` - Minimax API

**Common Patterns**:
- All providers validate API responses
- Handle empty responses, missing fields, errors
- Return natural language text (not JSON)

### Models (`backend/models.py`)

**Node**:
```python
class Node(BaseModel):
    id: str
    name: str
    description: str
    provider: str
    model: str
    input_description: str  # Natural language
    output_description: str  # Natural language
    dependencies: List[str]
    status: NodeStatus
    result: Optional[str]  # Natural language result
    error: Optional[str]
    execution_time: Optional[float]
```

**Plan**:
```python
class Plan(BaseModel):
    plan_id: str
    user_prompt: str
    title: Optional[str]
    nodes: List[Node]
    edges: List[Dict[str, str]]  # [{"from": "id", "to": "id"}]
    status: str  # draft, executing, completed, failed
```

**NodeStatus** (Enum):
- `PENDING` - Not started
- `READY` - Dependencies met, ready to run
- `RUNNING` - Currently executing
- `COMPLETED` - Finished successfully
- `FAILED` - Execution failed

### Config (`backend/config.py`)

**Purpose**: Centralized configuration management.

**Key Methods**:
- `get_api_key(provider: str) -> Optional[str]`
- `get_available_providers() -> Dict[str, bool]`
- `get_available_provider_names() -> List[str]`

**Environment Variables**:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `MINIMAX_API_KEY`
- `MINIMAX_GROUP_ID` (optional)

**Default Models**:
- Maps provider names to default model names

## Frontend Components

### Main Page (`frontend/pages/index.tsx`)

**Features**:
- Provider/model selection
- Prompt input
- Plan creation
- DAG visualization (ReactFlow)
- Execution control
- Real-time status via WebSocket
- Saved executions list

**State Management**:
- React hooks (`useState`, `useEffect`)
- WebSocket connection for real-time updates
- Axios for API calls

### Execution View (`frontend/pages/execution/[id].tsx`)

**Purpose**: Detailed view of a saved execution.

**Features**:
- Load execution from storage
- Display node results
- Show execution timeline
- Render markdown results

### API Communication

**Pattern**:
- All API calls use `/api/*` paths
- Next.js rewrites proxy to `http://localhost:8000/api/*`
- WebSocket connects directly to `ws://localhost:8000/ws/{execution_id}`

**Key API Calls**:
```typescript
// Get providers
GET /api/providers

// Create plan
POST /api/plan
Body: {prompt, provider, model}

// Execute
POST /api/execute
Body: {plan_id}
→ Returns: {execution_id}

// Start execution
POST /api/execute/{execution_id}/start

// Get status
GET /api/execution/{execution_id}/status

// Get results
GET /api/execution/{execution_id}/result
```

## Prompt System (`backend/prompts/`)

**Purpose**: Externalize prompts for easy iteration.

**Files**:
- `planner_system.txt` - System prompt for planner
- `planner_user.txt` - User prompt template for planning
- `node_execution_system.txt` - System prompt for node execution
- `node_execution_user.txt` - User prompt template for execution

**Usage**:
```python
from .prompts import load_prompt, format_prompt

template = load_prompt("planner_user.txt")
prompt = format_prompt(template, user_prompt="...", ...)
```

**Template Format**:
- Uses Python `.format()` syntax
- Variables: `{user_prompt}`, `{available_providers}`, etc.
