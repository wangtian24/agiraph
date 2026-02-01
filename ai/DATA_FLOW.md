# Data Flow and Execution Patterns

## Planning Flow

```
1. User submits prompt + provider/model selection
   ↓
2. API receives POST /api/plan
   ↓
3. Planner.create_plan() called
   ↓
4. Planner loads system/user prompts from templates
   ↓
5. Planner calls AI provider.generate() with prompts
   ↓
6. AI returns JSON DAG structure:
   {
     "nodes": [...],
     "edges": [...]
   }
   ↓
7. Planner parses JSON and creates Node objects
   ↓
8. Planner validates all providers are available
   ↓
9. Planner creates Plan object
   ↓
10. API stores Plan in active_plans dict
   ↓
11. API returns plan JSON to frontend
```

## Execution Flow

```
1. User triggers execution
   ↓
2. API receives POST /api/execute
   ↓
3. API creates execution_id and stores in active_executions
   ↓
4. API receives POST /api/execute/{id}/start
   ↓
5. API spawns background task: run_execution()
   ↓
6. run_execution() calls Executor.execute(plan)
   ↓
7. Executor validates all nodes have available providers
   ↓
8. Executor builds dependency graph
   ↓
9. Executor enters execution loop:
   
   While nodes remain:
     a. Find ready nodes (all dependencies completed)
     b. For each ready node:
        - Mark as RUNNING
        - Prepare inputs from dependency results (natural language)
        - Create provider instance
        - Build execution prompt from template
        - Call provider.generate()
        - Store result in node.result (natural language string)
        - Mark as COMPLETED
     c. Execute all ready nodes in parallel (asyncio.create_task)
     d. Wait for all tasks in wave to complete
     e. Store results in node_results dict
   
   ↓
10. Executor returns result dict:
    {
      "status": "completed" | "failed",
      "node_results": {node_id: "result string"},
      "execution_logs": [...]
    }
   ↓
11. run_execution() saves result to JSON file in storage/
   ↓
12. run_execution() updates active_executions with final status
```

## Node Input Preparation

When a node has dependencies, its inputs are prepared as natural language:

```
For each dependency node_id:
  1. Look up result in node_results dict
  2. Get dependency node name for context
  3. Format as: "From {node_name} ({node_id}):\n{result}"
  4. Combine all dependency results with "\n\n"
  
Example:
  "From Research Topic X (node_1):
  [Research results about X...]
  
  From Research Topic Y (node_2):
  [Research results about Y...]"
```

## Parallel Execution Pattern

```
Initial State:
  completed = set()
  ready_nodes = [node_0]  # No dependencies

Wave 1:
  Execute: [node_0] in parallel
  Wait for completion
  completed = {node_0}

Wave 2:
  ready_nodes = [node_1, node_2, node_3]  # All depend on node_0
  Execute: [node_1, node_2, node_3] in parallel
  Wait for completion
  completed = {node_0, node_1, node_2, node_3}

Wave 3:
  ready_nodes = [node_4]  # Depends on node_1, node_2, node_3
  Execute: [node_4] in parallel
  Wait for completion
  completed = {node_0, node_1, node_2, node_3, node_4}
  
Done!
```

## Real-time Updates Flow

```
1. Frontend connects to WS /ws/{execution_id}
   ↓
2. API WebSocket handler accepts connection
   ↓
3. Every 1 second:
   a. Read execution info from active_executions
   b. Read plan from active_plans
   c. Get current node states from plan.nodes
   d. Send JSON update:
      {
        "status": "executing",
        "node_states": {"node_0": "completed", "node_1": "running", ...},
        "logs": ["Last 10 log messages"]
      }
   ↓
4. Frontend receives update and updates UI
   ↓
5. Repeat until execution completes or connection closes
```

## Storage Pattern

Execution results are saved as JSON files:

```
storage/
  {execution_id}.json
  
Structure:
{
  "execution_id": "uuid",
  "plan_id": "uuid",
  "user_prompt": "...",
  "title": "...",
  "timestamp": "ISO timestamp",
  "status": "completed" | "failed",
  "nodes": [
    {
      "id": "node_0",
      "name": "...",
      "description": "...",
      "provider": "openai",
      "model": "gpt-4o-mini",
      "status": "completed",
      "result": "Natural language result...",
      "error": null,
      "execution_time": 2.5
    },
    ...
  ],
  "node_results": {
    "node_0": "Result string...",
    "node_1": "Result string...",
    ...
  },
  "execution_logs": [
    "Starting execution...",
    "Completed node node_0...",
    ...
  ]
}
```

## Error Handling Flow

```
Node Execution Error:
  1. Exception caught in _execute_node()
  2. Node status set to FAILED
  3. Node.error set to error message
  4. Exception logged
  5. Execution continues with other nodes
  
Dependency Failure:
  1. Executor detects nodes with failed dependencies
  2. Logs error: "Cannot proceed - dependencies failed"
  3. Execution stops
  4. Plan status set to "failed"
  
Provider Unavailable:
  1. Validated before execution starts
  2. Raises ValueError with available providers list
  3. Execution never starts
  
JSON Parse Error (Planning):
  1. Caught in Planner.create_plan()
  2. Raises ValueError with error details
  3. API returns 500 error to frontend
```

## Key Data Structures

**active_plans** (dict):
```python
{
  "plan_id": Plan object
}
```

**active_executions** (dict):
```python
{
  "execution_id": {
    "execution_id": "uuid",
    "plan_id": "uuid",
    "status": "executing" | "completed" | "failed",
    "started_at": "ISO timestamp",
    "completed_at": "ISO timestamp" | None,
    "node_states": {"node_id": "status"},
    "logs": ["log message", ...]
  }
}
```

**node_results** (in Executor):
```python
{
  "node_id": "Natural language result string"
}
```

## State Transitions

**Plan Status**:
- "draft" → "executing" → "completed" | "failed"

**Node Status**:
- PENDING → RUNNING → COMPLETED | FAILED

**Execution Status**:
- "starting" → "executing" → "completed" | "failed"
