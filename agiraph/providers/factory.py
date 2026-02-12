"""Provider factory — create the right adapter based on model string."""

from __future__ import annotations

from agiraph.providers.base import ModelProvider, ProviderAdapter


def parse_model_string(model: str) -> tuple[str, str]:
    """Parse 'provider/model-name' into (provider, model)."""
    if "/" in model:
        provider, model_name = model.split("/", 1)
        return provider.lower(), model_name
    # Infer provider from model name
    if model.startswith("claude") or model.startswith("claude-"):
        return "anthropic", model
    if model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        return "openai", model
    # Default to anthropic
    return "anthropic", model


def create_adapter(model: str) -> ProviderAdapter:
    """Create a provider adapter for the given model string."""
    provider, model_name = parse_model_string(model)

    if provider == "claude-code":
        # Claude Code CLI is not a standard provider — it handles its own tools.
        # Return a text-fallback adapter as a placeholder; the coordinator/worker
        # will detect the claude-code prefix and use ClaudeCodeRunner directly.
        from agiraph.providers.text_fallback import TextFallbackAdapter
        return TextFallbackAdapter(model=model_name)
    elif provider == "anthropic":
        from agiraph.providers.anthropic_provider import AnthropicAdapter
        return AnthropicAdapter(model=model_name)
    elif provider == "openai":
        from agiraph.providers.openai_provider import OpenAIAdapter
        return OpenAIAdapter(model=model_name)
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'anthropic/model', 'openai/model', or 'claude-code/model'.")


def create_provider(model: str) -> ModelProvider:
    """Create a ModelProvider wrapping the appropriate adapter."""
    adapter = create_adapter(model)
    return ModelProvider(adapter)
