"""Aider bridge implementation.

Aider is an AI pair programming tool that works in the terminal.
This bridge integrates it with the Harness Bench protocol.

Usage:
    bridge = AiderBridge(workspace, model="anthropic/claude-sonnet-4-20250514")
    success = bridge.run(task_id="L1-PY-01", run_id="run_abc123")
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    import pexpect
    PEXPECT_AVAILABLE = True
except ImportError:
    PEXPECT_AVAILABLE = False

from ..core.bridge import HarnessBridge
from ..core.protocol import CommitAction


class AiderBridge(HarnessBridge):
    """Bridge for Aider AI pair programming tool.

    Aider can be automated using pexpect for interactive control,
    or run in simple one-shot mode with --message.
    """

    harness_id = "aider"
    harness_vendor = "aider"
    harness_version = "0.50.0"

    def __init__(
        self,
        workspace: Path,
        model: str | None = "anthropic/claude-sonnet-4-20250514",
        auto_test: bool = True,
        test_cmd: str | None = None,
        max_iterations: int = 20,
        timeout: int = 300,
        interactive: bool = False,
    ):
        """Initialize Aider bridge.

        Args:
            workspace: Path to task workspace
            model: Model in aider format (e.g., anthropic/claude-sonnet-4-20250514)
            auto_test: Whether to run tests automatically after edits
            test_cmd: Test command to run (e.g., "python test.py")
            max_iterations: Maximum edit iterations
            timeout: Total timeout in seconds
            interactive: Use interactive mode with pexpect
        """
        super().__init__(workspace, model)
        self.auto_test = auto_test
        self.test_cmd = test_cmd
        self.max_iterations = max_iterations
        self.timeout = timeout
        self.interactive = interactive

    def execute_task(self, task_prompt: str) -> bool:
        """Execute task using Aider.

        Args:
            task_prompt: The task prompt from TASK.md

        Returns:
            True if task completed successfully
        """
        if self.interactive and PEXPECT_AVAILABLE:
            return self._execute_interactive(task_prompt)
        else:
            return self._execute_oneshot(task_prompt)

    def _execute_oneshot(self, task_prompt: str) -> bool:
        """Execute in one-shot mode using --message flag.

        Args:
            task_prompt: Task prompt

        Returns:
            True if successful
        """
        cmd = self._build_command(task_prompt)

        self.log_event("aider_start", {
            "model": self.model,
            "mode": "oneshot",
        })

        try:
            start_time = time.time()

            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=self._get_env(),
            )

            elapsed = time.time() - start_time

            # Aider makes its own commits, so we just need to track them
            self._sync_aider_commits()

            self.log_event("aider_complete", {
                "exit_code": result.returncode,
                "elapsed": elapsed,
                "stdout_lines": len(result.stdout.split("\n")),
            })

            # Consider success if exit code is 0 or if files were created
            return result.returncode == 0 or self._has_target_files()

        except subprocess.TimeoutExpired:
            self.log_event("aider_timeout", {"timeout": self.timeout})
            return False
        except Exception as e:
            self.log_event("aider_error", {"error": str(e)})
            return False

    def _execute_interactive(self, task_prompt: str) -> bool:
        """Execute in interactive mode using pexpect.

        This allows for more control over the conversation flow.

        Args:
            task_prompt: Task prompt

        Returns:
            True if successful
        """
        if not PEXPECT_AVAILABLE:
            raise RuntimeError("pexpect not available for interactive mode")

        cmd = " ".join(self._build_interactive_command())

        self.log_event("aider_start", {
            "model": self.model,
            "mode": "interactive",
        })

        try:
            # Spawn aider process
            child = pexpect.spawn(
                cmd,
                cwd=str(self.workspace),
                timeout=self.timeout,
                env=self._get_env(),
                encoding="utf-8",
            )

            # Wait for prompt
            child.expect(r"[>]", timeout=30)

            # Send task prompt
            child.sendline(task_prompt)

            # Monitor iterations
            iteration = 0
            while iteration < self.max_iterations:
                try:
                    # Wait for completion or error
                    index = child.expect([
                        r"[>]",  # Ready for next input
                        r"Tokens:",  # Token count (indicates completion)
                        pexpect.EOF,
                        pexpect.TIMEOUT,
                    ], timeout=60)

                    if index == 0:
                        # Aider is waiting for input - task may be done
                        self._sync_aider_commits()
                        if self._has_target_files():
                            break
                        # Send follow-up if needed
                        child.sendline("/quit")
                        break

                    elif index == 1:
                        # Token count shown, iteration complete
                        iteration += 1
                        self._sync_aider_commits()

                    elif index in [2, 3]:
                        # EOF or timeout
                        break

                except pexpect.exceptions.TIMEOUT:
                    self.log_event("aider_iteration_timeout", {"iteration": iteration})
                    break

            child.close()

            self.log_event("aider_complete", {
                "iterations": iteration,
                "exit_status": child.exitstatus,
            })

            return self._has_target_files()

        except Exception as e:
            self.log_event("aider_error", {"error": str(e)})
            return False

    def _build_command(self, task_prompt: str) -> list[str]:
        """Build one-shot Aider command.

        Args:
            task_prompt: Task prompt

        Returns:
            Command list
        """
        cmd = [
            "aider",
            "--yes",  # Auto-confirm
            "--no-git",  # We handle git ourselves
            "--no-pretty",  # Clean output
        ]

        if self.model:
            cmd.extend(["--model", self.model])

        if self.auto_test and self.test_cmd:
            cmd.extend(["--test-cmd", self.test_cmd])
            cmd.append("--auto-test")

        # Add the message
        cmd.extend(["--message", task_prompt])

        return cmd

    def _build_interactive_command(self) -> list[str]:
        """Build interactive Aider command.

        Returns:
            Command list
        """
        cmd = [
            "aider",
            "--no-git",
            "--no-pretty",
        ]

        if self.model:
            cmd.extend(["--model", self.model])

        if self.auto_test and self.test_cmd:
            cmd.extend(["--test-cmd", self.test_cmd])
            cmd.append("--auto-test")

        return cmd

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for Aider.

        Returns:
            Environment dictionary
        """
        env = os.environ.copy()

        # Aider needs API keys based on model
        if self.model:
            if "anthropic" in self.model.lower():
                if "ANTHROPIC_API_KEY" not in env:
                    raise ValueError("ANTHROPIC_API_KEY not set")
            elif "openai" in self.model.lower() or "gpt" in self.model.lower():
                if "OPENAI_API_KEY" not in env:
                    raise ValueError("OPENAI_API_KEY not set")
            elif "gemini" in self.model.lower():
                if "GOOGLE_API_KEY" not in env:
                    raise ValueError("GOOGLE_API_KEY not set")

        return env

    def _sync_aider_commits(self) -> None:
        """Sync any commits made by Aider to our protocol format.

        Aider makes its own commits. We rewrite them to follow protocol.
        """
        # Since we use --no-git, Aider doesn't commit
        # We just commit any changes ourselves
        if self._has_uncommitted_changes():
            self.iteration += 1
            self._git("add", "-A")
            self._commit(CommitAction.EDIT, f"Aider edit (iteration {self.iteration})")

    def _has_uncommitted_changes(self) -> bool:
        """Check for uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

    def _has_target_files(self) -> bool:
        """Check if target files were created."""
        # Look for any .py files in src/
        src_dir = self.workspace / "src"
        if src_dir.exists():
            py_files = list(src_dir.glob("*.py"))
            return len(py_files) > 0
        return False
