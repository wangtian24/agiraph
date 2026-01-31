"""Google Gemini provider implementation."""
import google.genai as genai
import asyncio
from typing import Optional
from .base import AIProvider


class GeminiProvider(AIProvider):
    """Google Gemini API provider."""
    
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.api_key = api_key
        # Initialize client - google.genai uses Client with api_key
        self.client = genai.Client(api_key=api_key)
    
    async def generate(self, prompt: str, model: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Generate response using Gemini API."""
        # Combine system prompt with user prompt
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        
        # google.genai API - run in executor since it's synchronous
        loop = asyncio.get_event_loop()
        
        def _generate():
            try:
                # Use the new google.genai Client API
                # Try different API patterns as the exact API may vary
                try:
                    # Pattern 1: client.models.generate_content
                    response = self.client.models.generate_content(
                        model=model,
                        contents=full_prompt,
                        **kwargs
                    )
                except (AttributeError, TypeError):
                    # Pattern 2: Direct model access
                    model_obj = self.client.get_model(model)
                    response = model_obj.generate_content(full_prompt, **kwargs)
                
                # Extract text from response
                return self._extract_text(response)
            except Exception as e:
                # Provide more context in error
                raise ValueError(f"Gemini API call failed: {e}. Check API key and model name.")
        
        response_text = await loop.run_in_executor(None, _generate)
        return response_text
    
    def _extract_text(self, response) -> str:
        """Extract text from response object."""
        # Handle different response formats
        if hasattr(response, 'text') and response.text:
            return response.text
        
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content'):
                content = candidate.content
                if hasattr(content, 'parts') and content.parts:
                    part = content.parts[0]
                    if hasattr(part, 'text'):
                        return part.text
                elif hasattr(content, 'text'):
                    return content.text
        
        # Check for direct content attribute
        if hasattr(response, 'content'):
            content = response.content
            if isinstance(content, str):
                return content
            elif hasattr(content, 'text'):
                return content.text
        
        # If we can't extract text, raise an error with response info
        import json
        response_str = str(response)
        if hasattr(response, '__dict__'):
            response_str = json.dumps(response.__dict__, default=str, indent=2)
        
        raise ValueError(
            f"Could not extract text from Gemini response. "
            f"Response type: {type(response)}, "
            f"Response attributes: {dir(response)}, "
            f"Response: {response_str[:500]}"
        )
    
    def get_available_models(self) -> list[str]:
        """Get available Gemini models."""
        return [
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-pro"
        ]
