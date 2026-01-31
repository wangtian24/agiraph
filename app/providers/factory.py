"""Factory for creating AI provider instances."""
from typing import Optional
from .base import AIProvider
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .gemini_provider import GeminiProvider
from .minimax_provider import MinimaxProvider
from ..config import Config


def create_provider(provider_name: str, **kwargs) -> Optional[AIProvider]:
    """Create an AI provider instance."""
    provider_name = provider_name.lower()
    
    if provider_name == "openai":
        api_key = kwargs.get("api_key") or Config.OPENAI_API_KEY
        if not api_key:
            raise ValueError("OpenAI API key not configured")
        return OpenAIProvider(api_key)
    
    elif provider_name == "anthropic":
        api_key = kwargs.get("api_key") or Config.ANTHROPIC_API_KEY
        if not api_key:
            raise ValueError("Anthropic API key not configured")
        return AnthropicProvider(api_key)
    
    elif provider_name == "gemini":
        api_key = kwargs.get("api_key") or Config.GOOGLE_API_KEY
        if not api_key:
            raise ValueError("Google API key not configured")
        return GeminiProvider(api_key)
    
    elif provider_name == "minimax":
        api_key = kwargs.get("api_key") or Config.MINIMAX_API_KEY
        group_id = kwargs.get("group_id") or Config.MINIMAX_GROUP_ID
        if not api_key:
            raise ValueError("Minimax API key not configured")
        # group_id is not needed for Anthropic-compatible API (used for M2.1 models)
        # but kept for backward compatibility
        return MinimaxProvider(api_key, group_id if group_id else None)
    
    else:
        raise ValueError(f"Unknown provider: {provider_name}")
