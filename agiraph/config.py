"""Configuration loading and defaults."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

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

# Search provider
SEARCH_PROVIDER = os.getenv("AGIRAPH_SEARCH_PROVIDER", "brave")  # brave | serper
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
