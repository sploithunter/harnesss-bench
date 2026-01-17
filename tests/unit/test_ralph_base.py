"""Tests for RalphLoopBase shared functionality."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harness_bench.harnesses.ralph_base import RalphLoopBase


class ConcreteRalphLoop(RalphLoopBase):
    """Concrete implementation for testing abstract base class."""

    harness_id = "test-harness"
    harness_vendor = "test-vendor"
    harness_version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commands_run = []
        self.success_on_iteration = kwargs.get("success_on_iteration", 1)
        self._current_iteration = 0

    def _run_harness_command(self, prompt: str, timeout: float) -> tuple[bool, str]:
        """Mock harness command that succeeds on configured iteration."""
        self._current_iteration += 1
        self.commands_run.append({"prompt": prompt, "timeout": timeout})

        if self._current_iteration >= self.success_on_iteration:
            return True, "completed"
        return True, "completed"

    def _get_env(self) -> dict[str, str]:
        """Return mock environment."""
        return {"TEST_API_KEY": "test-key"}


class TestRalphLoopBaseInit:
    """Test RalphLoopBase initialization."""

    def test_default_values(self, git_workspace: Path):
        """Test default initialization values."""
        bridge = ConcreteRalphLoop(workspace=git_workspace)

        assert bridge.max_iterations == 10
        assert bridge.total_timeout == 300
        assert bridge.stagnation_limit == 3
        assert bridge.verify_timeout == 300
        assert bridge.verbose is True
        assert bridge.iteration == 0
        assert bridge.stagnation_count == 0
        assert bridge.total_cost_usd == 0.0

    def test_custom_values(self, git_workspace: Path, temp_dir: Path):
        """Test initialization with custom values."""
        verify_script = temp_dir / "verify.py"
        verify_script.write_text("# mock")

        bridge = ConcreteRalphLoop(
            workspace=git_workspace,
            verify_script=verify_script,
            model="test-model",
            max_iterations=5,
            total_timeout=600,
            stagnation_limit=2,
            verbose=False,
            verify_timeout=120,
        )

        assert bridge.max_iterations == 5
        assert bridge.total_timeout == 600
        assert bridge.stagnation_limit == 2
        assert bridge.verbose is False
        assert bridge.verify_timeout == 120
        assert bridge.model == "test-model"


class TestTimeManagement:
    """Test time-related functionality."""

    def test_time_remaining_initial(self, git_workspace: Path):
        """Test _time_remaining before start."""
        bridge = ConcreteRalphLoop(
            workspace=git_workspace,
            total_timeout=300,
        )

        assert bridge._time_remaining() == 300

    def test_time_remaining_after_start(self, git_workspace: Path):
        """Test _time_remaining decreases after start."""
        bridge = ConcreteRalphLoop(
            workspace=git_workspace,
            total_timeout=300,
        )

        bridge._start_time = time.time() - 100  # Started 100 seconds ago

        remaining = bridge._time_remaining()
        assert 199 <= remaining <= 201  # Allow 1 second tolerance

    def test_time_remaining_expired(self, git_workspace: Path):
        """Test _time_remaining returns 0 when expired."""
        bridge = ConcreteRalphLoop(
            workspace=git_workspace,
            total_timeout=300,
        )

        bridge._start_time = time.time() - 500  # Started 500 seconds ago

        assert bridge._time_remaining() == 0

    def test_is_timed_out(self, git_workspace: Path):
        """Test _is_timed_out detection."""
        bridge = ConcreteRalphLoop(
            workspace=git_workspace,
            total_timeout=10,
        )

        bridge._start_time = time.time() - 5
        assert bridge._is_timed_out() is False

        bridge._start_time = time.time() - 15
        assert bridge._is_timed_out() is True


class TestStateFiles:
    """Test state file management."""

    def test_init_state_files(self, git_workspace: Path):
        """Test _init_state_files creates required files."""
        bridge = ConcreteRalphLoop(workspace=git_workspace)
        bridge._init_state_files()

        progress_file = git_workspace / "progress.txt"
        status_file = git_workspace / ".ralph_status.json"

        assert progress_file.exists()
        assert status_file.exists()

        # Check progress file content
        progress_content = progress_file.read_text()
        assert "# test-harness Ralph Loop Progress" in progress_content

        # Check status file content
        status = json.loads(status_file.read_text())
        assert status["iteration"] == 0
        assert status["status"] == "running"

    def test_append_progress(self, git_workspace: Path):
        """Test _append_progress adds content to progress file."""
        bridge = ConcreteRalphLoop(workspace=git_workspace)
        bridge._init_state_files()

        bridge._append_progress("Test message 1")
        bridge._append_progress("Test message 2")

        progress_content = (git_workspace / "progress.txt").read_text()
        assert "Test message 1" in progress_content
        assert "Test message 2" in progress_content

    def test_update_status(self, git_workspace: Path, sample_verification_result: dict):
        """Test _update_status updates status file."""
        bridge = ConcreteRalphLoop(workspace=git_workspace)
        bridge._init_state_files()
        bridge.iteration = 3
        bridge.stagnation_count = 1

        bridge._update_status(sample_verification_result)

        status = json.loads((git_workspace / ".ralph_status.json").read_text())
        assert status["iteration"] == 3
        assert status["status"] == "passed"
        assert status["stagnation_count"] == 1


class TestPromptBuilding:
    """Test prompt building functionality."""

    def test_build_base_prompt_includes_task_md(self, task_workspace: Path):
        """Test _build_base_prompt includes TASK.md content."""
        bridge = ConcreteRalphLoop(workspace=task_workspace)

        prompt = bridge._build_base_prompt("Complete the task")

        assert "# TASK.md" in prompt
        assert "implement" in prompt.lower()  # Content from TASK.md
        assert "Complete the task" in prompt

    def test_build_base_prompt_includes_progress(self, task_workspace: Path):
        """Test _build_base_prompt includes progress log."""
        bridge = ConcreteRalphLoop(workspace=task_workspace)
        bridge._progress_log = [
            "Iteration 1 - Failed: some error",
            "Iteration 2 - Failed: another error",
        ]

        prompt = bridge._build_base_prompt("Complete the task")

        assert "Previous Iteration Progress" in prompt
        assert "some error" in prompt
        assert "another error" in prompt

    def test_build_base_prompt_truncates_long_progress(self, task_workspace: Path):
        """Test _build_base_prompt truncates very long progress logs."""
        bridge = ConcreteRalphLoop(workspace=task_workspace)
        bridge._progress_log = [f"Entry {i}" for i in range(50)]

        prompt = bridge._build_base_prompt("Complete the task")

        assert "truncated" in prompt
        # Should only include last 30 entries
        assert "Entry 49" in prompt
        assert "Entry 19" not in prompt


class TestStagnationDetection:
    """Test circuit breaker/stagnation detection."""

    def test_check_stagnation_no_change(self, git_workspace: Path):
        """Test stagnation increments when no changes."""
        bridge = ConcreteRalphLoop(
            workspace=git_workspace,
            stagnation_limit=3,
        )
        bridge._init_state_files()

        assert bridge._check_stagnation(files_changed=False) is False
        assert bridge.stagnation_count == 1

        assert bridge._check_stagnation(files_changed=False) is False
        assert bridge.stagnation_count == 2

        # Third time triggers circuit breaker
        assert bridge._check_stagnation(files_changed=False) is True
        assert bridge.stagnation_count == 3

    def test_check_stagnation_resets_on_change(self, git_workspace: Path):
        """Test stagnation resets when files change."""
        bridge = ConcreteRalphLoop(
            workspace=git_workspace,
            stagnation_limit=3,
        )
        bridge._init_state_files()

        bridge._check_stagnation(files_changed=False)
        bridge._check_stagnation(files_changed=False)
        assert bridge.stagnation_count == 2

        # Change detected, should reset
        bridge._check_stagnation(files_changed=True)
        assert bridge.stagnation_count == 0


class TestVerificationFailureProcessing:
    """Test verification failure processing."""

    def test_process_verification_failure_logs_error(self, git_workspace: Path):
        """Test _process_verification_failure logs error message."""
        bridge = ConcreteRalphLoop(workspace=git_workspace, verbose=False)
        bridge._init_state_files()
        bridge.iteration = 1

        verify_result = {
            "success": False,
            "message": "Some tests failed",
            "checkpoints": [
                {"name": "check1", "passed": True, "message": "OK"},
                {"name": "check2", "passed": False, "message": "Failed assertion"},
            ],
        }

        bridge._process_verification_failure(verify_result)

        assert len(bridge._progress_log) >= 1
        assert "Some tests failed" in bridge._progress_log[0]
        assert any("FAIL" in entry for entry in bridge._progress_log)

    def test_process_verification_failure_dds_hint(self, git_workspace: Path):
        """Test _process_verification_failure adds DDS hints."""
        bridge = ConcreteRalphLoop(workspace=git_workspace, verbose=False)
        bridge._init_state_files()
        bridge.iteration = 1

        verify_result = {
            "success": False,
            "message": "Import error",
            "checkpoints": [
                {
                    "name": "import",
                    "passed": False,
                    "message": "ModuleNotFoundError: cyclonedx not found",
                },
            ],
        }

        bridge._process_verification_failure(verify_result)

        # Should include DDS hint
        progress_joined = "\n".join(bridge._progress_log)
        assert "HINT" in progress_joined or "rti.connextdds" in progress_joined


class TestCommitIfChanged:
    """Test git commit functionality."""

    def test_commit_if_changed_no_changes(self, git_workspace: Path):
        """Test _commit_if_changed returns False when no changes."""
        bridge = ConcreteRalphLoop(workspace=git_workspace)
        bridge.iteration = 1

        result = bridge._commit_if_changed()
        assert result is False

    def test_commit_if_changed_with_changes(self, git_workspace: Path):
        """Test _commit_if_changed returns True and commits when changes exist."""
        bridge = ConcreteRalphLoop(workspace=git_workspace)
        bridge.iteration = 1

        # Create a new file
        (git_workspace / "new_file.txt").write_text("test content")

        result = bridge._commit_if_changed()
        assert result is True

        # Verify commit was made
        import subprocess
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=git_workspace,
            capture_output=True,
            text=True,
        )
        assert "[test-harness-ralph] Iteration 1" in log.stdout
