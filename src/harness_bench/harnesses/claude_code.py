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
from .ralph_base import RalphLoopBase


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


def normalize_claude_model(model: str) -> str:
    """Normalize model name for Claude Code CLI.

    Claude Code CLI accepts:
    - Short aliases: 'sonnet', 'opus', 'haiku'
    - Full model names: 'claude-sonnet-4-5-20250929'

    It does NOT accept provider prefixes like 'anthropic/'.

    Args:
        model: Model name (may include provider prefix or version aliases)

    Returns:
        Normalized model name for Claude Code CLI
    """
    if not model:
        return model

    # Strip provider prefix (e.g., 'anthropic/claude-sonnet-4-5-20250929')
    if "/" in model:
        model = model.split("/", 1)[1]

    # Map common aliases to Claude Code CLI format
    # The CLI accepts both short aliases and full names
    aliases = {
        # Sonnet 4.5 aliases
        "sonnet-4.5": "sonnet",
        "sonnet-4-5": "sonnet",
        "claude-sonnet-4.5": "sonnet",
        "claude-sonnet-4-5": "sonnet",
        # Opus 4.5 aliases
        "opus-4.5": "opus",
        "opus-4-5": "opus",
        "claude-opus-4.5": "opus",
        "claude-opus-4-5": "opus",
        # Haiku 4.5 aliases
        "haiku-4.5": "haiku",
        "haiku-4-5": "haiku",
        "claude-haiku-4.5": "haiku",
        "claude-haiku-4-5": "haiku",
        # Sonnet 4.0 aliases
        "sonnet-4.0": "claude-sonnet-4-20250514",
        "sonnet-4": "claude-sonnet-4-20250514",
        # Opus 4.0 aliases
        "opus-4.0": "claude-opus-4-20250514",
        "opus-4": "claude-opus-4-20250514",
    }

    model_lower = model.lower()
    if model_lower in aliases:
        return aliases[model_lower]

    return model


def expand_claude_model_id(model: str) -> str:
    """Expand model alias to full model ID.

    For result tracking and reporting, we want the full model ID rather than
    short aliases. This is the reverse of normalize_claude_model.

    Args:
        model: Model name (may be short alias or full ID)

    Returns:
        Full model ID (e.g., 'claude-opus-4-5-20251101')
    """
    if not model:
        return model

    model_lower = model.lower()

    # Map short aliases to full model IDs
    alias_to_full = {
        "sonnet": "claude-sonnet-4-5-20250929",
        "opus": "claude-opus-4-5-20251101",
        "haiku": "claude-haiku-4-5-20251001",
    }

    if model_lower in alias_to_full:
        return alias_to_full[model_lower]

    # Already a full model ID or unknown
    return model


class RalphLoopBridge(RalphLoopBase):
    """Ralph Wiggum-style while loop bridge for Claude Code.

    Semi-dumb loop that tracks state in files/git, not LLM context.
    Each iteration gets fresh context but can see prior work via files.

    Key features:
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
            model: Claude model (can use aliases like 'sonnet-4.5' or full names)
            max_iterations: Max loop iterations
            total_timeout: TOTAL timeout for entire test (seconds)
            stagnation_limit: Stop after N iterations with no file changes
            allowed_tools: Allowed tools list
            verbose: Print real-time progress to stdout
            verify_timeout: Timeout for verification script (seconds)
        """
        # Normalize model name for Claude Code CLI
        normalized_model = normalize_claude_model(model) if model else model
        super().__init__(
            workspace=workspace,
            verify_script=verify_script,
            model=normalized_model,
            max_iterations=max_iterations,
            total_timeout=total_timeout,
            stagnation_limit=stagnation_limit,
            verbose=verbose,
            verify_timeout=verify_timeout,
        )
        self.allowed_tools = allowed_tools or [
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
        ]

    @property
    def log_filename(self) -> str:
        """Return the log filename for Claude Code."""
        return ".ralph_log.txt"

    def _run_harness_command(self, prompt: str, timeout: float) -> tuple[bool, str]:
        """Run Claude Code (fresh context - no --continue).

        Uses Popen with explicit process management for reliable timeout handling.
        subprocess.run timeout doesn't always kill child processes properly.

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds

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

        self._log(f"Command: claude -p --model {self.model} ... (timeout: {timeout:.0f}s)")

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
                    start_time = time.time()

                    while True:
                        # Check timeout
                        elapsed = time.time() - start_time
                        if elapsed > timeout:
                            raise subprocess.TimeoutExpired(cmd, timeout)

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

                # Store response for result tracking
                self._last_harness_response = stdout

                # Log any errors
                if returncode != 0 and stderr:
                    self._log(f"Stderr: {stderr[:500]}", "ERROR")

                if returncode == 0:
                    return True, "completed"
                else:
                    return False, f"exit_code={returncode}"

            except subprocess.TimeoutExpired:
                self._log(f"TIMEOUT after {timeout:.0f}s - killing process group", "WARN")
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

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for Claude Code.

        Returns:
            Environment dictionary

        Raises:
            EnvironmentError: If ANTHROPIC_API_KEY is not set
        """
        from ..exceptions import EnvironmentError

        env = os.environ.copy()
        if "ANTHROPIC_API_KEY" not in env:
            raise EnvironmentError("ANTHROPIC_API_KEY not set")
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


class ClaudeCodeSubscriptionBridge(RalphLoopBase):
    """Claude Code bridge using subscription (no API key required).

    Uses tmux to run Claude Code interactively with your Claude subscription,
    like CIN-Interface does. This avoids the -p flag which requires an API key.

    Key differences from RalphLoopBridge:
    - Uses interactive Claude Code (no -p flag)
    - Runs via tmux session with send-keys
    - Captures full conversation logs via Claude's transcript
    - Works with Claude subscription instead of API key
    - Produces comprehensive log file with header, turn content, and summary

    Usage:
        bridge = ClaudeCodeSubscriptionBridge(workspace, verify_script="verify.py")
        success = bridge.run(task_id="L1-PY-01", run_id="run_abc123")
    """

    harness_id = "claude-code-subscription"
    harness_vendor = "anthropic"
    harness_version = "1.0.0"

    def __init__(
        self,
        workspace: Path,
        verify_script: Path | str | None = None,
        model: str | None = "sonnet",
        max_iterations: int = 10,
        total_timeout: int = 300,
        stagnation_limit: int = 3,
        allowed_tools: list[str] | None = None,
        verbose: bool = True,
        verify_timeout: int = 300,
        task_id: str | None = None,
        append_system_prompt: bool = True,
    ):
        """Initialize subscription bridge.

        Args:
            workspace: Path to task workspace
            verify_script: Path to verify.py
            model: Claude model (aliases like 'sonnet', 'opus', 'haiku')
            max_iterations: Max loop iterations
            total_timeout: TOTAL timeout for entire test (seconds)
            stagnation_limit: Stop after N iterations with no file changes
            allowed_tools: Allowed tools list
            verbose: Print real-time progress to stdout
            verify_timeout: Timeout for verification script (seconds)
            task_id: Task identifier for logging
            append_system_prompt: Add system prompt encouraging thorough testing (default: True)
        """
        normalized_model = normalize_claude_model(model) if model else model
        super().__init__(
            workspace=workspace,
            verify_script=verify_script,
            model=normalized_model,
            max_iterations=max_iterations,
            total_timeout=total_timeout,
            stagnation_limit=stagnation_limit,
            verbose=verbose,
            verify_timeout=verify_timeout,
        )
        self.allowed_tools = allowed_tools or [
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
        ]
        self._tmux_session: str | None = None
        self._completion_file: Path | None = None
        self._task_id = task_id
        self._append_system_prompt = append_system_prompt
        self._iteration_cost: float = 0.0
        self._last_response: str = ""
        # Structured result tracking (JSON format like dual-agent benchmark)
        self._conversation_log: list[dict[str, Any]] = []
        self._started_timestamp: str = ""
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._last_verify_result: dict[str, Any] | None = None

    @property
    def log_filename(self) -> str:
        """Return the log filename for Claude Code subscription."""
        return ".claude_subscription_log.txt"

    def _init_result_tracking(self, task_prompt: str) -> None:
        """Initialize structured result tracking.

        Delegates to base class to capture initial files and set up turn 0.

        Args:
            task_prompt: The original task prompt
        """
        # Call base class to capture initial files and set up turn 0
        super()._init_result_tracking(task_prompt)

    def _clean_pane_output(self, raw_output: str) -> str:
        """Clean up tmux pane capture to remove terminal chrome.

        Removes:
        - Command line echo (everything before first ❯ prompt)
        - Claude Code welcome box (unicode box-drawing characters)
        - Trailing status line

        Args:
            raw_output: Raw tmux pane capture

        Returns:
            Cleaned output with just the conversation
        """
        lines = raw_output.split('\n')
        cleaned_lines = []
        in_conversation = False

        for line in lines:
            # Start capturing at first ❯ prompt (conversation start)
            if not in_conversation and '❯' in line:
                in_conversation = True

            if in_conversation:
                # Skip lines that are mostly box-drawing characters (welcome box)
                box_chars = set('╭╮╰╯│─┌┐└┘├┤┬┴┼▐▛▜▌▝▘█')
                if line.strip():
                    non_box = sum(1 for c in line if c not in box_chars and c not in ' ')
                    total = len(line.strip())
                    # Skip if more than 60% box characters
                    if total > 0 and non_box / total < 0.4:
                        continue

                # Skip status line at bottom
                if 'bypass permissions' in line.lower():
                    continue
                if line.strip().startswith('⏵⏵'):
                    continue

                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).strip()

    def _log_coder_turn(
        self,
        response: str,
        iteration_cost: float,
        elapsed: float,
        tool_calls: list[dict] | None = None,
    ) -> None:
        """Log a coder turn with response and workspace files.

        Overrides base to clean terminal chrome from pane capture.
        Uses same key names as base class for consistency.

        Args:
            response: Claude's full response (pane capture)
            iteration_cost: Cost for this iteration in USD
            elapsed: Elapsed time in seconds
            tool_calls: Optional list of tool calls (unused, for signature compat)
        """
        # Clean up the pane output to remove terminal chrome
        cleaned_response = self._clean_pane_output(response)

        # Call base class with cleaned response
        super()._log_coder_turn(cleaned_response, iteration_cost, elapsed, tool_calls)

    # Critical checkpoints that determine pass/fail (others are informational)
    CRITICAL_CHECKPOINTS = {
        "file_exists", "syntax_valid", "preflight", "publisher_runs",
        "subscriber_runs", "samples_received", "samples_sent",
    }

    def _log_verification_turn(self, verify_result: dict[str, Any]) -> None:
        """Log verification result as a turn.

        Stores test_results as structured JSON with checkpoints marked as:
        - "pass": checkpoint passed
        - "fail": critical checkpoint failed
        - "warn": non-critical checkpoint failed (informational)

        Args:
            verify_result: Verification result dict
        """
        self._last_verify_result = verify_result

        details = verify_result.get("details", {})
        raw_checkpoints = details.get("checkpoints", []) or verify_result.get("checkpoints", [])

        # Build structured checkpoints with proper status
        checkpoints = []
        for cp in raw_checkpoints:
            name = cp.get("name", "unknown")
            passed = cp.get("passed", False)
            cp_details = cp.get("details", {})

            if passed:
                status = "pass"
            elif name in self.CRITICAL_CHECKPOINTS:
                status = "fail"
            else:
                status = "warn"  # Non-critical failure

            checkpoints.append({
                "name": name,
                "status": status,
                "details": cp_details,
            })

        # Build structured test results
        test_results = {
            "success": verify_result.get("success", False),
            "score": verify_result.get("score", 0.0),
            "message": verify_result.get("message", ""),
            "checkpoints": checkpoints,
        }

        # Update the last coder turn with structured test results
        if self._conversation_log and self._conversation_log[-1].get("role") == "coder":
            self._conversation_log[-1]["test_results"] = test_results

    def _generate_result_json(self, success: bool, reason: str, elapsed_seconds: float) -> Path:
        """Generate structured JSON result file.

        Args:
            success: Whether the task succeeded
            reason: Reason for success/failure
            elapsed_seconds: Total elapsed time

        Returns:
            Path to the generated JSON file
        """
        import datetime

        task_id = self._task_id or self.workspace.name or "unknown"
        timestamp = datetime.datetime.now().isoformat()

        # Extract verification data first (needed for top-level fields)
        samples_matched = 0
        samples_expected = 0
        verification_score = 0.0
        if self._last_verify_result:
            details = self._last_verify_result.get("details", {})
            samples_matched = details.get("samples_received", 0)
            verification_score = self._last_verify_result.get("score", 0.0)

            # Extract samples_expected from checkpoint details (verify scripts store it there)
            for cp in details.get("checkpoints", []):
                if cp.get("name") == "samples_received":
                    cp_details = cp.get("details", {})
                    samples_expected = cp_details.get("expected", 0)
                    break

        # Build result structure - key metrics at top for easy reading
        # Use full model ID for tracking/reporting (not alias like "opus")
        full_model_id = expand_claude_model_id(self.model or "sonnet")
        result = {
            "task_id": task_id,
            "model": full_model_id,
            "harness": self.harness_id,
            "success": success,
            "reason": reason,
            "samples_matched": samples_matched,
            "samples_expected": samples_expected,
            "verification_score": verification_score,
            "total_iterations": self.iteration,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "time_seconds": round(elapsed_seconds, 2),
            "timestamp": self._started_timestamp,
            "completed_at": timestamp,
            "harness_version": self.harness_version,
            "config": {
                "max_iterations": self.max_iterations,
                "total_timeout": self.total_timeout,
                "stagnation_limit": self.stagnation_limit,
            },
            "conversation_log": self._conversation_log,
        }

        # Write JSON file (use full model ID for consistency)
        json_filename = f"{task_id}_{full_model_id}_{timestamp.replace(':', '-')}.json"
        json_path = self.workspace / json_filename
        with open(json_path, "w") as f:
            json.dump(result, f, indent=2)

        self._log(f"Result JSON: {json_filename}")
        return json_path

    def _generate_session_id(self) -> str:
        """Generate a unique tmux session ID."""
        import uuid
        return f"harness-bench-{uuid.uuid4().hex[:8]}"

    def _check_tmux_available(self) -> bool:
        """Check if tmux is available."""
        try:
            result = subprocess.run(
                ["which", "tmux"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _create_completion_hook(self) -> Path:
        """Create a temporary hook script that signals completion.

        Returns:
            Path to the completion signal file
        """
        import tempfile

        # Create completion signal file path
        completion_file = self.workspace / f".claude_complete_{self.iteration}"

        # Create hook script that touches completion file on Stop event
        hook_script = f'''#!/bin/bash
# Harness-bench completion hook
input=$(cat)
hook_event=$(echo "$input" | jq -r '.hook_event_name // "unknown"')

if [ "$hook_event" = "Stop" ] || [ "$hook_event" = "SessionEnd" ]; then
    touch "{completion_file}"
fi
'''
        hook_path = self.workspace / ".harness_completion_hook.sh"
        hook_path.write_text(hook_script)
        hook_path.chmod(0o755)

        return completion_file

    def _setup_hooks(self, completion_file: Path) -> Path:
        """Setup Claude Code hooks for logging and completion detection.

        Creates a comprehensive hook that:
        1. Logs all events to .claude_events_iter{N}.jsonl
        2. Extracts assistant responses from Claude's transcript
        3. Signals completion when Stop/SessionEnd fires

        Args:
            completion_file: Path where completion signal will be written

        Returns:
            Path to the hook script
        """
        # Comprehensive hook modeled after CIN-Interface's vibecraft-hook.sh
        hook_script = f'''#!/bin/bash
# Harness-bench Claude Code hook - captures full conversation with responses
# Based on CIN-Interface vibecraft-hook.sh pattern

set -e

# Add common paths (hooks run with minimal PATH)
KNOWN_PATHS=(
  "/opt/homebrew/bin"
  "/usr/local/bin"
  "$HOME/.local/bin"
  "/usr/bin"
  "/bin"
)
for dir in "${{KNOWN_PATHS[@]}}"; do
  [ -d "$dir" ] && export PATH="$dir:$PATH"
done

# Find jq
JQ=$(command -v jq 2>/dev/null || echo "")
if [ -z "$JQ" ]; then
    # Fallback: just signal completion without parsing
    read -r line
    if echo "$line" | grep -q '"Stop"\\|"SessionEnd"'; then
        touch "{completion_file}"
    fi
    exit 0
fi

# Read input from stdin
input=$(cat)

# Parse basic fields
hook_event=$("$JQ" -r '.hook_event_name // "unknown"' <<< "$input")
session_id=$("$JQ" -r '.session_id // "unknown"' <<< "$input")
cwd=$("$JQ" -r '.cwd // ""' <<< "$input")
transcript_path=$("$JQ" -r '.transcript_path // ""' <<< "$input")

# Timestamp (macOS compatible)
if [[ "$OSTYPE" == "darwin"* ]]; then
    if command -v perl &> /dev/null; then
        timestamp=$(perl -MTime::HiRes=time -e 'printf "%.0f", time * 1000')
    else
        timestamp=$(($(date +%s) * 1000))
    fi
else
    timestamp=$(($(date +%s) * 1000 + $(date +%N | cut -c1-3)))
fi

# Output files
EVENTS_FILE="{self.workspace}/.claude_events_iter{self.iteration}.jsonl"
TRANSCRIPT_LOG="{self.workspace}/.claude_full_transcript_iter{self.iteration}.jsonl"

# Extract assistant response from transcript if available
assistant_response=""
if [ -n "$transcript_path" ] && [ -f "$transcript_path" ]; then
    # Extract last assistant response (same as CIN-Interface)
    assistant_response=$(tail -200 "$transcript_path" | \\
        "$JQ" -rs '[.[] | select(.type == "assistant") | select(.message.content | map(select(.type == "text")) | length > 0)] | last | .message.content | map(select(.type == "text")) | map(.text) | join("\\n")' 2>/dev/null || echo "")
fi

# Build event based on type
case "$hook_event" in
    PreToolUse)
        tool_name=$("$JQ" -r '.tool_name // "unknown"' <<< "$input")
        tool_input=$("$JQ" -c '.tool_input // {{}}' <<< "$input")

        # Extract assistant text that preceded this tool call
        assistant_text=""
        if [ -n "$transcript_path" ] && [ -f "$transcript_path" ]; then
            assistant_text=$(tail -30 "$transcript_path" | \\
                "$JQ" -rs '
                  (to_entries | map(select(.value.type == "user")) | last | .key) as $last_user |
                  to_entries | map(select(.key > ($last_user // -1))) |
                  map(.value) |
                  map(select(.type == "assistant")) |
                  map(.message.content | map(select(.type == "text")) | map(.text)) |
                  flatten | join("\\n")
                ' 2>/dev/null || echo "")
        fi

        event=$("$JQ" -n -c \\
            --arg type "pre_tool_use" \\
            --argjson ts "$timestamp" \\
            --arg session "$session_id" \\
            --arg tool "$tool_name" \\
            --argjson toolInput "$tool_input" \\
            --arg assistantText "$assistant_text" \\
            '{{type: $type, timestamp: $ts, sessionId: $session, tool: $tool, toolInput: $toolInput, assistantText: $assistantText}}')
        ;;

    PostToolUse)
        tool_name=$("$JQ" -r '.tool_name // "unknown"' <<< "$input")
        tool_response=$("$JQ" -c '.tool_response // {{}}' <<< "$input")

        event=$("$JQ" -n -c \\
            --arg type "post_tool_use" \\
            --argjson ts "$timestamp" \\
            --arg session "$session_id" \\
            --arg tool "$tool_name" \\
            --argjson toolResponse "$tool_response" \\
            '{{type: $type, timestamp: $ts, sessionId: $session, tool: $tool, toolResponse: $toolResponse}}')
        ;;

    Stop|SubagentStop)
        event=$("$JQ" -n -c \\
            --arg type "stop" \\
            --argjson ts "$timestamp" \\
            --arg session "$session_id" \\
            --arg response "$assistant_response" \\
            '{{type: $type, timestamp: $ts, sessionId: $session, response: $response}}')

        # Signal completion
        touch "{completion_file}"

        # Copy full transcript if available
        if [ -n "$transcript_path" ] && [ -f "$transcript_path" ]; then
            cp "$transcript_path" "$TRANSCRIPT_LOG" 2>/dev/null || true
        fi
        ;;

    SessionEnd)
        event=$("$JQ" -n -c \\
            --arg type "session_end" \\
            --argjson ts "$timestamp" \\
            --arg session "$session_id" \\
            --arg response "$assistant_response" \\
            '{{type: $type, timestamp: $ts, sessionId: $session, response: $response}}')

        # Signal completion
        touch "{completion_file}"

        # Copy full transcript if available
        if [ -n "$transcript_path" ] && [ -f "$transcript_path" ]; then
            cp "$transcript_path" "$TRANSCRIPT_LOG" 2>/dev/null || true
        fi
        ;;

    UserPromptSubmit)
        prompt=$("$JQ" -r '.prompt // ""' <<< "$input")
        event=$("$JQ" -n -c \\
            --arg type "user_prompt" \\
            --argjson ts "$timestamp" \\
            --arg session "$session_id" \\
            --arg prompt "$prompt" \\
            '{{type: $type, timestamp: $ts, sessionId: $session, prompt: $prompt}}')
        ;;

    *)
        # Log raw input for unknown events
        event=$("$JQ" -c '. + {{"logged_at": '"$timestamp"'}}' <<< "$input")
        ;;
esac

# Append event to JSONL file
echo "$event" >> "$EVENTS_FILE"

exit 0
'''
        hook_path = self.workspace / ".harness_hook.sh"
        hook_path.write_text(hook_script)
        hook_path.chmod(0o755)
        return hook_path

    def _send_to_tmux_safe(self, session_id: str, text: str) -> None:
        """Send text to tmux session using load-buffer + paste-buffer.

        This is the reliable method used by CIN-Interface for sending
        large/complex prompts to interactive Claude sessions.

        Args:
            session_id: tmux session name
            text: Text to send
        """
        import secrets

        # Create temp file with unique name
        temp_file = Path(f"/tmp/harness-bench-prompt-{int(time.time())}-{secrets.token_hex(8)}.txt")
        temp_file.write_text(text)

        try:
            # Load text into tmux buffer
            subprocess.run(
                ["tmux", "load-buffer", str(temp_file)],
                check=True,
                capture_output=True,
            )
            # Paste buffer into session
            subprocess.run(
                ["tmux", "paste-buffer", "-t", session_id],
                check=True,
                capture_output=True,
            )
            # Small delay for paste to complete
            time.sleep(0.1)
            # Send Enter to submit
            subprocess.run(
                ["tmux", "send-keys", "-t", session_id, "Enter"],
                check=True,
                capture_output=True,
            )
        finally:
            # Clean up temp file
            try:
                temp_file.unlink()
            except Exception:
                pass

    def _run_harness_command(self, prompt: str, timeout: float) -> tuple[bool, str]:
        """Run Claude Code interactively via tmux with subscription.

        Uses the same pattern as CIN-Interface:
        1. Create tmux session
        2. Start Claude Code interactively
        3. Send prompt via load-buffer + paste-buffer
        4. Wait for completion via hooks
        5. Capture full conversation log

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds

        Returns:
            Tuple of (success: bool, reason: str)
        """
        # Check tmux availability - fail if not available (no silent API fallback)
        if not self._check_tmux_available():
            self._log("ERROR: tmux is required for subscription mode but not found", "ERROR")
            self._log("Install tmux: brew install tmux (macOS) or apt install tmux (Linux)", "ERROR")
            raise RuntimeError("tmux is required for ClaudeCodeSubscriptionBridge but was not found")

        # Setup completion detection via hooks
        completion_file = self.workspace / f".claude_complete_{self.iteration}"
        if completion_file.exists():
            completion_file.unlink()

        hook_path = self._setup_hooks(completion_file)

        # Generate unique tmux session name
        session_id = self._generate_session_id()
        self._tmux_session = session_id

        # Build claude command (interactive mode - no -p flag!)
        claude_args = [
            "--dangerously-skip-permissions",
            "--permission-mode=bypassPermissions",
        ]
        if self.model:
            claude_args.extend(["--model", self.model])
        if self.allowed_tools:
            claude_args.extend(["--allowedTools", ",".join(self.allowed_tools)])

        # Optionally add system prompt appendix to encourage thorough task completion
        # This helps match the behavior of -p mode which tends to be more thorough
        if self._append_system_prompt:
            append_prompt = (
                "CRITICAL: You MUST run tests and verify your work before declaring the task complete. "
                "Do NOT stop after just writing code - actually execute tests to confirm functionality. "
                "If tests fail, debug and fix the issues. Only declare done when tests pass. "
                "Be thorough: read files, write code, run tests, fix issues, repeat until success."
            )
            # Quote the prompt to protect from shell interpretation (contains spaces)
            claude_args.extend(["--append-system-prompt", f'"{append_prompt}"'])

        # Add hooks via settings override for completion detection and logging
        # Tool hooks use matcher: '*', generic hooks have no matcher
        tool_hook_entry = {
            "matcher": "*",  # Match all tools
            "hooks": [{"type": "command", "command": str(hook_path), "timeout": 10}]
        }
        generic_hook_entry = {
            "hooks": [{"type": "command", "command": str(hook_path), "timeout": 10}]
        }
        hooks_dict = {
            "hooks": {
                "Stop": [generic_hook_entry],
                "SessionEnd": [generic_hook_entry],
                "PreToolUse": [tool_hook_entry],
                "PostToolUse": [tool_hook_entry],
            }
        }
        hooks_json = json.dumps(hooks_dict)
        # Single-quote the JSON to protect it from shell interpretation
        claude_args.extend(["--settings", f"'{hooks_json}'"])

        claude_cmd = f"claude {' '.join(claude_args)}"
        self._log(f"Command: {claude_cmd}")

        # Create tmux session in workspace directory
        try:
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_id, "-c", str(self.workspace)],
                check=True,
                capture_output=True,
            )
            self._log(f"Created tmux session: {session_id}")
        except subprocess.CalledProcessError as e:
            self._log(f"Failed to create tmux session: {e}", "ERROR")
            return False, f"tmux_create_failed: {e}"

        # Create conversation log file
        conversation_log = self.workspace / f".claude_conversation_iter{self.iteration}.txt"

        # Save prompt to temp file for reliable delivery
        prompt_file = self.workspace / ".harness_prompt.txt"
        prompt_file.write_text(prompt)

        try:
            # Step 1: Write full command to a runner script
            # The command with all args + settings JSON is too long for tmux send-keys
            # (causes terminal line buffer issues). Writing to a script file avoids this.
            full_cmd = f"{claude_cmd} < '{prompt_file}'"
            runner_script = self.workspace / ".harness_runner.sh"
            runner_script.write_text(f"#!/bin/bash\n{full_cmd}\n")
            runner_script.chmod(0o755)
            self._log(f"Starting Claude with runner script (cmd length: {len(full_cmd)})")

            subprocess.run(
                ["tmux", "send-keys", "-t", session_id, f"'{runner_script}'", "Enter"],
                check=True,
                capture_output=True,
            )
            self._log("Started Claude Code with prompt")

            # Step 4: Wait for completion (poll completion file from hooks)
            start_time = time.time()
            poll_interval = 2.0
            last_pane_capture = ""

            while time.time() - start_time < timeout:
                # Check completion signal from hooks
                if completion_file.exists():
                    self._log("Completion signal received from hooks")
                    break

                # Check if tmux session still exists
                result = subprocess.run(
                    ["tmux", "has-session", "-t", session_id],
                    capture_output=True,
                )
                if result.returncode != 0:
                    self._log("tmux session ended", "WARN")
                    break

                # Periodic progress logging
                if self.verbose:
                    elapsed = time.time() - start_time
                    if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                        self._log(f"Still running... ({elapsed:.0f}s elapsed)")

                time.sleep(poll_interval)

            elapsed = time.time() - start_time
            timed_out = elapsed >= timeout and not completion_file.exists()

            # Step 5: Capture final pane output (full conversation)
            pane_output = ""
            try:
                # Check tmux session status before capture
                status_result = subprocess.run(
                    ["tmux", "has-session", "-t", session_id],
                    capture_output=True,
                )
                self._log(f"tmux session {session_id} status: {'exists' if status_result.returncode == 0 else 'DOES NOT EXIST'}")

                # Capture with large scroll history (-S -10000 = last 10000 lines)
                capture_result = subprocess.run(
                    ["tmux", "capture-pane", "-t", session_id, "-p", "-S", "-10000"],
                    capture_output=True,
                    text=True,
                )
                pane_output = capture_result.stdout
                if capture_result.stderr:
                    self._log(f"tmux capture-pane stderr: {capture_result.stderr}", "WARN")
                if capture_result.returncode != 0:
                    self._log(f"tmux capture-pane returned {capture_result.returncode}", "WARN")

                conversation_log.write_text(pane_output)
                self._log(f"Conversation log saved: {conversation_log.name} ({len(pane_output)} chars)")

                # Also save structured JSONL for consistency with other bridges
                jsonl_log = self.workspace / f".claude_conversation_iter{self.iteration}.jsonl"
                with open(jsonl_log, 'w') as f:
                    f.write(json.dumps({
                        "type": "interactive_session",
                        "mode": "subscription",
                        "iteration": self.iteration,
                        "timestamp": time.time(),
                        "elapsed_seconds": elapsed,
                        "content": pane_output,
                        "completed": not timed_out,
                    }) + "\n")

                # Store for comprehensive log and base class result tracking
                self._last_response = pane_output
                self._last_harness_response = pane_output  # For base class _log_coder_turn

            except Exception as e:
                self._log(f"Failed to capture pane: {e}", "WARN")

            # Step 6: Copy Claude's internal transcript and calculate cost
            transcript_path = self._copy_claude_transcript()
            iteration_cost = 0.0
            if transcript_path:
                iteration_cost = self._calculate_cost_from_transcript(transcript_path)
                self.total_cost_usd += iteration_cost

            # Note: Base class execute_task will call _log_coder_turn after verification

            if timed_out:
                self._log(f"TIMEOUT after {timeout:.0f}s", "WARN")
                return False, "timeout"

            return True, "completed"

        except Exception as e:
            self._log(f"Error: {e}", "ERROR")
            import traceback
            self._log(traceback.format_exc(), "ERROR")
            return False, f"error: {e}"

        finally:
            # Cleanup: kill tmux session
            try:
                subprocess.run(
                    ["tmux", "kill-session", "-t", session_id],
                    capture_output=True,
                )
                self._log(f"Killed tmux session: {session_id}")
            except Exception:
                pass

            # Cleanup temp files (keep logs)
            for temp_file in [hook_path, prompt_file]:
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception:
                    pass

    # Anthropic pricing per million tokens (as of Jan 2025)
    # https://www.anthropic.com/pricing
    ANTHROPIC_PRICING = {
        # Model: (input_per_mtok, output_per_mtok, cache_write_multiplier, cache_read_multiplier)
        "sonnet": (3.00, 15.00, 1.25, 0.10),
        "opus": (15.00, 75.00, 1.25, 0.10),
        "haiku": (0.80, 4.00, 1.25, 0.10),
        # Full model names
        "claude-sonnet-4-5-20250929": (3.00, 15.00, 1.25, 0.10),
        "claude-opus-4-5-20251101": (15.00, 75.00, 1.25, 0.10),
        "claude-haiku-4-5-20251001": (0.80, 4.00, 1.25, 0.10),
        # Older versions
        "claude-sonnet-4-20250514": (3.00, 15.00, 1.25, 0.10),
    }

    def _calculate_cost_from_transcript(self, transcript_path: Path) -> float:
        """Calculate cost from transcript usage data.

        Parses the transcript JSONL file and extracts FINAL token usage
        (usage values are cumulative, so we take the last entry).

        Args:
            transcript_path: Path to transcript JSONL file

        Returns:
            Estimated cost in USD
        """
        if not transcript_path.exists():
            return 0.0

        # Get pricing for model
        model_key = self.model or "sonnet"
        # Try exact match first, then prefix match
        pricing = self.ANTHROPIC_PRICING.get(model_key)
        if not pricing:
            for key in self.ANTHROPIC_PRICING:
                if key in model_key or model_key in key:
                    pricing = self.ANTHROPIC_PRICING[key]
                    break
        if not pricing:
            pricing = self.ANTHROPIC_PRICING["sonnet"]  # Default

        input_per_mtok, output_per_mtok, cache_write_mult, cache_read_mult = pricing

        # Usage values in transcript are CUMULATIVE (running totals)
        # We need the FINAL values, not the sum
        # Each iteration creates a fresh Claude session, so transcript is per-iteration
        final_usage = None
        session_id = None

        try:
            with open(transcript_path) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("type") == "assistant" and entry.get("message", {}).get("usage"):
                            final_usage = entry["message"]["usage"]
                            session_id = entry.get("sessionId")
                    except json.JSONDecodeError:
                        continue

            if not final_usage:
                self._log("No usage data found in transcript")
                return 0.0

            # Extract final cumulative values
            total_input = final_usage.get("input_tokens", 0)
            total_output = final_usage.get("output_tokens", 0)
            total_cache_write = final_usage.get("cache_creation_input_tokens", 0)
            total_cache_read = final_usage.get("cache_read_input_tokens", 0)

            # Calculate cost
            # Regular input tokens
            input_cost = (total_input / 1_000_000) * input_per_mtok
            # Output tokens
            output_cost = (total_output / 1_000_000) * output_per_mtok
            # Cache write (1.25x input price)
            cache_write_cost = (total_cache_write / 1_000_000) * input_per_mtok * cache_write_mult
            # Cache read (0.1x input price)
            cache_read_cost = (total_cache_read / 1_000_000) * input_per_mtok * cache_read_mult

            total_cost = input_cost + output_cost + cache_write_cost + cache_read_cost

            self._log(f"Token usage: input={total_input}, output={total_output}, "
                     f"cache_write={total_cache_write}, cache_read={total_cache_read}")
            self._log(f"Calculated cost: ${total_cost:.4f} (model={model_key})")

            return total_cost

        except Exception as e:
            self._log(f"Failed to calculate cost from transcript: {e}", "WARN")
            return 0.0

    def _copy_claude_transcript(self) -> Path | None:
        """Copy Claude Code's most recent transcript file to workspace.

        Returns:
            Path to the copied transcript, or None if not found
        """
        import shutil

        # Claude stores transcripts at ~/.claude/projects/<project-hash>/
        claude_dir = Path.home() / ".claude" / "projects"
        if not claude_dir.exists():
            return None

        # Find the most recently modified transcript across all projects
        # (within the last 5 minutes to match this session)
        cutoff_time = time.time() - 300  # Last 5 minutes
        newest_transcript = None
        newest_mtime = 0

        for project_dir in claude_dir.iterdir():
            if project_dir.is_dir():
                for transcript in project_dir.glob("*.jsonl"):
                    try:
                        mtime = transcript.stat().st_mtime
                        if mtime > cutoff_time and mtime > newest_mtime:
                            newest_mtime = mtime
                            newest_transcript = transcript
                    except Exception:
                        pass

        # Copy only the most recent transcript
        if newest_transcript:
            try:
                dest = self.workspace / f".claude_transcript_{newest_transcript.name}"
                shutil.copy2(newest_transcript, dest)
                self._log(f"Copied transcript: {dest.name}")
                return dest
            except Exception as e:
                self._log(f"Failed to copy transcript: {e}", "WARN")

        return None

    def _get_env(self) -> dict[str, str]:
        """Get environment variables.

        For subscription mode, no API key required.
        For API fallback, needs ANTHROPIC_API_KEY.
        """
        env = os.environ.copy()
        # Don't require API key for subscription mode
        # The fallback will fail gracefully if no key and no tmux
        return env
