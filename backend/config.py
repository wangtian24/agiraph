"""Configuration management for API keys and settings."""
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Optional

# Load .env file from project root (if it exists and is readable)
env_path = Path(__file__).parent.parent / '.env'
try:
    if env_path.exists() and env_path.is_file():
        load_dotenv(dotenv_path=env_path)
    else:
        # Try loading from current directory or environment
        load_dotenv()
except (PermissionError, OSError):
    # If we can't read .env, just use environment variables
    pass


class Config:
    """Application configuration."""
    
    # API Keys
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")
    MINIMAX_API_KEY: Optional[str] = os.getenv("MINIMAX_API_KEY")
    MINIMAX_GROUP_ID: Optional[str] = os.getenv("MINIMAX_GROUP_ID")
    OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")

    # Default models per provider
    DEFAULT_MODELS = {
        "openai": "gpt-4.1",
        "anthropic": "claude-sonnet-4-5",
        "gemini": "gemini-3-flash-preview",
        "minimax": "MiniMax-M2.1",
        "openrouter": "openai/gpt-4.1",
    }

    # Available models per provider
    PROVIDER_MODELS: Dict[str, List[str]] = {
        "openai": [
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "gpt-4o",
            "gpt-4o-mini",
            "o3",
            "o3-mini",
            "o4-mini",
            "o1",
        ],
        "anthropic": [
            "claude-opus-4-6",
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
            "claude-sonnet-4-0",
            "claude-opus-4-0",
            "claude-3-7-sonnet-latest",
        ],
        "gemini": [
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-pro",
        ],
        "minimax": [
            "MiniMax-M2.1",
            "MiniMax-M2.1-lightning",
            "MiniMax-M2",
        ],
        "openrouter": [
            "openai/gpt-4.1",
            "openai/gpt-4.1-mini",
            "openai/gpt-4.1-nano",
            "openai/o3",
            "openai/o3-mini",
            "openai/o4-mini",
            "anthropic/claude-opus-4-6",
            "anthropic/claude-sonnet-4-5",
            "anthropic/claude-haiku-4-5",
            "google/gemini-2.5-pro-preview",
            "google/gemini-2.5-flash-preview",
            "deepseek/deepseek-r1",
            "deepseek/deepseek-chat-v3",
            "meta-llama/llama-4-maverick",
            "meta-llama/llama-4-scout",
        ],
    }
    
    @classmethod
    def get_api_key(cls, provider: str) -> Optional[str]:
        """Get API key for a provider."""
        key_map = {
            "openai": cls.OPENAI_API_KEY,
            "anthropic": cls.ANTHROPIC_API_KEY,
            "gemini": cls.GOOGLE_API_KEY,
            "minimax": cls.MINIMAX_API_KEY,
            "openrouter": cls.OPENROUTER_API_KEY,
        }
        return key_map.get(provider.lower())
    
    @classmethod
    def get_available_providers(cls) -> Dict[str, bool]:
        """Check which providers have API keys configured."""
        return {
            "openai": cls.OPENAI_API_KEY is not None and cls.OPENAI_API_KEY.strip() != "",
            "anthropic": cls.ANTHROPIC_API_KEY is not None and cls.ANTHROPIC_API_KEY.strip() != "",
            "gemini": cls.GOOGLE_API_KEY is not None and cls.GOOGLE_API_KEY.strip() != "",
            "minimax": cls.MINIMAX_API_KEY is not None and cls.MINIMAX_API_KEY.strip() != "",
            "openrouter": cls.OPENROUTER_API_KEY is not None and cls.OPENROUTER_API_KEY.strip() != "",
        }
    
    @classmethod
    def get_available_provider_names(cls) -> List[str]:
        """Get list of available provider names."""
        available = cls.get_available_providers()
        return [name for name, is_available in available.items() if is_available]