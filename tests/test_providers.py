"""Test provider factory and adapters."""

from agiraph.providers.factory import parse_model_string, create_adapter
from agiraph.providers.anthropic_provider import AnthropicAdapter
from agiraph.providers.openai_provider import OpenAIAdapter
from agiraph.models import ToolDef


def test_parse_model_string():
    assert parse_model_string("anthropic/claude-sonnet-4-5") == ("anthropic", "claude-sonnet-4-5")
    assert parse_model_string("openai/gpt-4o") == ("openai", "gpt-4o")
    assert parse_model_string("claude-sonnet-4-5") == ("anthropic", "claude-sonnet-4-5")
    assert parse_model_string("gpt-4o") == ("openai", "gpt-4o")


def test_create_adapter():
    adapter = create_adapter("anthropic/claude-sonnet-4-5")
    assert isinstance(adapter, AnthropicAdapter)

    adapter = create_adapter("openai/gpt-4o")
    assert isinstance(adapter, OpenAIAdapter)


def test_anthropic_format_tools():
    adapter = AnthropicAdapter()
    tools = [
        ToolDef(
            name="test_tool",
            description="A test",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        )
    ]
    formatted = adapter.format_tools(tools)
    assert len(formatted) == 1
    assert formatted[0]["name"] == "test_tool"
    assert formatted[0]["input_schema"]["properties"]["x"]["type"] == "string"


def test_openai_format_tools():
    adapter = OpenAIAdapter()
    tools = [
        ToolDef(
            name="test_tool",
            description="A test",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        )
    ]
    formatted = adapter.format_tools(tools)
    assert len(formatted) == 1
    assert formatted[0]["type"] == "function"
    assert formatted[0]["function"]["name"] == "test_tool"


def test_tool_prompt_generation():
    adapter = AnthropicAdapter()
    tools = [
        ToolDef(name="bash", description="Run a command", parameters={}, guidance="Use carefully."),
    ]
    prompt = adapter.format_tool_prompt(tools)
    assert "bash" in prompt
    assert "Use carefully" in prompt
