# Poetry Usage Guide

This project uses [Poetry](https://python-poetry.org/) for dependency management.

## Installation

First, install Poetry if you haven't already:

```bash
# On macOS/Linux
curl -sSL https://install.python-poetry.org | python3 -

# Or using pip
pip install poetry

# Or using homebrew (macOS)
brew install poetry
```

## Basic Commands

### Install Dependencies

```bash
# Install all dependencies (including dev dependencies)
poetry install

# Install only production dependencies
poetry install --no-dev
```

### Add Dependencies

```bash
# Add a production dependency
poetry add package-name

# Add a development dependency
poetry add --group dev package-name

# Add with version constraint
poetry add "package-name>=1.0.0"
```

### Remove Dependencies

```bash
# Remove a dependency
poetry remove package-name
```

### Update Dependencies

```bash
# Update all dependencies to latest compatible versions
poetry update

# Update a specific package
poetry update package-name
```

### Show Dependencies

```bash
# Show dependency tree
poetry show --tree

# Show a specific package
poetry show package-name
```

## Running the Application

### Activate Poetry Shell

```bash
# Activate the Poetry virtual environment
poetry shell

# Then run your scripts normally
python main.py
python test_providers.py
```

### Run Commands Without Activating Shell

```bash
# Run commands in the Poetry environment
poetry run python main.py
poetry run python test_providers.py

# Or use the defined script
poetry run agiraph
```

## Virtual Environment Management

```bash
# Show virtual environment path
poetry env info

# Create virtual environment in project directory
poetry config virtualenvs.in-project true

# Remove virtual environment
poetry env remove python
```

## Export Requirements (for compatibility)

If you need a requirements.txt file (e.g., for Docker):

```bash
# Export production dependencies
poetry export -f requirements.txt --output requirements.txt --without-hashes

# Export with dev dependencies
poetry export -f requirements.txt --output requirements-dev.txt --with dev --without-hashes
```

## Common Workflow

1. **Initial Setup:**
   ```bash
   poetry install
   ```

2. **Add a new dependency:**
   ```bash
   poetry add new-package
   ```

3. **Run the application:**
   ```bash
   poetry run python main.py
   ```

4. **Update dependencies:**
   ```bash
   poetry update
   ```

## Configuration

Poetry configuration is in `pyproject.toml`. Key sections:
- `[tool.poetry.dependencies]` - Production dependencies
- `[tool.poetry.group.dev.dependencies]` - Development dependencies
- `[tool.poetry.scripts]` - Command-line scripts

## Troubleshooting

### Clear Poetry Cache
```bash
poetry cache clear pypi --all
```

### Reinstall Dependencies
```bash
poetry install --no-cache
```

### Check for Issues
```bash
poetry check
```
