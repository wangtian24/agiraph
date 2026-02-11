"""Base class for AI providers."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class AIProvider(ABC):
    """Abstract base class for AI providers."""
    
    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key
        self.kwargs = kwargs
    
    @abstractmethod
    async def generate(self, prompt: str, model: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Generate a response from the AI model."""
        pass
    
    @abstractmethod
    def get_available_models(self) -> list[str]:
        """Get list of available models for this provider."""
        pass
