"""Minimax provider implementation."""
import httpx
from typing import Optional
from .base import AIProvider


class MinimaxProvider(AIProvider):
    """Minimax API provider."""
    
    def __init__(self, api_key: str, group_id: str):
        super().__init__(api_key, group_id=group_id)
        self.group_id = group_id
        self.base_url = "https://api.minimax.chat/v1/text/chatcompletion_pro"
    
    async def generate(self, prompt: str, model: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Generate response using Minimax API."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "group_id": self.group_id,
                    **kwargs
                },
                timeout=60.0
            )
            response.raise_for_status()
            
            # Check if response is valid JSON
            try:
                data = response.json()
            except Exception as e:
                raise ValueError(f"Minimax API returned invalid JSON: {e}. Response text: {response.text[:500]}")
            
            # Debug: log response structure if it's unexpected
            # Handle different response structures
            # Check for common response formats
            if "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    return choice["message"]["content"]
                elif "text" in choice:
                    return choice["text"]
                elif "content" in choice:
                    return choice["content"]
            
            # Alternative structure: direct reply or reply field
            if "reply" in data:
                return data["reply"]
            
            if "content" in data:
                return data["content"]
            
            if "text" in data:
                return data["text"]
            
            # Check for error in response
            if "error" in data:
                error_msg = data.get("error", {}).get("message", str(data.get("error", "Unknown error")))
                raise ValueError(f"Minimax API error: {error_msg}")
            
            # If we can't find the response, raise an error with the actual structure
            import json
            raise ValueError(
                f"Unexpected Minimax API response structure. "
                f"Response keys: {list(data.keys())}. "
                f"Full response (first 500 chars): {json.dumps(data, indent=2)[:500]}"
            )
    
    def get_available_models(self) -> list[str]:
        """Get available Minimax models."""
        return [
            "abab6.5s",
            "abab6.5",
            "abab5.5s",
            "abab5.5"
        ]
