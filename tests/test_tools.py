"""Test tool registry and definitions."""

from agiraph.tools.definitions import ALL_TOOLS, WORKER_TOOLS, COORDINATOR_TOOLS
from agiraph.tools.registry import ToolRegistry
from agiraph.tools.setup import create_default_registry
from agiraph.models import ToolCall


def test_all_tools_defined():
    assert len(ALL_TOOLS) == 25
    names = [t.name for t in ALL_TOOLS]
    assert "publish" in names
    assert "finish" in names
    assert "bash" in names
    assert "web_search" in names


def test_worker_vs_coordinator_tools():
    assert len(WORKER_TOOLS) < len(COORDINATOR_TOOLS)
    worker_names = {t.name for t in WORKER_TOOLS}
    assert "finish" not in worker_names
    assert "spawn_worker" not in worker_names
    assert "assign_worker" not in worker_names
    assert "publish" in worker_names
    assert "bash" in worker_names


def test_registry_creation():
    registry = create_default_registry()
    assert len(registry.names()) == 25

    worker_tools = registry.get_worker_tools()
    coordinator_tools = registry.get_coordinator_tools()
    assert len(coordinator_tools) > len(worker_tools)


def test_registry_get_def():
    registry = create_default_registry()
    bash_def = registry.get_def("bash")
    assert bash_def is not None
    assert bash_def.name == "bash"
    assert "command" in str(bash_def.parameters)

    assert registry.get_def("nonexistent") is None


def test_tool_parameters_valid():
    """All tools should have valid JSON Schema parameters."""
    for tool in ALL_TOOLS:
        assert tool.parameters.get("type") == "object"
        assert "properties" in tool.parameters
