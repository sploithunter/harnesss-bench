"""Harness Bridge - The interface between harnesses and the benchmark protocol.

This module provides the base class that harness adapters must implement.
A bridge is responsible for:
1. Setting up the workspace
2. Invoking the harness
3. Committing changes following the protocol
4. Signaling completion
"""

from __future__ import annotations

import subprocess
import platform
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import (
    Manifest,
    HarnessInfo,
    TaskInfo,
    RunInfo,
    EnvironmentInfo,
    RunStatus,
)
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    CommitAction,
    format_commit_message,
)
from .submission import SubmissionClient, SubmissionConfig, SubmissionResult


class HarnessBridge(ABC):
    """Abstract base class for harness bridges.

    A harness bridge adapts a specific AI coding assistant to work with
    the Harness Bench protocol. Implement this class to add support for
    a new harness.

    Example:
        class AiderBridge(HarnessBridge):
            harness_id = "aider"
            harness_vendor = "aider"

            def execute_task(self, task_prompt: str) -> bool:
                # Run aider with the task
                ...
                return success
    """

    # Subclasses must define these
    harness_id: str = ""
    harness_vendor: str | None = None
    harness_version: str | None = None

    def __init__(self, workspace: Path, model: str | None = None):
        """Initialize the bridge.

        Args:
            workspace: Path to the task workspace (git repository)
            model: Optional model identifier for the harness
        """
        self.workspace = Path(workspace)
        self.model = model
        self.iteration = 0
        self._manifest: Manifest | None = None

    @property
    def manifest(self) -> Manifest:
        """Get the current manifest."""
        if self._manifest is None:
            raise RuntimeError("Manifest not initialized. Call setup() first.")
        return self._manifest

    def setup(self, task_id: str, run_id: str, task_name: str | None = None) -> None:
        """Initialize workspace for task execution.

        This creates the harness branch and initial manifest.

        Args:
            task_id: Task identifier
            run_id: Unique run identifier
            task_name: Optional human-readable task name
        """
        # Create manifest
        self._manifest = Manifest(
            protocol_version=str(CURRENT_PROTOCOL_VERSION),
            harness=HarnessInfo(
                id=self.harness_id,
                version=self.harness_version,
                vendor=self.harness_vendor,
                model=self.model,
            ),
            task=TaskInfo(
                id=task_id,
                name=task_name,
            ),
            run=RunInfo(
                id=run_id,
                status=RunStatus.PENDING,
            ),
            environment=EnvironmentInfo(
                os=platform.system().lower(),
                arch=platform.machine(),
                python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            ),
        )

        # Create harness branch
        branch_name = self.manifest.get_branch_name()
        self._git("checkout", "-b", branch_name)

        # Mark as started and save manifest
        self.manifest.mark_started()
        self.manifest.save(self.workspace)

        # Initial commit
        self._git("add", "-A")
        self._commit(CommitAction.START, "Begin task execution")

    def commit_edit(self, description: str, body: str | None = None) -> None:
        """Commit file changes made by harness.

        Call this after the harness modifies files.

        Args:
            description: Short description of the change
            body: Optional extended description
        """
        self.iteration += 1
        self._git("add", "-A")
        self._commit(CommitAction.EDIT, description, body)

    def commit_fix(self, description: str, previous_error: str | None = None) -> None:
        """Commit a bug fix after test failure.

        Args:
            description: Short description of the fix
            previous_error: The error that was fixed
        """
        self.iteration += 1
        body = f"Previous error: {previous_error}" if previous_error else None
        self._git("add", "-A")
        self._commit(CommitAction.FIX, description, body)

    def commit_test(self, description: str, passed: bool, output: str | None = None) -> None:
        """Record a test execution.

        Args:
            description: Description of the test
            passed: Whether the test passed
            output: Test output (truncated if too long)
        """
        status = "passed" if passed else "failed"
        body = None
        if output:
            # Truncate long output
            max_len = 1000
            if len(output) > max_len:
                output = output[:max_len] + "\n... (truncated)"
            body = f"Status: {status}\nOutput:\n{output}"

        self._git("add", "-A")
        self._commit(CommitAction.TEST, f"{description} ({status})", body)

    def complete(self, success: bool = True, message: str | None = None) -> None:
        """Signal task completion.

        Args:
            success: Whether the task completed successfully
            message: Optional completion message
        """
        self.manifest.mark_completed(success)
        self.manifest.save(self.workspace)

        action = CommitAction.COMPLETE if success else CommitAction.FAIL
        default_msg = "Task completed successfully" if success else "Task failed"

        self._git("add", "-A")
        self._commit(action, message or default_msg)

    def timeout(self, message: str | None = None) -> None:
        """Signal task timeout.

        Args:
            message: Optional timeout message
        """
        self.manifest.mark_timeout()
        self.manifest.save(self.workspace)

        self._git("add", "-A")
        self._commit(CommitAction.TIMEOUT, message or "Task timed out")

    @abstractmethod
    def execute_task(self, task_prompt: str) -> bool:
        """Execute the task using the harness.

        This is the main method that subclasses must implement.
        It should:
        1. Pass the task prompt to the harness
        2. Monitor the harness as it works
        3. Call commit_edit/commit_fix as changes are made
        4. Return True if successful, False otherwise

        The bridge is responsible for calling complete() or timeout()
        after this method returns.

        Args:
            task_prompt: The task description/prompt

        Returns:
            True if the task was completed successfully
        """
        pass

    def run(self, task_id: str, run_id: str, task_name: str | None = None) -> bool:
        """Run the complete benchmark workflow.

        This is a convenience method that:
        1. Sets up the workspace
        2. Reads the task prompt
        3. Executes the task
        4. Signals completion

        Args:
            task_id: Task identifier
            run_id: Unique run identifier
            task_name: Optional human-readable task name

        Returns:
            True if the task completed successfully
        """
        # Setup
        self.setup(task_id, run_id, task_name)

        # Read task prompt
        task_file = self.workspace / "TASK.md"
        if not task_file.exists():
            self.complete(False, "TASK.md not found")
            return False

        task_prompt = task_file.read_text()

        # Execute
        try:
            success = self.execute_task(task_prompt)
            self.complete(success)
            return success
        except TimeoutError:
            self.timeout()
            return False
        except Exception as e:
            self.complete(False, f"Error: {e}")
            return False

    def _commit(
        self,
        action: CommitAction,
        description: str,
        body: str | None = None,
    ) -> None:
        """Create a protocol-compliant commit."""
        message = format_commit_message(
            action=action,
            description=description,
            harness_id=self.harness_id,
            iteration=self.iteration,
            body=body,
        )
        self._git("commit", "-m", message, "--allow-empty")

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        """Run git command in workspace."""
        return subprocess.run(
            ["git", *args],
            cwd=self.workspace,
            check=True,
            capture_output=True,
            text=True,
        )

    def get_file_content(self, path: str) -> str | None:
        """Read a file from the workspace.

        Args:
            path: Relative path within workspace

        Returns:
            File content or None if not found
        """
        full_path = self.workspace / path
        if full_path.exists():
            return full_path.read_text()
        return None

    def write_file(self, path: str, content: str) -> None:
        """Write a file to the workspace.

        Args:
            path: Relative path within workspace
            content: File content
        """
        full_path = self.workspace / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    def log_event(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Log a structured event to the events file.

        Args:
            event: Event name
            data: Optional event data
        """
        import json

        events_file = self.workspace / ".harness-bench" / "events.jsonl"
        events_file.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
        }
        if data:
            entry["data"] = data

        with open(events_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def submit(
        self,
        message: str | None = None,
        config: SubmissionConfig | None = None,
    ) -> SubmissionResult:
        """Submit the completed run to the submissions repository.

        This pushes the workspace to the central submissions repository
        and optionally creates a pull request for evaluation.

        Args:
            message: Optional submission message
            config: Submission configuration

        Returns:
            SubmissionResult with status and URLs
        """
        client = SubmissionClient(config)
        result = client.submit(self.workspace, message)

        self.log_event(
            "submission",
            {
                "success": result.success,
                "submission_id": result.submission_id,
                "pr_url": result.pr_url,
                "error": result.error,
            },
        )

        return result


class ManualBridge(HarnessBridge):
    """A bridge for manual/external harness execution.

    Use this when the harness runs outside of Python (e.g., a GUI IDE).
    The bridge just handles git protocol, user triggers commits manually
    or via CLI commands.
    """

    harness_id = "manual"
    harness_vendor = "harness-bench"

    def execute_task(self, task_prompt: str) -> bool:
        """Manual execution - always returns True.

        For manual bridges, the actual work happens outside this method.
        Call commit_edit(), complete(), etc. from external scripts or CLI.
        """
        # No-op for manual bridge
        return True

    def wait_for_completion(self, timeout_seconds: int = 3600) -> bool:
        """Wait for manual completion signal.

        This could watch for a file, listen on a socket, etc.
        For now, just returns immediately.
        """
        # Subclasses can implement actual waiting logic
        return True
