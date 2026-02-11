#!/usr/bin/env python3
"""Main entry point for the AI orchestration framework."""
import asyncio
from backend.cli import main

if __name__ == "__main__":
    asyncio.run(main())
