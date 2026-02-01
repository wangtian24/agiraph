# Component Overview

## Core Components

### Planner (`backend/planner.py`)

**Purpose**: Converts natural language prompts into structured DAG plans.

**Key Methods**:
- `create_plan(user_prompt, force_provider, force_model)` - Main entry point
- `get_planner_system_prompt()` - Generates system prompt with provider constraints

**Dependencies**:
- `backend.providers.factory.create_provider()` - Creates AI provider
- `backend.prompts` - Loads prompt templates
- `backend.models.Plan, Node` - Creates plan structure
- `backend.config.Config` - Gets available providers

**Output**: `Plan` object with:
- `plan_id` (UUID)
- `user_prompt` (original prompt)
- `title` (generated short title)
- `nodes` (list of Node objects)
- `edges` (dependency relationships)
- `status` ("draft")

**Key Behavior**:
- Always enforces provider/model selection if provided
- Validates all nodes use available providers
- Generates initial context node (node_0) pattern
- Handles both old (contract-based) and new (description-based) node formats

### Executor (`backend/executor.py`)

**Purpose**: Executes DAG plans with parallel execution support.

**Key Methods**:
- `execute(plan)` - Main execution entry point
- `_execute_node(node, plan)` - Executes single node
- `_get_ready_nodes(plan, completed)` - Finds nodes ready to execute
- `_prepare_node_inputs(node, plan)` - Prepares inputs from dependencies
- `_build_dependency_graph(plan)` - Builds dependency map

**Dependencies**:
- `backend.providers.factory.create_provider()` - Creates providers for nodes
- `backend.prompts` - Loads execution prompts
- `backend.models.Node, Plan, NodeStatus` - Uses data models

**Execution Flow**:
1. Validate all nodes have available providers
2. Build dependency graph
3. While nodes remain:
   - Find ready nodes (all dependencies completed)
   - Execute ready nodes in parallel (asyncio.create_task)
   - Wait for wave to complete
   - Store results in `node_results` dict
4. Return final result with status and logs

**Key Behavior**:
- Natural language results passed between nodes
- Parallel execution of independent nodes
- Graceful failure handling (failed nodes don't block others unnecessarily)
- Execution logs stored for debugging

### API (`backend/api.py`)

**Purpose**: FastAPI REST API and WebSocket server.

**Key Endpoints**:
- `GET /api/providers` - List available providers
- `POST /api/plan` - Create plan from prompt
- `POST /api/execute` - Create execution (returns execution_id)
- `POST /api/execute/{id}/start` - Actually start execution (async)
- `GET /api/execution/{id}/status` - Get execution status
- `GET /api/execution/{id}/result` - Get final results
- `GET /api/executions` - List saved executions
- `GET /api/execution/{id}/load` - Load saved execution
- `WS /ws/{execution_id}` - WebSocket for real-time updates

**State Management**:
- `active_plans` dict: plan_id → Plan object
- `active_executions` dict: execution_id → execution info dict

**Key Functions**:
- `run_execution()` - Background task that runs execution
- `save_execution_result()` - Saves to JSON file in `storage/`

### Models (`backend/models.py`)

**Data Structures**:

**NodeStatus** (Enum):
- PENDING → READY → RUNNING → COMPLETED/FAILED

**Node** (Pydantic):
- `id`: Unique identifier
- `name`: Human-readable name
- `description`: What the node does
- `provider`: AI provider name
- `model`: Model name
- `input_description`: Natural language input description
- `output_description`: Natural language output description
- `dependencies`: List of node IDs this depends on
- `status`: Current NodeStatus
- `result`: Natural language result string (when completed)
- `error`: Error message (if failed)
- `execution_time`: Time taken in seconds

**Plan** (Pydantic):
- `plan_id`: Unique identifier
- `user_prompt`: Original user prompt
- `title`: Short title
- `nodes`: List of Node objects
- `edges`: List of {"from": "node_id", "to": "node_id"}
- `status`: "draft" | "executing" | "completed" | "failed"

**ExecutionState** (Pydantic):
- `execution_id`: Unique identifier
- `plan_id`: Associated plan ID
- `node_states`: Dict of node_id → NodeStatus
- `started_at`: ISO timestamp
- `completed_at`: ISO timestamp (when done)
- `logs`: List of log messages

### Config (`backend/config.py`)

**Purpose**: Centralized configuration management.

**Key Methods**:
- `get_api_key(provider)` - Get API key for provider
- `get_available_providers()` - Returns dict of provider → bool
- `get_available_provider_names()` - Returns list of available provider names

**Configuration**:
- API keys from environment variables (via `.env` file)
- `DEFAULT_MODELS` dict maps provider → default model name

### Provider System (`backend/providers/`)

**Base Class** (`base.py`):
- `AIProvider` abstract base class
- Requires `generate(prompt, model, system_prompt)` method
- Requires `get_available_models()` method

**Factory** (`factory.py`):
- `create_provider(provider_name)` - Creates provider instance
- Handles API key retrieval from Config
- Supports: openai, anthropic, gemini, minimax

**Provider Implementations**:
- Each provider inherits from `AIProvider`
- Implements provider-specific API calls
- Handles provider-specific response formats
- Returns natural language strings

## Data Flow Between Components

```
User Prompt
    ↓
Planner.create_plan()
    ↓ (uses AI provider)
JSON DAG Structure
    ↓
Plan Object (with Nodes)
    ↓
API stores in active_plans
    ↓
Executor.execute(plan)
    ↓
For each node:
    - Check dependencies
    - Prepare inputs (natural language)
    - Create provider
    - Execute node (AI call)
    - Store result
    ↓
Final Result Dict
    ↓
API saves to storage/
```

## Key Relationships

- **Planner → Providers**: Uses provider to generate DAG plan
- **Executor → Providers**: Uses providers to execute each node
- **API → Planner**: Creates plans from user requests
- **API → Executor**: Triggers execution
- **All → Config**: Get API keys and available providers
- **All → Models**: Use Pydantic models for data validation

## Extension Points

1. **New Providers**: Add to `providers/` and register in factory
2. **New Prompts**: Add templates to `prompts/` directory
3. **New API Endpoints**: Add routes to `api.py`
4. **New Node Types**: Extend `Node` model (currently all are AI tasks)
5. **Storage Backend**: Replace JSON file storage with database
