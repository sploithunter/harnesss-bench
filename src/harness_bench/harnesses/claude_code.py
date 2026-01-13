"""Claude Code bridge implementation.

Claude Code is Anthropic's CLI coding assistant. This bridge
integrates it with the Harness Bench protocol.

Usage:
    bridge = ClaudeCodeBridge(workspace, model="claude-sonnet-4-20250514")
    success = bridge.run(task_id="L1-PY-01", run_id="run_abc123")
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from ..core.bridge import HarnessBridge
from ..core.protocol import CommitAction


class ClaudeCodeBridge(HarnessBridge):
    """Bridge for Anthropic Claude Code CLI.

    Claude Code can be invoked in non-interactive mode for automation.
    This bridge monitors its output and commits changes as they occur.
    """

    harness_id = "claude-code"
    harness_vendor = "anthropic"
    harness_version = "1.0.0"

    def __init__(
        self,
        workspace: Path,
        model: str | None = "claude-sonnet-4-20250514",
        max_turns: int = 20,
        timeout: int = 300,
        allowed_tools: list[str] | None = None,
    ):
        """Initialize Claude Code bridge.

        Args:
            workspace: Path to task workspace
            model: Claude model to use (default: claude-sonnet-4-20250514)
            max_turns: Maximum conversation turns
            timeout: Total timeout in seconds
            allowed_tools: List of allowed tools (default: all safe tools)
        """
        super().__init__(workspace, model)
        self.max_turns = max_turns
        self.timeout = timeout
        self.allowed_tools = allowed_tools or [
            "Read",
            "Write",
            "Edit",
            "Bash",
            "Glob",
            "Grep",
        ]

    def execute_task(self, task_prompt: str) -> bool:
        """Execute task using Claude Code.

        Args:
            task_prompt: The task prompt from TASK.md

        Returns:
            True if task completed successfully
        """
        # Build Claude Code command
        cmd = self._build_command(task_prompt)

        self.log_event("claude_code_start", {
            "model": self.model,
            "max_turns": self.max_turns,
        })

        try:
            # Run Claude Code with streaming output
            start_time = time.time()
            process = subprocess.Popen(
                cmd,
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._get_env(),
            )

            # Monitor output and commit changes
            last_commit_time = start_time
            output_buffer = []

            while True:
                # Check timeout
                if time.time() - start_time > self.timeout:
                    process.terminate()
                    self.log_event("timeout", {"elapsed": time.time() - start_time})
                    return False

                # Check if process completed
                retcode = process.poll()
                if retcode is not None:
                    break

                # Read output (non-blocking would be better but this is simpler)
                line = process.stdout.readline() if process.stdout else ""
                if line:
                    output_buffer.append(line)
                    self._process_output_line(line)

                # Periodically commit any changes
                if time.time() - last_commit_time > 5:
                    if self._has_uncommitted_changes():
                        self.commit_edit("Progress update")
                        last_commit_time = time.time()

                time.sleep(0.1)

            # Get remaining output
            stdout, stderr = process.communicate()
            if stdout:
                output_buffer.extend(stdout.split("\n"))

            # Final commit of any remaining changes
            if self._has_uncommitted_changes():
                self.commit_edit("Final changes")

            # Log completion
            self.log_event("claude_code_complete", {
                "exit_code": retcode,
                "elapsed": time.time() - start_time,
                "output_lines": len(output_buffer),
            })

            return retcode == 0

        except Exception as e:
            self.log_event("claude_code_error", {"error": str(e)})
            return False

    def _build_command(self, task_prompt: str) -> list[str]:
        """Build the Claude Code CLI command.

        Args:
            task_prompt: Task prompt to pass

        Returns:
            Command list for subprocess
        """
        cmd = [
            "claude",
            "--print",  # Non-interactive mode
            "--output-format", "json",
            "--max-turns", str(self.max_turns),
        ]

        # Add model if specified
        if self.model:
            cmd.extend(["--model", self.model])

        # Add allowed tools
        for tool in self.allowed_tools:
            cmd.extend(["--allowedTools", tool])

        # Add the prompt
        cmd.extend(["--prompt", task_prompt])

        return cmd

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for Claude Code.

        Returns:
            Environment dictionary
        """
        env = os.environ.copy()

        # Ensure ANTHROPIC_API_KEY is set
        if "ANTHROPIC_API_KEY" not in env:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        # Set workspace as working directory context
        env["CLAUDE_CODE_WORKSPACE"] = str(self.workspace)

        return env

    def _process_output_line(self, line: str) -> None:
        """Process a line of Claude Code output.

        Args:
            line: Output line to process
        """
        line = line.strip()
        if not line:
            return

        # Try to parse as JSON event
        try:
            event = json.loads(line)
            event_type = event.get("type", "")

            if event_type == "tool_use":
                tool = event.get("tool", "")
                if tool in ["Write", "Edit"]:
                    # File was modified
                    file_path = event.get("input", {}).get("file_path", "unknown")
                    self.log_event("file_modified", {"path": file_path, "tool": tool})

            elif event_type == "error":
                self.log_event("claude_error", {"message": event.get("message", "")})

        except json.JSONDecodeError:
            # Not JSON, just log as raw output
            pass

    def _has_uncommitted_changes(self) -> bool:
        """Check if workspace has uncommitted changes.

        Returns:
            True if there are changes to commit
        """
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


class ClaudeCodeManualBridge(HarnessBridge):
    """Bridge for manual Claude Code execution.

    Use this when running Claude Code interactively (not automated).
    The bridge sets up the workspace and you run Claude Code manually.
    After completion, call complete() to finalize.

    Usage:
        bridge = ClaudeCodeManualBridge(workspace)
        bridge.setup(task_id="L1-PY-01", run_id="run_abc123")

        # User runs Claude Code manually in the workspace
        # ...

        # After Claude Code finishes:
        bridge.complete(success=True)
    """

    harness_id = "claude-code"
    harness_vendor = "anthropic"

    def execute_task(self, task_prompt: str) -> bool:
        """Manual execution placeholder.

        This just returns True since actual work is done manually.
        """
        print(f"Workspace ready at: {self.workspace}")
        print(f"Task prompt in: {self.workspace / 'TASK.md'}")
        print("\nRun Claude Code manually in the workspace.")
        print("When done, call bridge.complete(success=True/False)")
        return True
