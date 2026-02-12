"""Configuration loading and defaults."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Look for .env in the package's parent directory (project root)
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")
load_dotenv()  # also check cwd

# Paths
BASE_DIR = Path(os.getenv("AGIRAPH_BASE_DIR", Path.cwd() / "agents"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

# Provider API keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Defaults
DEFAULT_MODEL = os.getenv("AGIRAPH_DEFAULT_MODEL", "anthropic/claude-sonnet-4-5")
DEFAULT_MAX_ITERATIONS = int(os.getenv("AGIRAPH_MAX_ITERATIONS", "20"))
DEFAULT_TEMPERATURE = float(os.getenv("AGIRAPH_TEMPERATURE", "0.7"))
DEFAULT_MAX_TOKENS = int(os.getenv("AGIRAPH_MAX_TOKENS", "4096"))
MAX_CONCURRENT_WORKERS = int(os.getenv("AGIRAPH_MAX_WORKERS", "4"))

# Human interaction
HUMAN_RESPONSE_TIMEOUT = int(os.getenv("AGIRAPH_HUMAN_TIMEOUT", "3600"))  # 1 hour

# Memory
MAX_MEMORY_INLINE = int(os.getenv("AGIRAPH_MAX_MEMORY_INLINE", "20000"))  # ~20KB before grep mode

# Server
SERVER_HOST = os.getenv("AGIRAPH_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("AGIRAPH_PORT", "8000"))

# Search provider (fallback for models without native search)
SEARCH_PROVIDER = os.getenv("AGIRAPH_SEARCH_PROVIDER", "brave")  # brave | serper
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")

# ---------------------------------------------------------------------------
# Model capabilities — native tool support per provider
# ---------------------------------------------------------------------------
# Models that support native server-side web search via their API.
# When native search is available, we use it instead of our own search tools.
NATIVE_SEARCH_MAX_USES = int(os.getenv("AGIRAPH_SEARCH_MAX_USES", "5"))  # limit cost

# Anthropic: all modern Claude models support web_search_20250305
# OpenAI: web search requires Responses API (not Chat Completions) — not yet supported
# Claude Code: handles search internally
MODEL_NATIVE_SEARCH = {
    # Anthropic — native web search via API
    "anthropic/claude-sonnet-4-5": True,
    "anthropic/claude-opus-4-6": True,
    "anthropic/claude-haiku-4-5": True,
    # OpenAI — would need Responses API adapter (TODO)
    "openai/gpt-4o": False,
    "openai/gpt-4.1": False,
    "openai/o3-mini": False,
    # Claude Code — has its own built-in search
    "claude-code/sonnet": False,
    "claude-code/opus": False,
    "claude-code/haiku": False,
}
