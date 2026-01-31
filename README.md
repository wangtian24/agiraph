# AI Agent Orchestration Framework

A proof-of-concept framework for orchestrating multiple AI agents to collaborate on complex tasks through a DAG-based execution plan with clear contracts between nodes.

## Features

- **Intelligent Planning**: AI creates a DAG from user prompts, maximizing parallelism
- **Parallel Execution**: Executes independent nodes simultaneously
- **Multi-Provider Support**: OpenAI, Anthropic (Claude), Google Gemini, Minimax
- **Clear Contracts**: Each node has explicit input/output contracts
- **Interactive CLI**: Text-based interface with DAG visualization

## Setup

1. **Install dependencies:**

   **Using Poetry (recommended):**
   ```bash
   # Install Poetry if you haven't already
   curl -sSL https://install.python-poetry.org | python3 -
   
   # Install project dependencies
   poetry install
   
   # Activate the virtual environment
   poetry shell
   ```
   
   **Or using pip:**
   ```bash
   pip install -r requirements.txt
   ```
   
   See [POETRY_USAGE.md](POETRY_USAGE.md) for detailed Poetry commands.

2. **Configure API keys:**
   Copy `.env.example` to `.env` and fill in your API keys:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your keys:
   ```
   OPENAI_API_KEY=your_key_here
   ANTHROPIC_API_KEY=your_key_here
   GOOGLE_API_KEY=your_key_here
   MINIMAX_API_KEY=your_key_here
   MINIMAX_GROUP_ID=your_group_id_here
   ```
   
   You only need to configure the providers you want to use.

3. **Run the CLI:**
   
   **With Poetry:**
   ```bash
   poetry run python main.py
   # Or if you're in poetry shell:
   python main.py
   ```
   
   **With pip:**
   ```bash
   python main.py
   ```

## Usage

1. Enter a task description when prompted
2. Review the generated DAG plan
3. Optionally view detailed node information
4. Confirm execution
5. Monitor execution in real-time
6. View results and logs

## Example

```
Enter your task: Create a Python script that fetches weather data and generates a report

The planner will create a DAG like:
- node_0: Fetch weather data (no dependencies)
- node_1: Process weather data (depends on node_0)
- node_2: Generate report (depends on node_1)

Nodes node_0 can run immediately, then node_1, then node_2.
```

## Architecture

- `app/models.py`: Data structures for nodes, plans, and execution state
- `app/planner.py`: AI planner that creates DAGs from prompts
- `app/executor.py`: DAG executor with parallel execution
- `app/providers/`: AI provider integrations
- `app/cli.py`: Command-line interface
- `app/config.py`: Configuration management

## How It Works

1. **Planning**: The planner uses an AI model to break down tasks into a DAG with clear contracts
2. **Review**: User reviews the plan structure
3. **Execution**: The executor runs nodes in parallel waves based on dependencies
4. **Results**: Aggregated results from all nodes

## Notes

- The planner is designed to maximize parallelism by minimizing unnecessary dependencies
- Each node executes independently with clear input/output contracts
- Failed nodes are logged but don't necessarily stop execution of independent nodes
- All node communication happens through the contract system
