# System Architecture

## Overview

This is an AI Agent Orchestration Framework that enables parallel execution of AI tasks through a DAG (Directed Acyclic Graph) structure. The system breaks down complex tasks into independent nodes that can execute concurrently when dependencies allow.

## High-Level Architecture

```
┌─────────────────┐
│   Frontend       │  Next.js + React + TypeScript
│   (Port 3000)    │  - DAG Visualization (ReactFlow)
└────────┬─────────┘  - Real-time Status (WebSocket)
         │
         │ HTTP/WebSocket
         │
┌────────▼─────────┐
│   Backend API    │  FastAPI (Port 8000)
│   (backend/api)  │  - REST endpoints
└────────┬─────────┘  - WebSocket for real-time updates
         │
    ┌────┴────┬──────────────┬─────────────┐
    │         │              │             │
┌───▼───┐ ┌──▼───┐    ┌──────▼──────┐ ┌───▼──────┐
│Planner│ │Executor│   │  Providers  │ │  Storage │
│       │ │        │   │  Factory    │ │  (JSON)  │
└───────┘ └────────┘   └─────────────┘ └──────────┘
```

## Core Components

### 1. Frontend (`frontend/`)
- **Framework**: Next.js 14 with TypeScript
- **Visualization**: ReactFlow for DAG rendering
- **Communication**: Axios for REST, WebSocket for real-time updates
- **Key Files**:
  - `pages/index.tsx` - Main interface for creating plans
  - `pages/execution/[id].tsx` - Execution detail view
  - Next.js rewrites proxy `/api/*` to `http://localhost:8000/api/*`

### 2. Backend API (`backend/api.py`)
- **Framework**: FastAPI
- **Responsibilities**:
  - Plan creation endpoints
  - Execution management
  - Real-time status via WebSocket
  - Storage persistence (JSON files in `storage/`)
- **In-Memory State**: `active_plans` and `active_executions` dictionaries

### 3. Planner (`backend/planner.py`)
- **Purpose**: Converts user prompts into DAG plans
- **Process**:
  1. Takes user prompt + provider/model selection
  2. Calls AI provider with planning prompts
  3. Parses JSON response into `Plan` object with `Node` objects
  4. Validates provider availability
  5. Generates title if not provided

### 4. Executor (`backend/executor.py`)
- **Purpose**: Executes DAG plans with parallelization
- **Algorithm**:
  1. Builds dependency graph
  2. Identifies ready nodes (all dependencies completed)
  3. Executes ready nodes in parallel using `asyncio`
  4. Passes results between nodes as natural language
  5. Continues until all nodes complete or fail

### 5. Providers (`backend/providers/`)
- **Pattern**: Abstract base class `AIProvider` with concrete implementations
- **Supported**: OpenAI, Anthropic (Claude), Google Gemini, Minimax
- **Factory**: `factory.py` creates provider instances based on name
- **Configuration**: API keys from environment variables via `Config`

### 6. Models (`backend/models.py`)
- **Node**: Represents a task in the DAG
  - Has dependencies, provider, model, status
  - Stores natural language results (not structured JSON)
- **Plan**: Complete execution plan with nodes and edges
- **NodeStatus**: Enum (PENDING, READY, RUNNING, COMPLETED, FAILED)

## Data Flow

### Plan Creation Flow
```
User Prompt → API `/api/plan` → Planner.create_plan()
  → AI Provider (planning prompt) → JSON Plan
  → Validate providers → Return Plan to frontend
```

### Execution Flow
```
User clicks Execute → API `/api/execute` → Create execution_id
  → API `/api/execute/{id}/start` → Background task
  → DAGExecutor.execute() → Parallel node execution
  → Results saved to storage/ → WebSocket updates
  → Frontend displays results
```

### Node Execution Flow
```
Node Ready → _execute_node()
  → Prepare inputs from dependency results (natural language)
  → Load prompt templates
  → Call AI Provider.generate()
  → Store natural language result
  → Mark node as COMPLETED
```

## Key Design Decisions

1. **Natural Language Results**: Nodes return natural language text, not structured JSON. This simplifies contracts and makes the system more flexible.

2. **Parallel Execution**: Uses `asyncio` to execute independent nodes concurrently, maximizing throughput.

3. **Provider Abstraction**: All AI providers implement the same interface, making it easy to add new providers.

4. **Prompt Templates**: Prompts stored in `backend/prompts/` as text files for easy iteration without code changes.

5. **Storage**: Execution results saved as JSON files in `storage/` directory for persistence and review.

6. **Real-time Updates**: WebSocket provides live status updates during execution.

## File Organization

```
agiraph/
├── backend/
│   ├── api.py           # FastAPI endpoints
│   ├── planner.py       # DAG plan creation
│   ├── executor.py      # DAG execution engine
│   ├── models.py        # Data models (Node, Plan)
│   ├── config.py        # Configuration & API keys
│   ├── providers/       # AI provider implementations
│   └── prompts/         # Prompt templates
├── frontend/
│   ├── pages/           # Next.js pages
│   └── styles/          # CSS/Tailwind
├── storage/              # Execution results (JSON)
└── ai/                   # AI-oriented documentation
```

## Dependencies

- **Backend**: FastAPI, Pydantic, python-dotenv, provider-specific SDKs
- **Frontend**: Next.js, React, ReactFlow, Axios, react-markdown
- **Python**: 3.10+

## Configuration

- API keys in `.env` file or environment variables
- Backend runs on port 8000
- Frontend runs on port 3000 (proxies to backend)
