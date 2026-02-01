# Coding Guidelines

Guidelines and conventions for working with this codebase.

## Code Style

### Python

- **Type Hints**: Use type hints for function parameters and return types
- **Async/Await**: Use `async`/`await` for all AI provider calls and I/O operations
- **Error Handling**: Use try/except blocks with specific exception types
- **Docstrings**: Use docstrings for classes and public methods
- **Imports**: Group imports: stdlib, third-party, local

**Example**:
```python
from typing import List, Optional
from fastapi import HTTPException

from .models import Plan, Node
from .providers.factory import create_provider

async def create_plan(prompt: str) -> Plan:
    """Create a plan from user prompt."""
    try:
        # Implementation
        pass
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### TypeScript/React

- **TypeScript**: Use TypeScript for all components, avoid `any` when possible
- **Hooks**: Use functional components with hooks
- **State**: Use `useState` for local state, consider context for shared state
- **Effects**: Use `useEffect` for side effects, clean up subscriptions

**Example**:
```typescript
const [plan, setPlan] = useState<Plan | null>(null);

useEffect(() => {
  // Setup
  return () => {
    // Cleanup
  };
}, [dependencies]);
```

## Architecture Patterns

### Provider Pattern

All AI providers implement the `AIProvider` abstract base class:

```python
class AIProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, model: str, 
                      system_prompt: Optional[str] = None) -> str:
        pass
```

**Adding a New Provider**:
1. Create `backend/providers/{name}_provider.py`
2. Inherit from `AIProvider`
3. Implement `generate()` and `get_available_models()`
4. Register in `factory.py`
5. Add API key to `Config` class

### Factory Pattern

Use factory function for provider creation:
```python
provider = create_provider("openai")
```

This centralizes provider instantiation and handles configuration.

### Template Pattern

Prompts stored as text files in `backend/prompts/`:
- Load with `load_prompt(filename)`
- Format with `format_prompt(template, **kwargs)`
- Allows iteration without code changes

## Error Handling

### Backend

- **Validation**: Validate inputs early, raise `ValueError` for invalid data
- **API Errors**: Use `HTTPException` with appropriate status codes
- **Provider Errors**: Catch provider-specific exceptions, wrap in descriptive errors
- **Logging**: Log errors with context (node_id, execution_id, etc.)

**Example**:
```python
try:
    response = await provider.generate(prompt, model)
except ProviderError as e:
    self._log(f"Node {node.id} failed: {e}")
    node.status = NodeStatus.FAILED
    node.error = str(e)
    raise
```

### Frontend

- **API Errors**: Handle axios errors gracefully
- **User Feedback**: Show error messages to users
- **Fallbacks**: Provide fallback UI when data unavailable

**Example**:
```typescript
try {
  const response = await axios.post('/api/plan', { prompt, provider, model });
  setPlan(response.data);
} catch (error: any) {
  alert(`Error: ${error.response?.data?.detail || error.message}`);
}
```

## Data Flow

### Natural Language Results

**Key Decision**: Nodes return natural language text, not structured JSON.

**Rationale**:
- Simpler contracts (no schema validation)
- More flexible (AI can adapt output format)
- Easier to pass between nodes

**Implications**:
- Don't parse node results as JSON
- Pass results as-is between nodes
- Display results as markdown in frontend

### State Management

**Backend**:
- Use in-memory dictionaries for active plans/executions
- Persist to JSON files in `storage/` for long-term storage
- WebSocket updates reflect current in-memory state

**Frontend**:
- React state for UI state
- Poll or WebSocket for execution status
- Load saved executions from API

## Testing Patterns

### Provider Testing

Test providers independently:
```python
# test_providers.py
provider = create_provider("openai")
result = await provider.generate("Test prompt", "gpt-4o-mini")
assert result is not None
```

### Integration Testing

Test full execution flow:
1. Create plan
2. Execute plan
3. Verify results
4. Check storage

## Common Patterns

### Async Execution

Always use `asyncio` for parallel execution:
```python
tasks = [asyncio.create_task(execute_node(node)) for node in ready_nodes]
results = await asyncio.gather(*tasks)
```

### Dependency Resolution

Use topological sort pattern:
1. Build dependency graph
2. Find nodes with no dependencies (ready nodes)
3. Execute ready nodes in parallel
4. Mark as completed, repeat

### Prompt Formatting

Use template system:
```python
template = load_prompt("node_execution_user.txt")
prompt = format_prompt(
    template,
    description=node.description,
    inputs_section=inputs_text,
    ...
)
```

## File Organization

### Backend

- `backend/api.py` - API endpoints only
- `backend/planner.py` - Planning logic
- `backend/executor.py` - Execution logic
- `backend/models.py` - Data models
- `backend/config.py` - Configuration
- `backend/providers/` - Provider implementations
- `backend/prompts/` - Prompt templates

### Frontend

- `frontend/pages/` - Next.js pages (routes)
- `frontend/styles/` - CSS/Tailwind styles
- Keep components in same file as page (or extract if reused)

## Naming Conventions

### Python

- **Classes**: PascalCase (`DAGExecutor`, `Node`)
- **Functions**: snake_case (`create_plan`, `execute_node`)
- **Constants**: UPPER_SNAKE_CASE (`DEFAULT_MODELS`)
- **Private**: Leading underscore (`_log`, `_execute_node`)

### TypeScript

- **Components**: PascalCase (`Home`, `ExecutionView`)
- **Functions**: camelCase (`createPlan`, `executePlan`)
- **Interfaces**: PascalCase (`Plan`, `Node`)
- **Constants**: UPPER_SNAKE_CASE or camelCase

## Documentation

### Code Comments

- Explain **why**, not **what**
- Document complex algorithms
- Note edge cases and assumptions

### Docstrings

Use docstrings for public APIs:
```python
async def create_plan(self, user_prompt: str, 
                     force_provider: str = None) -> Plan:
    """Create a DAG plan from user prompt.
    
    Args:
        user_prompt: The task to plan
        force_provider: If provided, all nodes will use this provider
        
    Returns:
        Plan object with nodes and edges
        
    Raises:
        ValueError: If planning fails or response invalid
    """
```

## Performance Considerations

### Parallel Execution

- Execute independent nodes concurrently
- Use `asyncio.gather()` for parallel tasks
- Don't block on I/O operations

### Caching

- Cache provider instances when possible
- Cache prompt templates (loaded once)
- Consider caching plan results if expensive

### Storage

- JSON files are simple but not scalable
- Consider database for production
- Clean up old execution files periodically

## Security

### API Keys

- Never commit API keys to repository
- Use environment variables or `.env` file
- Validate API keys before use

### Input Validation

- Validate user inputs (prompts, IDs)
- Sanitize inputs before passing to AI
- Limit prompt length if needed

### Error Messages

- Don't expose internal errors to users
- Log detailed errors server-side
- Return user-friendly error messages

## Future Considerations

### Scalability

- Current design uses in-memory state (not production-ready)
- Consider Redis for shared state
- Use database for persistence
- Add task queue (Celery) for long-running tasks

### Monitoring

- Add logging framework (structlog)
- Track execution metrics
- Monitor API usage and costs
- Alert on failures

### Testing

- Add unit tests for core logic
- Add integration tests for API
- Test provider error handling
- Test edge cases (circular deps, etc.)
