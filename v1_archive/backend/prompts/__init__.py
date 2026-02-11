"""Prompt templates for the AI orchestration framework."""
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


def load_prompt(filename: str) -> str:
    """Load a prompt template from file."""
    file_path = PROMPTS_DIR / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {filename}")
    return file_path.read_text(encoding="utf-8").strip()


def format_prompt(template: str, **kwargs) -> str:
    """Format a prompt template with keyword arguments."""
    return template.format(**kwargs)

