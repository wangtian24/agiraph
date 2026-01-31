"""Minimax provider implementation using Anthropic SDK.
Based on official Minimax API documentation:
https://platform.minimax.io/docs/guides/text-generation

Uses Anthropic SDK with custom base URL as recommended by Minimax.
"""
import os
import anthropic
import asyncio
from typing import Optional
from .base import AIProvider


class MinimaxProvider(AIProvider):
    """Minimax API provider using Anthropic-compatible API."""
    
    def __init__(self, api_key: str, group_id: Optional[str] = None):
        super().__init__(api_key, group_id=group_id)
        self.api_key = api_key
        self.group_id = group_id
        # Use Anthropic SDK with Minimax base URL as per official documentation
        # https://platform.minimax.io/docs/guides/text-generation
        self.client = anthropic.Anthropic(
            api_key=api_key,
            base_url="https://api.minimax.io/anthropic"
        )
    
    async def generate(self, prompt: str, model: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Generate response using Minimax API via Anthropic SDK.
        
        Follows the exact pattern from:
        https://platform.minimax.io/docs/guides/text-generation
        """
        # Build messages in Anthropic format as shown in documentation
        messages = [{
            "role": "user",
            "content": [{
                "type": "text",
                "text": prompt
            }]
        }]
        
        # Prepare parameters
        params = {
            "model": model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            **{k: v for k, v in kwargs.items() if k != "max_tokens"}
        }
        
        if system_prompt:
            params["system"] = system_prompt
        
        # Get debug info for error messages
        debug_mode = os.getenv("MINIMAX_DEBUG", "false").lower() == "true"
        if debug_mode:
            api_key_info = f"Full API key: {self.api_key}"
            group_id_info = f"Group ID: {self.group_id if self.group_id else 'None'}"
        else:
            api_key_preview = f"{self.api_key[:8]}...{self.api_key[-4:]}" if len(self.api_key) > 12 else "***"
            api_key_info = f"API key: {api_key_preview} (set MINIMAX_DEBUG=true to see full key)"
            group_id_preview = f"{self.group_id[:4]}...{self.group_id[-4:]}" if self.group_id and len(self.group_id) > 8 else (self.group_id or "None")
            group_id_info = f"Group ID: {group_id_preview} (set MINIMAX_DEBUG=true to see full)"
        
        # Call API using Anthropic SDK (run in executor since it's synchronous)
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(**params)
            )
        except Exception as e:
            # Handle API errors
            error_msg = str(e)
            raise ValueError(
                f"Minimax API error: {error_msg}. "
                f"{api_key_info}, {group_id_info}"
            )
        
        # Parse response as shown in documentation
        # Extract text from content blocks
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "thinking":
                # Thinking blocks are available but we return text only
                pass
        
        if not text_parts:
            raise ValueError(
                f"Minimax API returned no text content. "
                f"Response content blocks: {len(response.content)}. "
                f"{api_key_info}, {group_id_info}"
            )
        
        return "\n".join(text_parts)
    
    def get_available_models(self) -> list[str]:
        """Get available Minimax models.
        
        According to documentation:
        https://platform.minimax.io/docs/guides/text-generation
        """
        return [
            "MiniMax-M2.1",
            "MiniMax-M2.1-lightning",
            "MiniMax-M2"
        ]
