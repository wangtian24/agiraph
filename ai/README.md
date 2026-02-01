# AI-Oriented Documentation

This directory contains comprehensive documentation designed to help AI coding agents quickly understand and work with this codebase.

## Quick Start for AI Agents

When working on this project, read these files in order:

1. **ARCHITECTURE.md** - Start here for high-level system overview
2. **COMPONENTS.md** - Detailed component documentation
3. **CODING_GUIDELINES.md** - Coding patterns and conventions
4. **API_REFERENCE.md** - Complete API endpoint documentation

## Documentation Structure

### ARCHITECTURE.md
- System overview and high-level design
- Component relationships
- Data flow diagrams
- Key design decisions
- File organization

**Read this when**: You need to understand how the system works overall.

### COMPONENTS.md
- Detailed documentation of each component
- Method signatures and purposes
- Input/output formats
- Implementation details

**Read this when**: You're working on a specific component or need to understand its internals.

### CODING_GUIDELINES.md
- Code style and conventions
- Architecture patterns
- Error handling approaches
- Testing patterns
- Common code patterns

**Read this when**: You're writing new code or modifying existing code.

### API_REFERENCE.md
- Complete API endpoint documentation
- Request/response formats
- WebSocket protocol
- Data models
- Usage examples

**Read this when**: You're working on API endpoints or frontend-backend integration.

## How to Use These Docs

### For New Features
1. Read ARCHITECTURE.md to understand system design
2. Read COMPONENTS.md to find relevant components
3. Read CODING_GUIDELINES.md for patterns to follow
4. Reference API_REFERENCE.md if working with APIs

### For Bug Fixes
1. Read COMPONENTS.md for the affected component
2. Check CODING_GUIDELINES.md for error handling patterns
3. Review API_REFERENCE.md if it's an API issue

### For Refactoring
1. Read ARCHITECTURE.md to understand current design
2. Read COMPONENTS.md to understand dependencies
3. Follow CODING_GUIDELINES.md for new patterns

## Key Concepts

### DAG Execution
The system executes tasks as a Directed Acyclic Graph (DAG), allowing parallel execution of independent nodes.

### Natural Language Results
Nodes return natural language text, not structured JSON. This simplifies contracts and makes the system flexible.

### Provider Abstraction
All AI providers implement the same interface, making it easy to add new providers or switch between them.

### Parallel Execution
The executor identifies nodes with satisfied dependencies and executes them concurrently using `asyncio`.

## Related Documentation

- **Root README.md** - Project setup and usage
- **backend/providers/PROVIDER_FIXES.md** - Provider-specific fixes and improvements
- **frontend/README.md** - Frontend setup and features

## Maintenance

These docs should be updated when:
- Architecture changes significantly
- New components are added
- Coding patterns evolve
- API endpoints change

Keep documentation close to code changes to maintain accuracy.
