"""Configuration loading and defaults.

Reads from config.toml at the project root, with environment variable overrides.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

# Look for .env in the package's parent directory (project root)
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")
load_dotenv()  # also check cwd

# ---------------------------------------------------------------------------
# Load config.toml
# ---------------------------------------------------------------------------

_toml_path = _project_root / "config.toml"
_cfg: dict = {}
if _toml_path.exists():
    with open(_toml_path, "rb") as f:
        _cfg = tomllib.load(f)

_server = _cfg.get("server", {})
_agent = _cfg.get("agent", {})
_search = _cfg.get("search", {})

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(os.getenv("AGIRAPH_BASE_DIR", _agent.get("base_dir", str(Path.cwd() / "agents"))))
BASE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Provider API keys (env-only, never in toml)
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# Agent defaults
# ---------------------------------------------------------------------------

DEFAULT_MODEL = os.getenv("AGIRAPH_DEFAULT_MODEL", _agent.get("default_model", "anthropic/claude-sonnet-4-5"))
DEFAULT_MAX_ITERATIONS = int(os.getenv("AGIRAPH_MAX_ITERATIONS", _agent.get("max_iterations", 20)))
DEFAULT_TEMPERATURE = float(os.getenv("AGIRAPH_TEMPERATURE", _agent.get("temperature", 0.7)))
DEFAULT_MAX_TOKENS = int(os.getenv("AGIRAPH_MAX_TOKENS", _agent.get("max_tokens", 4096)))
MAX_CONCURRENT_WORKERS = int(os.getenv("AGIRAPH_MAX_WORKERS", _agent.get("max_workers", 4)))

# Human interaction
HUMAN_RESPONSE_TIMEOUT = int(os.getenv("AGIRAPH_HUMAN_TIMEOUT", _agent.get("human_timeout", 3600)))

# Memory
MAX_MEMORY_INLINE = int(os.getenv("AGIRAPH_MAX_MEMORY_INLINE", _agent.get("max_memory_inline", 20000)))

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

SERVER_HOST = os.getenv("AGIRAPH_HOST", _server.get("host", "0.0.0.0"))
SERVER_PORT = int(os.getenv("AGIRAPH_PORT", _server.get("port", 8000)))

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

SEARCH_PROVIDER = os.getenv("AGIRAPH_SEARCH_PROVIDER", _search.get("provider", "brave"))
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")

NATIVE_SEARCH_MAX_USES = int(os.getenv("AGIRAPH_SEARCH_MAX_USES", _search.get("max_native_uses", 5)))

# ---------------------------------------------------------------------------
# Model capabilities — native tool support per provider
# ---------------------------------------------------------------------------

MODEL_NATIVE_SEARCH = {
    "anthropic/claude-sonnet-4-5": True,
    "anthropic/claude-opus-4-6": True,
    "anthropic/claude-haiku-4-5": True,
    "openai/gpt-4o": False,
    "openai/gpt-4.1": False,
    "openai/o3-mini": False,
    "claude-code/sonnet": False,
    "claude-code/opus": False,
    "claude-code/haiku": False,
}
