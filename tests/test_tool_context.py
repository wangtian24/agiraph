"""Test ToolContext path resolution and security."""

import pytest
from pathlib import Path

from agiraph.tools.context import ToolContext


def test_resolve_path(tmp_path):
    agent_path = tmp_path / "agents" / "test"
    agent_path.mkdir(parents=True)
    run_dir = agent_path / "runs" / "run1"
    run_dir.mkdir(parents=True)

    ctx = ToolContext(agent_path=agent_path, run_dir=run_dir)
    resolved = ctx.resolve_path("nodes/n1/scratch/test.md")
    assert str(resolved).endswith("nodes/n1/scratch/test.md")


def test_resolve_path_prevents_traversal(tmp_path):
    agent_path = tmp_path / "agents" / "test"
    agent_path.mkdir(parents=True)
    run_dir = agent_path / "runs" / "run1"
    run_dir.mkdir(parents=True)

    ctx = ToolContext(agent_path=agent_path, run_dir=run_dir)
    with pytest.raises(PermissionError):
        ctx.resolve_path("../../../../etc/passwd")
