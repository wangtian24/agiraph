<p align="center">
  <img src="giraffe.png" alt="Agiraph Logo" width="200" />
</p>

# AI Agent Orchestration Framework

A proof-of-concept framework for orchestrating AI agents in a DAG (Directed Acyclic Graph) structure, enabling parallel execution of independent tasks with clear input/output contracts.

## Features

- **DAG-based Planning**: AI creates execution plans as directed acyclic graphs
- **Parallel Execution**: Independent nodes execute concurrently
- **Multi-Provider Support**: OpenAI, Anthropic (Claude), Google Gemini, and Minimax
- **Web UI**: Simple web interface for creating plans, visualizing DAGs, and monitoring execution
- **Result Storage**: All execution results are saved to JSON files for later review
- **Real-time Updates**: WebSocket support for live execution status

## Setup

### Prerequisites

- Python 3.10+
- Poetry (for dependency management)

### Installation

1. Install dependencies:
```bash
poetry install
```

2. Create a `.env` file in the project root with your API keys:
```env
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
GEMINI_API_KEY=your_gemini_key
MINIMAX_API_KEY=your_minimax_key
MINIMAX_GROUP_ID=your_group_id  # Optional for Minimax
```

Only providers with configured API keys will be available.

### Running the Web Server

1. Start the FastAPI backend:
```bash
poetry run python run_server.py
```

Or using uvicorn directly:
```bash
poetry run uvicorn backend.api:app --host 0.0.0.0 --port 8000 --reload
```

2. In a separate terminal, start the Next.js frontend:
```bash
cd frontend
npm install
npm run dev
```

3. Open your browser to `http://localhost:3000`

The Next.js frontend will proxy API requests to the backend running on port 8000.

### Running the CLI

For a text-based interface:
```bash
poetry run python main.py
```

## Usage

### Web Interface

1. **Create a Plan**: Enter a task prompt and select a provider/model
2. **Review DAG**: Visualize the execution plan with node dependencies
3. **Execute**: Start execution and monitor progress in real-time
4. **View Results**: See results for each node, including errors and execution times
5. **Load Saved Executions**: Review previously saved execution results

### CLI Interface

The CLI provides an interactive text-based interface:
- Select a provider and model
- Enter your task prompt
- Review the generated DAG plan
- Execute and monitor progress
- View final results

## Architecture

- **`backend/planner.py`**: AI planner that creates DAG plans from user prompts
- **`backend/executor.py`**: Executes DAG plans with parallel node execution
- **`backend/api.py`**: FastAPI backend with REST endpoints and WebSocket support
- **`backend/providers/`**: Multi-provider AI abstraction layer
- **`backend/models.py`**: Data models for plans, nodes, and execution state
- **`frontend/`**: Next.js frontend with DAG visualization and markdown rendering

## Storage

Execution results are automatically saved to `storage/` directory as JSON files. Each file contains:
- Execution metadata (ID, timestamp, status)
- Original user prompt
- Node results and execution times
- Execution logs

## Testing Providers

Test individual provider integrations:
```bash
poetry run python test_providers.py
```

This will test all configured providers with a simple question and display any errors.

## Development

### Prompt Files

All key prompts are stored in `backend/prompts/` directory for easy iteration:
- `planner_system.txt` - System prompt for the planner AI
- `planner_user.txt` - User prompt template for planning requests
- `node_execution_system.txt` - System prompt for node execution
- `node_execution_user.txt` - User prompt template for node execution

Edit these files directly to iterate on prompts without modifying code.

### Adding a New Provider

1. Create a new provider class in `backend/providers/` inheriting from `AIProvider`
2. Implement the `generate()` method
3. Register it in `backend/providers/factory.py`
4. Add configuration in `backend/config.py`

## License

MIT
