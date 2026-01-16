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
            "-p",  # Print mode (non-interactive)
            "--output-format", "text",  # Use text output for simplicity
            "--dangerously-skip-permissions",  # For automation
        ]

        # Add model if specified
        if self.model:
            cmd.extend(["--model", self.model])

        # Add allowed tools as comma-separated
        if self.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])

        # Add -- separator to prevent options from consuming the prompt
        cmd.append("--")

        # Add the prompt as positional argument (must be last)
        cmd.append(task_prompt)

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


class ClaudeCodeDriverBridge(HarnessBridge):
    """Bridge with driver model for iterative verification.

    This bridge runs Claude Code, checks results with verify.py,
    and feeds back errors for retry - similar to ConnextDev's approach.

    Usage:
        bridge = ClaudeCodeDriverBridge(
            workspace,
            verify_script="/path/to/verify.py",
            max_iterations=5
        )
        success = bridge.run(task_id="L1-PY-01", run_id="run_abc123")
    """

    harness_id = "claude-code"
    harness_vendor = "anthropic"
    harness_version = "1.0.0"

    def __init__(
        self,
        workspace: Path,
        verify_script: Path | str | None = None,
        model: str | None = "claude-sonnet-4-20250514",
        max_iterations: int = 5,
        timeout_per_iteration: int = 300,
        allowed_tools: list[str] | None = None,
    ):
        """Initialize driver bridge.

        Args:
            workspace: Path to task workspace
            verify_script: Path to verify.py script for checking results
            model: Claude model to use
            max_iterations: Maximum retry iterations
            timeout_per_iteration: Timeout per Claude Code invocation
            allowed_tools: List of allowed tools
        """
        super().__init__(workspace, model)
        self.verify_script = Path(verify_script).resolve() if verify_script else None
        self.max_iterations = max_iterations
        self.timeout_per_iteration = timeout_per_iteration
        self.allowed_tools = allowed_tools or [
            "Read",
            "Write",
            "Edit",
            "Bash",
            "Glob",
            "Grep",
        ]
        self.iteration = 0

    def execute_task(self, task_prompt: str) -> bool:
        """Execute task with driver loop.

        Runs Claude Code, verifies, and retries with feedback.

        Args:
            task_prompt: The task prompt from TASK.md

        Returns:
            True if verification passes
        """
        current_prompt = task_prompt

        while self.iteration < self.max_iterations:
            self.iteration += 1

            self.log_event("driver_iteration_start", {
                "iteration": self.iteration,
                "max_iterations": self.max_iterations,
            })

            # Run Claude Code
            success = self._run_claude_code(current_prompt)

            # Commit any changes
            if self._has_uncommitted_changes():
                self.commit_edit(f"Iteration {self.iteration}")

            # Run verification if script provided
            if self.verify_script and self.verify_script.exists():
                verify_result = self._run_verification()

                if verify_result.get("success", False):
                    self.log_event("driver_verification_passed", {
                        "iteration": self.iteration,
                        "score": verify_result.get("score", 1.0),
                    })
                    return True

                # Build feedback prompt for next iteration
                error_msg = verify_result.get("message", "Verification failed")
                checkpoints = verify_result.get("checkpoints", [])
                failed_checks = [
                    cp for cp in checkpoints
                    if not cp.get("passed", False)
                ]

                self.log_event("driver_verification_failed", {
                    "iteration": self.iteration,
                    "message": error_msg,
                    "failed_checks": len(failed_checks),
                })

                # Build retry prompt with feedback
                current_prompt = self._build_retry_prompt(
                    task_prompt, error_msg, failed_checks
                )
            else:
                # No verification script - just check if Claude Code succeeded
                if success:
                    return True

        self.log_event("driver_max_iterations", {
            "iterations": self.iteration,
        })
        return False

    def _run_claude_code(self, prompt: str) -> bool:
        """Run a single Claude Code invocation.

        Uses --continue for subsequent iterations to maintain context.

        Args:
            prompt: Prompt to send

        Returns:
            True if Claude Code exited successfully
        """
        cmd = self._build_command(prompt)

        # Use --continue for iterations after the first to maintain context
        if self.iteration > 1:
            # Insert --continue after 'claude' but before other args
            cmd.insert(1, "--continue")

        try:
            start_time = time.time()
            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout_per_iteration,
                env=self._get_env(),
            )

            elapsed = time.time() - start_time
            self.log_event("claude_code_run", {
                "iteration": self.iteration,
                "exit_code": result.returncode,
                "elapsed": elapsed,
                "stdout_lines": len(result.stdout.split("\n")),
                "continued_session": self.iteration > 1,
            })

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            self.log_event("claude_code_timeout", {
                "iteration": self.iteration,
                "timeout": self.timeout_per_iteration,
            })
            return False
        except Exception as e:
            self.log_event("claude_code_error", {
                "iteration": self.iteration,
                "error": str(e),
            })
            return False

    def _run_verification(self) -> dict[str, Any]:
        """Run the verification script.

        Returns:
            Verification result dict
        """
        try:
            result = subprocess.run(
                ["python", str(self.verify_script), str(self.workspace)],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.workspace,  # verify.py uses Path.cwd()
            )

            # Parse JSON output
            if result.stdout.strip():
                return json.loads(result.stdout.strip())
            else:
                return {
                    "success": False,
                    "message": result.stderr or "No output from verify.py",
                }

        except json.JSONDecodeError:
            return {
                "success": False,
                "message": f"Invalid JSON from verify.py: {result.stdout[:200]}",
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Verification timed out",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Verification error: {str(e)}",
            }

    def _build_retry_prompt(
        self,
        original_prompt: str,
        error_msg: str,
        failed_checks: list[dict]
    ) -> str:
        """Build a prompt for retry with verification feedback.

        Args:
            original_prompt: The original task prompt
            error_msg: Error message from verification
            failed_checks: List of failed checkpoints

        Returns:
            Retry prompt with context
        """
        parts = [
            "The previous attempt did not pass verification.",
            f"\nError: {error_msg}",
        ]

        if failed_checks:
            parts.append("\nFailed checks:")
            for check in failed_checks[:5]:  # Limit to top 5
                name = check.get("name", "Unknown")
                msg = check.get("message", "")
                parts.append(f"  - {name}: {msg}")

        parts.append("\nPlease fix the issues and try again.")
        parts.append("\n---\n")
        parts.append("Original task:")
        parts.append(original_prompt)

        return "\n".join(parts)

    def _build_command(self, prompt: str) -> list[str]:
        """Build the Claude Code CLI command."""
        cmd = [
            "claude",
            "-p",
            "--output-format", "text",
            "--dangerously-skip-permissions",
        ]

        if self.model:
            cmd.extend(["--model", self.model])

        if self.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])

        cmd.append("--")
        cmd.append(prompt)

        return cmd

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for Claude Code."""
        env = os.environ.copy()
        if "ANTHROPIC_API_KEY" not in env:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        env["CLAUDE_CODE_WORKSPACE"] = str(self.workspace)
        return env

    def _has_uncommitted_changes(self) -> bool:
        """Check if workspace has uncommitted changes."""
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


class RalphLoopBridge(HarnessBridge):
    """Ralph Wiggum-style while loop bridge.

    Semi-dumb loop that tracks state in files/git, not LLM context.
    Each iteration gets fresh context but can see prior work via files.

    Key differences from ClaudeCodeDriverBridge:
    - No --continue: Fresh context each iteration (like original Ralph)
    - State in files: progress.txt, .ralph_status.json
    - Circuit breaker: Stops on stagnation (no file changes)
    - Simple feedback: Just dumps error output, no intelligent prompting
    - TOTAL timeout for entire test, not per iteration

    Usage:
        bridge = RalphLoopBridge(workspace, verify_script="verify.py")
        success = bridge.run(task_id="L1-PY-01", run_id="run_abc123")
    """

    harness_id = "claude-code"
    harness_vendor = "anthropic"
    harness_version = "1.0.0"

    def __init__(
        self,
        workspace: Path,
        verify_script: Path | str | None = None,
        model: str | None = "claude-sonnet-4-20250514",
        max_iterations: int = 10,
        total_timeout: int = 300,
        stagnation_limit: int = 3,
        allowed_tools: list[str] | None = None,
        verbose: bool = True,
        verify_timeout: int = 300,
    ):
        """Initialize Ralph loop bridge.

        Args:
            workspace: Path to task workspace
            verify_script: Path to verify.py
            model: Claude model
            max_iterations: Max loop iterations
            total_timeout: TOTAL timeout for entire test (seconds)
            stagnation_limit: Stop after N iterations with no file changes
            allowed_tools: Allowed tools list
            verbose: Print real-time progress to stdout
            verify_timeout: Timeout for verification script (seconds)
        """
        super().__init__(workspace, model)
        # Resolve to absolute path since we run from workspace dir
        self.verify_script = Path(verify_script).resolve() if verify_script else None
        self.max_iterations = max_iterations
        self.total_timeout = total_timeout
        self.stagnation_limit = stagnation_limit
        self.verify_timeout = verify_timeout
        self.allowed_tools = allowed_tools or [
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
        ]
        self.iteration = 0
        self.stagnation_count = 0
        self.last_file_hash = ""
        self.verbose = verbose
        self._start_time = None
        self.total_cost_usd = 0.0

    def _log(self, message: str, level: str = "INFO") -> None:
        """Log message to stdout and progress file."""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}"
        if self.verbose:
            print(log_line, flush=True)
        # Also append to a detailed log file
        log_file = self.workspace / ".ralph_log.txt"
        with open(log_file, "a") as f:
            f.write(log_line + "\n")

    def _time_remaining(self) -> float:
        """Get seconds remaining before total timeout."""
        if self._start_time is None:
            return self.total_timeout
        elapsed = time.time() - self._start_time
        return max(0, self.total_timeout - elapsed)

    def _is_timed_out(self) -> bool:
        """Check if total timeout has been exceeded."""
        return self._time_remaining() <= 0

    def execute_task(self, task_prompt: str) -> bool:
        """Execute with Ralph-style while loop.

        State persists in files, not LLM context. Each iteration
        starts fresh but sees prior work via git and progress files.

        Uses TOTAL timeout - iterations share the time budget.
        """
        self._start_time = time.time()

        # Initialize state files
        self._init_state_files()
        self._log(f"Ralph loop started: max_iterations={self.max_iterations}, total_timeout={self.total_timeout}s")
        self._log(f"Workspace: {self.workspace}")
        self._log(f"Verify script: {self.verify_script}")

        while self.iteration < self.max_iterations:
            # Check total timeout before starting iteration
            remaining = self._time_remaining()
            if remaining <= 0:
                self._log("TOTAL TIMEOUT reached", "ERROR")
                self._append_progress("TIMEOUT: Total time limit reached")
                break

            self.iteration += 1
            iter_start = time.time()

            self._log(f"=== ITERATION {self.iteration}/{self.max_iterations} === (remaining: {remaining:.0f}s)")
            self.log_event("ralph_iteration_start", {
                "iteration": self.iteration,
                "stagnation_count": self.stagnation_count,
                "time_remaining": remaining,
            })

            # Update progress file with iteration info
            self._append_progress(f"=== Iteration {self.iteration} ===")

            # Build prompt (includes progress context)
            self._log("Building prompt...")
            prompt = self._build_ralph_prompt(task_prompt)
            self._log(f"Prompt length: {len(prompt)} chars")

            # Run Claude Code with remaining time as timeout
            self._log(f"Running Claude Code (timeout: {remaining:.0f}s)...")
            cc_start = time.time()
            cc_success, cc_reason = self._run_claude_code(prompt, timeout=remaining)
            cc_elapsed = time.time() - cc_start
            self._log(f"Claude Code finished: {cc_reason}, elapsed={cc_elapsed:.1f}s")

            # Commit changes
            self._log("Checking for file changes...")
            files_changed = self._commit_if_changed()
            self._log(f"Files changed: {files_changed}")

            # Check stagnation (circuit breaker)
            if not files_changed:
                self.stagnation_count += 1
                self._log(f"No changes - stagnation count: {self.stagnation_count}/{self.stagnation_limit}", "WARN")
                self._append_progress(f"No files changed (stagnation: {self.stagnation_count})")
                if self.stagnation_count >= self.stagnation_limit:
                    self._log("CIRCUIT BREAKER: Stopping due to stagnation", "ERROR")
                    self.log_event("ralph_circuit_breaker", {
                        "reason": "stagnation",
                        "iterations_without_change": self.stagnation_count,
                    })
                    self._append_progress("CIRCUIT BREAKER: Stopping due to stagnation")
                    break
            else:
                self.stagnation_count = 0

            # Run verification immediately after Claude Code finishes
            if self.verify_script and self.verify_script.exists():
                self._log("Running verification...")
                verify_start = time.time()
                verify_result = self._run_verification()
                verify_elapsed = time.time() - verify_start
                self._log(f"Verification finished: elapsed={verify_elapsed:.1f}s")

                self._update_status(verify_result)

                if verify_result.get("success", False):
                    total_elapsed = time.time() - self._start_time
                    self._log(f"VERIFICATION PASSED! Total time: {total_elapsed:.1f}s", "SUCCESS")
                    self._append_progress("VERIFICATION PASSED!")
                    self.log_event("ralph_success", {"iteration": self.iteration})
                    return True  # Exit immediately on success

                # Log failure details
                error_msg = verify_result.get("message", "Unknown error")
                self._log(f"Verification failed: {error_msg}", "WARN")
                self._append_progress(f"Verification failed: {error_msg}")

                checkpoints = verify_result.get("checkpoints", [])
                for cp in checkpoints:
                    if not cp.get("passed", False):
                        cp_msg = f"  FAIL: {cp.get('name')}: {cp.get('message', '')}"
                        self._log(cp_msg, "WARN")
                        self._append_progress(cp_msg)

            iter_elapsed = time.time() - iter_start
            self._log(f"Iteration {self.iteration} complete: {iter_elapsed:.1f}s, remaining: {self._time_remaining():.0f}s")

        total_elapsed = time.time() - self._start_time
        self._log(f"Ralph loop finished: iterations={self.iteration}, total_time={total_elapsed:.1f}s", "WARN")
        self.log_event("ralph_max_iterations", {"iterations": self.iteration})
        return False

    def _init_state_files(self) -> None:
        """Initialize Ralph state files."""
        progress_file = self.workspace / "progress.txt"
        if not progress_file.exists():
            progress_file.write_text("# Ralph Loop Progress\n\n")

        status_file = self.workspace / ".ralph_status.json"
        if not status_file.exists():
            status_file.write_text(json.dumps({
                "iteration": 0,
                "status": "running",
                "last_verification": None,
            }, indent=2))

    def _append_progress(self, message: str) -> None:
        """Append to progress file (visible to future iterations)."""
        progress_file = self.workspace / "progress.txt"
        with open(progress_file, "a") as f:
            f.write(f"{message}\n")

    def _update_status(self, verify_result: dict) -> None:
        """Update status JSON file."""
        status_file = self.workspace / ".ralph_status.json"
        status = {
            "iteration": self.iteration,
            "status": "passed" if verify_result.get("success") else "failed",
            "last_verification": verify_result,
            "stagnation_count": self.stagnation_count,
        }
        status_file.write_text(json.dumps(status, indent=2))

    def _build_ralph_prompt(self, original_prompt: str) -> str:
        """Build prompt with progress context.

        Unlike intelligent driver, this just dumps the progress file
        so Claude can see what happened in previous iterations.

        Also pre-includes TASK.md content to ensure it's seen before code generation.
        """
        parts = []

        # Pre-include TASK.md content to ensure the LLM sees requirements first
        task_md = self.workspace / "TASK.md"
        if task_md.exists():
            parts.append("# TASK.md - READ CAREFULLY BEFORE WRITING CODE\n")
            parts.append(task_md.read_text())
            parts.append("\n---\n\n")

        parts.append(original_prompt)

        # Add progress file contents if exists and has content
        progress_file = self.workspace / "progress.txt"
        if progress_file.exists():
            progress = progress_file.read_text().strip()
            if progress and "Iteration" in progress:
                parts.append("\n\n---\n# Previous Iteration Progress\n")
                # Only include last ~50 lines to avoid context bloat
                lines = progress.split("\n")
                if len(lines) > 50:
                    parts.append("(truncated...)\n")
                    lines = lines[-50:]
                parts.append("\n".join(lines))
                parts.append("\n---\n")
                parts.append("\nFix any issues noted above and complete the task.")

        return "\n".join(parts)

    def _run_claude_code(self, prompt: str, timeout: float | None = None) -> tuple[bool, str]:
        """Run Claude Code (fresh context - no --continue).

        Uses Popen with explicit process management for reliable timeout handling.
        subprocess.run timeout doesn't always kill child processes properly.

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds (uses remaining total time)

        Returns:
            Tuple of (success: bool, reason: str)
        """
        import signal

        cmd = [
            "claude", "-p",
            "--output-format", "stream-json",  # Stream JSON for real-time logging
            "--verbose",  # Include full conversation details
            "--dangerously-skip-permissions",
        ]
        if self.model:
            cmd.extend(["--model", self.model])
        if self.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])
        cmd.extend(["--", prompt])

        effective_timeout = timeout if timeout else self.total_timeout
        self._log(f"Command: claude -p --model {self.model} ... (timeout: {effective_timeout:.0f}s)")

        # Create conversation log file for this iteration
        conversation_log_file = self.workspace / f".claude_conversation_iter{self.iteration}.jsonl"

        try:
            # Use Popen for explicit process control with real-time logging
            proc = subprocess.Popen(
                cmd,
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._get_env(),
                # Start new process group so we can kill all children
                preexec_fn=os.setsid if os.name != 'nt' else None,
            )

            try:
                # Read stdout line by line and save to log file in real-time
                stdout_lines = []
                with open(conversation_log_file, 'w') as log_f:
                    import select
                    import time
                    start_time = time.time()

                    while True:
                        # Check timeout
                        elapsed = time.time() - start_time
                        if elapsed > effective_timeout:
                            raise subprocess.TimeoutExpired(cmd, effective_timeout)

                        # Check if process has finished
                        returncode = proc.poll()

                        # Read available output (non-blocking with timeout)
                        if proc.stdout:
                            line = proc.stdout.readline()
                            if line:
                                stdout_lines.append(line)
                                log_f.write(line)
                                log_f.flush()  # Real-time flush for crash recovery
                            elif returncode is not None:
                                # Process finished and no more output
                                break
                        else:
                            break

                stdout = ''.join(stdout_lines)
                stderr = proc.stderr.read() if proc.stderr else ''
                returncode = proc.returncode

                # Parse stream-json output for cost tracking
                cost_usd = 0.0
                for line in stdout_lines:
                    line = line.strip()
                    if line:
                        try:
                            event = json.loads(line)
                            # Look for result event with cost info
                            if event.get("type") == "result":
                                cost_usd = event.get("total_cost_usd", 0.0)
                                self.total_cost_usd += cost_usd
                        except json.JSONDecodeError:
                            pass

                self._log(f"Iteration cost: ${cost_usd:.4f}, Total cost: ${self.total_cost_usd:.4f}")
                self._log(f"Conversation log saved to: {conversation_log_file.name}")

                # Log output summary
                self._log(f"Claude Code exit={returncode}, cost=${cost_usd:.4f}")

                # Log any errors
                if returncode != 0 and stderr:
                    self._log(f"Stderr: {stderr[:500]}", "ERROR")

                if returncode == 0:
                    return True, "completed"
                else:
                    return False, f"exit_code={returncode}"

            except subprocess.TimeoutExpired:
                self._log(f"TIMEOUT after {effective_timeout:.0f}s - killing process group", "WARN")
                # Kill the entire process group (parent + all children)
                if os.name != 'nt':
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass  # Already dead
                else:
                    proc.kill()
                proc.wait()
                return False, "timeout"

        except Exception as e:
            self._log(f"Exception: {str(e)}", "ERROR")
            self._append_progress(f"ERROR: {str(e)}")
            return False, f"error: {str(e)}"

    def _commit_if_changed(self) -> bool:
        """Commit if there are changes. Returns True if files changed."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                # Compute simple hash of changed files
                current_hash = hash(result.stdout.strip())
                if current_hash != self.last_file_hash:
                    self.last_file_hash = current_hash
                    subprocess.run(
                        ["git", "add", "-A"],
                        cwd=self.workspace,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["git", "commit", "-m", f"[ralph] Iteration {self.iteration}"],
                        cwd=self.workspace,
                        capture_output=True,
                    )
                    return True
            return False
        except Exception:
            return False

    def _run_verification(self) -> dict[str, Any]:
        """Run verification script."""
        self._log(f"Running: python {self.verify_script.name} (timeout: {self.verify_timeout}s)")
        try:
            result = subprocess.run(
                ["python", str(self.verify_script), str(self.workspace)],
                capture_output=True,
                text=True,
                timeout=self.verify_timeout,
                cwd=self.workspace,  # verify.py uses Path.cwd()
            )
            if result.stdout.strip():
                parsed = json.loads(result.stdout.strip())
                self._log(f"Verification result: success={parsed.get('success')}, score={parsed.get('score')}")
                return parsed
            self._log(f"No output from verify.py, stderr: {result.stderr[:200] if result.stderr else 'none'}", "ERROR")
            return {"success": False, "message": result.stderr or "No output"}
        except json.JSONDecodeError as e:
            self._log(f"JSON decode error: {e}", "ERROR")
            return {"success": False, "message": f"Invalid JSON: {str(e)}"}
        except subprocess.TimeoutExpired:
            self._log(f"Verification timed out after {self.verify_timeout}s", "ERROR")
            return {"success": False, "message": "Verification timed out"}
        except Exception as e:
            self._log(f"Verification error: {str(e)}", "ERROR")
            return {"success": False, "message": str(e)}

    def _get_env(self) -> dict[str, str]:
        """Get environment variables."""
        env = os.environ.copy()
        if "ANTHROPIC_API_KEY" not in env:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return env


class IntelligentDriverBridge(HarnessBridge):
    """Intelligent driver using the same model as the harness.

    Uses Claude API directly (not Claude Code) to analyze verification
    failures and generate intelligent feedback prompts. Importantly,
    uses the SAME model as the harness to avoid unfair advantage.

    Usage:
        bridge = IntelligentDriverBridge(workspace, verify_script="verify.py")
        success = bridge.run(task_id="L1-PY-01", run_id="run_abc123")
    """

    harness_id = "claude-code"
    harness_vendor = "anthropic"
    harness_version = "1.0.0"

    def __init__(
        self,
        workspace: Path,
        verify_script: Path | str | None = None,
        model: str | None = "claude-sonnet-4-20250514",
        max_iterations: int = 5,
        timeout_per_iteration: int = 300,
        allowed_tools: list[str] | None = None,
    ):
        """Initialize intelligent driver bridge.

        Args:
            workspace: Path to task workspace
            verify_script: Path to verify.py
            model: Claude model (used for BOTH harness AND driver)
            max_iterations: Max iterations
            timeout_per_iteration: Timeout per Claude Code call
            allowed_tools: Allowed tools
        """
        super().__init__(workspace, model)
        self.verify_script = Path(verify_script).resolve() if verify_script else None
        self.max_iterations = max_iterations
        self.timeout_per_iteration = timeout_per_iteration
        self.allowed_tools = allowed_tools or [
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
        ]
        self.iteration = 0
        self._anthropic_client = None

    @property
    def anthropic_client(self):
        """Lazy-load Anthropic client."""
        if self._anthropic_client is None:
            try:
                import anthropic
                self._anthropic_client = anthropic.Anthropic()
            except ImportError:
                raise ImportError("anthropic package required for IntelligentDriverBridge")
        return self._anthropic_client

    def execute_task(self, task_prompt: str) -> bool:
        """Execute with intelligent driver loop."""
        current_prompt = task_prompt

        while self.iteration < self.max_iterations:
            self.iteration += 1

            self.log_event("intelligent_driver_iteration", {
                "iteration": self.iteration,
            })

            # Run Claude Code
            self._run_claude_code(current_prompt)

            # Commit changes
            self._commit_changes()

            # Verify
            if self.verify_script and self.verify_script.exists():
                verify_result = self._run_verification()

                if verify_result.get("success", False):
                    self.log_event("intelligent_driver_success", {
                        "iteration": self.iteration,
                    })
                    return True

                # Use driver model to analyze and generate feedback
                current_prompt = self._generate_intelligent_feedback(
                    task_prompt, verify_result
                )

        return False

    def _generate_intelligent_feedback(
        self,
        original_prompt: str,
        verify_result: dict,
    ) -> str:
        """Use Claude API to generate intelligent feedback.

        Uses the SAME model as the harness to avoid unfair advantage.
        """
        # Read relevant workspace files for context
        workspace_context = self._get_workspace_context()

        driver_prompt = f"""You are a code review assistant. A coding agent attempted a task but verification failed.

## Original Task
{original_prompt}

## Current Workspace Files
{workspace_context}

## Verification Result
{json.dumps(verify_result, indent=2)}

## Your Job
Analyze what went wrong and write a clear, actionable prompt for the coding agent to fix the issues.
Focus on:
1. What specific changes need to be made
2. Which files need modification
3. Any patterns or approaches that might help

Write the prompt as if you're talking directly to the coding agent. Be specific and actionable.
Start with "Fix the following issues:" and list concrete steps."""

        try:
            # Use same model as harness
            response = self.anthropic_client.messages.create(
                model=self.model or "claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": driver_prompt}],
            )

            feedback = response.content[0].text

            self.log_event("intelligent_driver_feedback", {
                "iteration": self.iteration,
                "feedback_length": len(feedback),
            })

            # Combine with original prompt
            return f"""{feedback}

---

## Original Task (for reference)
{original_prompt}"""

        except Exception as e:
            # Fall back to simple feedback if API call fails
            self.log_event("intelligent_driver_fallback", {
                "error": str(e),
            })
            return self._simple_feedback(original_prompt, verify_result)

    def _simple_feedback(self, original_prompt: str, verify_result: dict) -> str:
        """Simple feedback fallback."""
        error_msg = verify_result.get("message", "Unknown error")
        return f"""The previous attempt failed verification.

Error: {error_msg}

Please fix the issues and try again.

---
{original_prompt}"""

    def _get_workspace_context(self) -> str:
        """Get summary of key workspace files."""
        context_parts = []
        key_extensions = [".py", ".cpp", ".cxx", ".hpp", ".h", ".yaml", ".json"]

        for ext in key_extensions:
            for f in self.workspace.glob(f"*{ext}"):
                if f.is_file() and f.stat().st_size < 10000:
                    try:
                        content = f.read_text()
                        context_parts.append(f"### {f.name}\n```\n{content}\n```\n")
                    except Exception:
                        pass

        return "\n".join(context_parts[:10])  # Limit to 10 files

    def _run_claude_code(self, prompt: str) -> bool:
        """Run Claude Code."""
        cmd = [
            "claude", "-p",
            "--output-format", "text",
            "--dangerously-skip-permissions",
        ]
        if self.model:
            cmd.extend(["--model", self.model])
        if self.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])

        # Use --continue for iterations after first
        if self.iteration > 1:
            cmd.insert(1, "--continue")

        cmd.extend(["--", prompt])

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout_per_iteration,
                env=self._get_env(),
            )
            return result.returncode == 0
        except Exception:
            return False

    def _commit_changes(self) -> None:
        """Commit any uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                subprocess.run(["git", "add", "-A"], cwd=self.workspace, capture_output=True)
                subprocess.run(
                    ["git", "commit", "-m", f"[intelligent-driver] Iteration {self.iteration}"],
                    cwd=self.workspace,
                    capture_output=True,
                )
        except Exception:
            pass

    def _run_verification(self) -> dict[str, Any]:
        """Run verification."""
        try:
            result = subprocess.run(
                ["python", str(self.verify_script), str(self.workspace)],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.workspace,  # verify.py uses Path.cwd()
            )
            if result.stdout.strip():
                return json.loads(result.stdout.strip())
            return {"success": False, "message": result.stderr or "No output"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _get_env(self) -> dict[str, str]:
        """Get environment."""
        env = os.environ.copy()
        if "ANTHROPIC_API_KEY" not in env:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return env


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
