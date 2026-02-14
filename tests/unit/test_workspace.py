"""Tests for workspace path traversal fix (issue #2)."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness_bench.tasks.workspace import WorkspaceManager, _validate_path_component


class TestValidatePathComponent:
    """Test _validate_path_component helper."""

    def test_valid_tokens(self):
        """Valid tokens should not raise."""
        for token in ["run_abc123", "claude-code", "L1-PY-01", "v1.0", "simple"]:
            _validate_path_component(token, "test")

    def test_empty_string_rejected(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            _validate_path_component("", "test")

    def test_path_traversal_rejected(self):
        """Directory traversal sequences should raise ValueError."""
        with pytest.raises(ValueError, match="invalid characters"):
            _validate_path_component("../outside", "test")

    def test_slash_rejected(self):
        """Forward slashes should raise ValueError."""
        with pytest.raises(ValueError, match="invalid characters"):
            _validate_path_component("foo/bar", "test")

    def test_backslash_rejected(self):
        """Backslashes should raise ValueError."""
        with pytest.raises(ValueError, match="invalid characters"):
            _validate_path_component("foo\\bar", "test")

    def test_space_rejected(self):
        """Spaces should raise ValueError."""
        with pytest.raises(ValueError, match="invalid characters"):
            _validate_path_component("foo bar", "test")


class TestWorkspacePathTraversal:
    """Regression tests for issue #2: path traversal via run_id/harness_id."""

    def _make_mock_task(self, task_id: str = "L1-PY-01") -> MagicMock:
        """Create a mock Task with the given task ID."""
        task = MagicMock()
        task.config.id = task_id
        task.config.name = "Test Task"
        task.config.domain = "python"
        task.config.level = 1
        task.prompt = "Test prompt"
        task.starter_files_content = {}
        task.path = Path("/tmp/fake_task")
        return task

    def test_traversal_via_run_id(self, temp_dir: Path):
        """Malicious run_id with '../' must be rejected (PoC from issue #2)."""
        manager = WorkspaceManager(base_dir=temp_dir / "workspaces")
        task = self._make_mock_task()

        with pytest.raises(ValueError, match="invalid characters"):
            manager.create_workspace(task, "aider", run_id="../outside_pwn")

        # Verify no directory was created outside workspaces
        assert not (temp_dir / "outside_pwn").exists()

    def test_traversal_via_harness_id(self, temp_dir: Path):
        """Malicious harness_id with '../' must be rejected."""
        manager = WorkspaceManager(base_dir=temp_dir / "workspaces")
        task = self._make_mock_task()

        with pytest.raises(ValueError, match="invalid characters"):
            manager.create_workspace(task, "../evil", run_id="run_safe")

    def test_traversal_via_task_id(self, temp_dir: Path):
        """Malicious task_id with '../' must be rejected."""
        manager = WorkspaceManager(base_dir=temp_dir / "workspaces")
        task = self._make_mock_task(task_id="../escape")

        with pytest.raises(ValueError, match="invalid characters"):
            manager.create_workspace(task, "aider", run_id="run_safe")

    def test_safe_inputs_accepted(self, temp_dir: Path):
        """Normal inputs should not trigger validation errors."""
        manager = WorkspaceManager(base_dir=temp_dir / "workspaces")
        task = self._make_mock_task()

        # Should not raise - just verify validation passes
        # (will fail later on git init / file copy, but that's fine for this test)
        _validate_path_component(task.config.id, "task_id")
        _validate_path_component("claude-code", "harness_id")
        _validate_path_component("run_abc12345", "run_id")
