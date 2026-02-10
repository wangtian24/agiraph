"""OpenRouter provider implementation.
Uses the OpenAI-compatible API at https://openrouter.ai/api/v1.
"""
import openai
from typing import Optional
from .base import AIProvider


class OpenRouterProvider(AIProvider):
    """OpenRouter API provider (OpenAI-compatible)."""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    async def generate(self, prompt: str, model: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Generate response using OpenRouter API."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )

        if not response.choices or len(response.choices) == 0:
            raise ValueError("OpenRouter API returned no choices in response")

        choice = response.choices[0]
        if not hasattr(choice, 'message') or not choice.message:
            raise ValueError("OpenRouter API response missing message")

        content = choice.message.content
        if content is None:
            raise ValueError("OpenRouter API returned None content")

        return content

    def get_available_models(self) -> list[str]:
        """Get popular OpenRouter models."""
        return [
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
        ]
