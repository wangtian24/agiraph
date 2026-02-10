"""OpenAI provider implementation."""
import openai
from typing import Optional
from .base import AIProvider


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""
    
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = openai.AsyncOpenAI(api_key=api_key)
    
    async def generate(self, prompt: str, model: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Generate response using OpenAI API."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )
        
        # Handle response
        if not response.choices or len(response.choices) == 0:
            raise ValueError("OpenAI API returned no choices in response")
        
        choice = response.choices[0]
        if not hasattr(choice, 'message') or not choice.message:
            raise ValueError("OpenAI API response missing message")
        
        content = choice.message.content
        if content is None:
            raise ValueError("OpenAI API returned None content")
        
        return content
    
    def get_available_models(self) -> list[str]:
        """Get available OpenAI models."""
        return [
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "gpt-4o",
            "gpt-4o-mini",
            "o3",
            "o3-mini",
            "o4-mini",
            "o1",
        ]
