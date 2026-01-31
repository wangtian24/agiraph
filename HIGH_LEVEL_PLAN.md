# AI Agent Orchestration Framework - High Level Plan

## Project Overview
A proof-of-concept framework for orchestrating multiple AI agents (or human entities) to collaborate on complex tasks through a DAG-based execution plan with clear contracts between nodes.

## Architecture Overview

### Core Components

1. **Frontend (Web UI)**
   - Chat-like interface for task input
   - DAG visualization component
   - Real-time execution monitoring
   - Comment/feedback system for plan refinement
   - Results presentation

2. **Backend API**
   - Task planning service (creates DAG from user prompt)
   - Plan revision service (incorporates human feedback)
   - Execution engine (DAG executor with parallelization)
   - Status monitoring service (WebSocket/SSE for live updates)
   - AI provider abstraction layer

3. **DAG Execution Engine**
   - Dependency resolution
   - Parallel execution scheduler
   - Node state management
   - Contract validation between nodes

4. **AI Provider Integration**
   - Unified interface for multiple providers
   - API key management
   - Model availability checking
   - Support for: OpenAI, Anthropic (Claude), Google (Gemini), Minimax

## Technology Stack Recommendations

### Frontend
- **Framework**: React or Next.js (for modern UI)
- **DAG Visualization**: React Flow or Cytoscape.js
- **UI Components**: Tailwind CSS + shadcn/ui or Material-UI
- **Real-time Updates**: WebSocket client or Server-Sent Events (SSE)
- **State Management**: Zustand or React Query

### Backend
- **Framework**: FastAPI (Python) or Express.js (Node.js)
  - Recommendation: FastAPI for better AI/ML ecosystem integration
- **WebSocket/SSE**: For real-time status updates
- **Task Queue**: Celery (Python) or Bull (Node.js) for async task execution
- **Database**: SQLite (for PoC) or PostgreSQL for persistence
- **Caching**: Redis (optional, for execution state)

### AI Integration
- **OpenAI**: `openai` Python library
- **Anthropic**: `anthropic` Python library
- **Google Gemini**: `google-generativeai` Python library
- **Minimax**: Custom HTTP client

## Data Structures

### DAG Node (Component)
```python
{
  "id": "node_1",
  "name": "Code Generation",
  "description": "Generate Python code for data processing",
  "type": "ai_task",
  "provider": "openai",
  "model": "gpt-4",
  "input_contract": {
    "requirements": "string",
    "specifications": "string"
  },
  "output_contract": {
    "code": "string",
    "documentation": "string"
  },
  "dependencies": ["node_0"],  # IDs of prerequisite nodes
  "status": "pending|running|completed|failed",
  "result": {},  # Output data when completed
  "error": null
}
```

### DAG Plan
```python
{
  "plan_id": "uuid",
  "user_prompt": "original task description",
  "nodes": [Node],
  "edges": [{"from": "node_id", "to": "node_id"}],
  "status": "draft|approved|executing|completed",
  "revisions": [Revision],  # History of plan changes
  "comments": [Comment]  # Human feedback
}
```

### Execution State
```python
{
  "execution_id": "uuid",
  "plan_id": "uuid",
  "node_states": {"node_id": "status"},
  "started_at": "timestamp",
  "completed_at": "timestamp",
  "logs": [LogEntry]
}
```

## Workflow

### Phase 1: Planning
1. User submits task prompt
2. AI planner analyzes task and creates initial DAG
3. DAG includes:
   - Task breakdown into components
   - Clear input/output contracts for each node
   - Dependency relationships
   - Suggested AI provider/model for each node

### Phase 2: Review & Refinement
1. Frontend displays DAG visualization
2. User can:
   - View node details
   - Add comments on specific nodes
   - Request modifications
3. AI revises plan based on feedback
4. Iterate until user approves

### Phase 3: Execution
1. Execution engine:
   - Validates DAG (no cycles, all contracts defined)
   - Builds execution order (topological sort)
   - Identifies parallelizable nodes
2. Starts execution:
   - Nodes with no dependencies start immediately
   - As nodes complete, dependent nodes become eligible
   - Passes outputs between nodes according to contracts
3. Real-time updates:
   - Node status changes
   - Execution logs
   - Progress indicators

### Phase 4: Results
1. Aggregate all node outputs
2. Present final results in UI
3. Show execution timeline and statistics

## File Structure

```
agiraph/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatInterface.tsx
│   │   │   ├── DAGVisualization.tsx
│   │   │   ├── ExecutionMonitor.tsx
│   │   │   └── ResultsDisplay.tsx
│   │   ├── services/
│   │   │   ├── api.ts
│   │   │   └── websocket.ts
│   │   └── App.tsx
│   ├── package.json
│   └── ...
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── plans.py
│   │   │   ├── execution.py
│   │   │   └── status.py
│   │   ├── core/
│   │   │   ├── dag.py
│   │   │   ├── executor.py
│   │   │   └── planner.py
│   │   ├── providers/
│   │   │   ├── base.py
│   │   │   ├── openai.py
│   │   │   ├── anthropic.py
│   │   │   ├── gemini.py
│   │   │   └── minimax.py
│   │   ├── models/
│   │   │   └── schemas.py
│   │   └── config.py
│   ├── requirements.txt
│   └── main.py
├── config/
│   └── api_keys.example.env
├── README.md
└── HIGH_LEVEL_PLAN.md
```

## Key Features to Implement

### 1. AI Planner
- Takes user prompt
- Uses AI to break down into sub-tasks
- Defines contracts (input/output schemas)
- Creates dependency graph
- Suggests appropriate AI models for each task

### 2. Contract System
- Each node defines:
  - Required inputs (with schema)
  - Expected outputs (with schema)
- Validation before passing data between nodes
- Type checking and structure validation

### 3. Execution Engine
- Topological sort for execution order
- Parallel execution where possible
- State management (pending, running, completed, failed)
- Error handling and retry logic
- Output passing between nodes

### 4. Provider Abstraction
- Unified interface for all AI providers
- Dynamic model availability checking
- API key management (environment variables or config file)
- Fallback mechanisms

### 5. Real-time Monitoring
- WebSocket or SSE connection
- Live status updates
- Execution logs streaming
- Progress tracking

## Implementation Phases

### Phase 1: Core Backend (MVP)
- [ ] Basic FastAPI server
- [ ] AI provider integrations (OpenAI, Claude, Gemini, Minimax)
- [ ] Simple planner (single AI call to create DAG)
- [ ] Basic DAG executor
- [ ] REST API endpoints

### Phase 2: Frontend Basics
- [ ] React app setup
- [ ] Chat interface
- [ ] Basic DAG visualization
- [ ] API integration

### Phase 3: Planning & Refinement
- [ ] Plan revision logic
- [ ] Comment system
- [ ] DAG editing capabilities

### Phase 4: Execution & Monitoring
- [ ] Real-time status updates (WebSocket/SSE)
- [ ] Execution logs
- [ ] Progress indicators
- [ ] Error handling UI

### Phase 5: Polish
- [ ] Results presentation
- [ ] Execution statistics
- [ ] UI/UX improvements
- [ ] Documentation

## Configuration

### API Keys Management
- Environment variables (`.env` file)
- Config file option
- UI for key management (optional, for PoC)
- Validation on startup

### Model Availability
- Check available models per provider on startup
- Cache model lists
- Validate model selection before execution

## Future Enhancements (Beyond PoC)
- Human-in-the-loop nodes
- Payment/economy system between agents
- Agent reputation system
- More complex contract types
- Persistent storage of plans and executions
- Plan templates and reuse
- Multi-tenant support

## Next Steps
1. Review and approve this plan
2. Set up project structure
3. Implement Phase 1 (Core Backend)
4. Implement Phase 2 (Frontend Basics)
5. Iterate and refine
