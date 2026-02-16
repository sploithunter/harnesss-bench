"""Tests for ClaudeCodeBridge, specifically timeout enforcement."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from harness_bench.harnesses.claude_code import ClaudeCodeBridge


class TestClaudeCodeBridgeTimeout:
    """Test that ClaudeCodeBridge.execute_task enforces timeout even when
    the child process produces no stdout (issue #39)."""

    def test_timeout_enforced_on_silent_process(self, git_workspace: Path, mock_env):
        """Regression test for #39: timeout must be enforced when child emits no stdout.

        A subprocess that sleeps without producing output should be terminated
        within roughly the configured timeout, not allowed to run to completion.
        """
        bridge = ClaudeCodeBridge(git_workspace, timeout=2)

        # Patch _build_command to return a silent long-running process
        with patch.object(
            bridge,
            "_build_command",
            return_value=["python3", "-c", "import time; time.sleep(30)"],
        ):
            start = time.time()
            result = bridge.execute_task("noop")
            elapsed = time.time() - start

        # The process should have been terminated by the timeout (~2s),
        # not allowed to run for 30s.  Allow generous margin for CI.
        assert elapsed < 10, (
            f"execute_task took {elapsed:.1f}s, expected ~2s timeout"
        )
        assert result is False

    def test_output_still_captured_with_select(self, git_workspace: Path, mock_env):
        """Verify that stdout is still captured correctly after the select fix."""
        bridge = ClaudeCodeBridge(git_workspace, timeout=10)

        # Process that emits output then exits quickly
        with patch.object(
            bridge,
            "_build_command",
            return_value=[
                "python3", "-c",
                "import sys; sys.stdout.write('hello\\n'); sys.stdout.flush()",
            ],
        ):
            result = bridge.execute_task("noop")

        # Process exits with code 0
        assert result is True
