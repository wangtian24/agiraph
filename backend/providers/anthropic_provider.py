"""Anthropic (Claude) provider implementation."""
import anthropic
import asyncio
from typing import Optional
from .base import AIProvider


class AnthropicProvider(AIProvider):
    """Anthropic Claude API provider."""
    
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = anthropic.Anthropic(api_key=api_key)
    
    async def generate(self, prompt: str, model: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Generate response using Anthropic API."""
        # Anthropic doesn't have async client yet, run in executor
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
                **kwargs
            )
        )
        
        # Handle response
        if not response.content or len(response.content) == 0:
            raise ValueError("Anthropic API returned empty content")
        
        first_content = response.content[0]
        if not hasattr(first_content, 'text'):
            raise ValueError(f"Anthropic API response missing text. Content type: {type(first_content)}")
        
        text = first_content.text
        if text is None:
            raise ValueError("Anthropic API returned None text")
        
        return text
    
    def get_available_models(self) -> list[str]:
        """Get available Anthropic models."""
        return [
            "claude-opus-4-6",
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
            "claude-sonnet-4-0",
            "claude-opus-4-0",
            "claude-3-7-sonnet-latest",
        ]
