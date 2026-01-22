"""RalphLoopBase - Shared base class for Ralph-style iteration loops.

Ralph Wiggum-style loops are semi-dumb iteration loops that:
- Track state in files/git, not LLM context
- Give each iteration fresh context but access to prior work
- Use circuit breakers to stop on stagnation
- Use a TOTAL timeout shared across all iterations

This module provides the shared implementation used by:
- RalphLoopBridge (Claude Code)
- AiderRalphLoopBridge (Aider)
- CodexRalphLoopBridge (OpenAI Codex)
- CursorRalphLoopBridge (Cursor Agent)
"""

from __future__ import annotations

import datetime
import json
import os
import signal
import subprocess
import time
from abc import abstractmethod
from pathlib import Path
from typing import Any

from ..core.bridge import HarnessBridge
from ..exceptions import (
    EnvironmentError,
    TimeoutError,
    VerificationError,
    StagnationError,
)


class RalphLoopBase(HarnessBridge):
    """Base class for Ralph-style stateless iteration loops.

    Subclasses must implement:
    - _run_harness_command(): Execute the harness CLI
    - _get_env(): Get environment variables with required API keys
    - harness_id, harness_vendor, harness_version class attributes

    Optional overrides:
    - _init_state_files(): Customize state file initialization
    - _build_prompt(): Customize prompt building with progress context
    """

    def __init__(
        self,
        workspace: Path,
        verify_script: Path | str | None = None,
        model: str | None = None,
        max_iterations: int = 10,
        total_timeout: int = 300,
        stagnation_limit: int = 3,
        verbose: bool = True,
        verify_timeout: int = 300,
    ):
        """Initialize Ralph loop bridge.

        Args:
            workspace: Path to task workspace
            verify_script: Path to verify.py
            model: Model to use (harness-specific format)
            max_iterations: Max loop iterations
            total_timeout: TOTAL timeout for entire test (seconds)
            stagnation_limit: Stop after N iterations with no file changes
            verbose: Print real-time progress to stdout
            verify_timeout: Timeout for verification script (seconds)
        """
        super().__init__(workspace, model)
        self.verify_script = Path(verify_script).resolve() if verify_script else None
        self.max_iterations = max_iterations
        self.total_timeout = total_timeout
        self.stagnation_limit = stagnation_limit
        self.verify_timeout = verify_timeout
        self.verbose = verbose
        self.iteration = 0
        self.stagnation_count = 0
        self.last_file_hash = ""
        self._start_time: float | None = None
        self.total_cost_usd = 0.0
        self._progress_log: list[str] = []

        # Structured result tracking (consistent JSON format across all harnesses)
        self._conversation_log: list[dict[str, Any]] = []
        self._started_timestamp: str = ""
        self._task_id: str | None = None
        self._last_verify_result: dict[str, Any] | None = None
        self._last_harness_response: str = ""  # Captured response from harness
        self._initial_files: dict[str, str] = {}  # Files before model runs

    @property
    def log_filename(self) -> str:
        """Return the log filename for this harness."""
        return f".{self.harness_id}_ralph_log.txt"

    def _log(self, message: str, level: str = "INFO") -> None:
        """Log message to stdout and progress file.

        Args:
            message: Log message
            level: Log level (INFO, WARN, ERROR, SUCCESS)
        """
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}"
        if self.verbose:
            print(log_line, flush=True)
        # Also append to a detailed log file
        log_file = self.workspace / self.log_filename
        with open(log_file, "a") as f:
            f.write(log_line + "\n")

    def _time_remaining(self) -> float:
        """Get seconds remaining before total timeout.

        Returns:
            Remaining time in seconds (0 if timeout exceeded)
        """
        if self._start_time is None:
            return self.total_timeout
        elapsed = time.time() - self._start_time
        return max(0, self.total_timeout - elapsed)

    def _is_timed_out(self) -> bool:
        """Check if total timeout has been exceeded.

        Returns:
            True if timeout exceeded
        """
        return self._time_remaining() <= 0

    def _init_state_files(self) -> None:
        """Initialize Ralph state files.

        Creates progress.txt and .ralph_status.json if they don't exist.
        Subclasses can override to customize state file initialization.
        """
        progress_file = self.workspace / "progress.txt"
        if not progress_file.exists():
            progress_file.write_text(f"# {self.harness_id} Ralph Loop Progress\n\n")

        status_file = self.workspace / ".ralph_status.json"
        if not status_file.exists():
            status_file.write_text(json.dumps({
                "iteration": 0,
                "status": "running",
                "last_verification": None,
            }, indent=2))

    def _append_progress(self, content: str) -> None:
        """Append to progress file (visible to future iterations).

        Args:
            content: Content to append
        """
        progress_file = self.workspace / "progress.txt"
        with open(progress_file, "a") as f:
            f.write(f"{content}\n")

    def _update_status(self, verify_result: dict[str, Any]) -> None:
        """Update status JSON file with verification results.

        Args:
            verify_result: Verification result dict
        """
        status_file = self.workspace / ".ralph_status.json"
        status = {
            "iteration": self.iteration,
            "status": "passed" if verify_result.get("success") else "failed",
            "last_verification": verify_result,
            "stagnation_count": self.stagnation_count,
        }
        status_file.write_text(json.dumps(status, indent=2))

    # =========================================================================
    # Structured Result Tracking (consistent JSON across all harnesses)
    # =========================================================================

    def _capture_workspace_files(self) -> dict[str, str]:
        """Capture all workspace files recursively.

        Returns:
            Dict mapping relative paths to file contents
        """
        files = {}
        code_extensions = (".py", ".md", ".txt", ".json", ".yaml", ".yml", ".idl", ".xml", ".c", ".cpp", ".h", ".hpp")
        for f in self.workspace.rglob("*"):
            # Skip hidden files/directories
            if f.is_file() and not any(p.startswith(".") for p in f.relative_to(self.workspace).parts):
                if f.suffix in code_extensions:
                    try:
                        rel_path = str(f.relative_to(self.workspace))
                        files[rel_path] = f.read_text()
                    except Exception:
                        pass
        return files

    def _init_result_tracking(self, task_prompt: str) -> None:
        """Initialize structured result tracking.

        Sets up conversation log with turn 0 (instructions) and captures
        initial file state for tracking file provenance.

        Args:
            task_prompt: The original task prompt
        """
        self._started_timestamp = datetime.datetime.now().isoformat()

        # Capture initial workspace state (files provided by task/harness)
        self._initial_files = self._capture_workspace_files()

        # Turn 0: instructions with initial files
        self._conversation_log.append({
            "turn": 0,
            "role": "instructions",
            "source": "TASK.md",
            "content": task_prompt,
            "initial_files": self._initial_files,  # Files provided before model runs
        })

    def _log_coder_turn(
        self,
        response: str,
        iteration_cost: float,
        elapsed: float,
        tool_calls: list[dict] | None = None,
    ) -> None:
        """Log a coder turn with response and workspace files.

        Tracks file provenance: created, modified, or unchanged from initial state.

        Args:
            response: The harness response (stdout or captured conversation)
            iteration_cost: Cost for this iteration in USD
            elapsed: Elapsed time in seconds
            tool_calls: Optional list of tool calls made (for harnesses that track them)
        """
        # Capture current workspace files
        current_files = self._capture_workspace_files()

        # Categorize files by provenance
        files_created = {}    # New files created by model
        files_modified = {}   # Existing files modified by model
        files_unchanged = {}  # Existing files not modified

        initial = getattr(self, '_initial_files', {})

        for path, content in current_files.items():
            if path not in initial:
                files_created[path] = content
            elif initial[path] != content:
                files_modified[path] = content
            else:
                files_unchanged[path] = content

        turn_data = {
            "turn": self.iteration,
            "role": "coder",
            "harness_output": response,
            "iteration_cost_usd": iteration_cost,
            "elapsed_seconds": elapsed,
            # File provenance tracking
            "files_created": files_created,
            "files_modified": files_modified,
            "files_unchanged": files_unchanged,
        }

        # Add tool calls if provided
        if tool_calls:
            turn_data["tool_calls"] = tool_calls

        # Add test results if we have them
        if self._last_verify_result:
            turn_data["test_results"] = self._last_verify_result

        self._conversation_log.append(turn_data)

    def _generate_result_json(self, success: bool, reason: str, elapsed_seconds: float) -> Path:
        """Generate structured JSON result file.

        This produces consistent output format across all harnesses for comparison.

        Args:
            success: Whether the task succeeded
            reason: Reason for success/failure
            elapsed_seconds: Total elapsed time

        Returns:
            Path to the generated JSON file
        """
        task_id = self._task_id or self.workspace.name or "unknown"
        timestamp = datetime.datetime.now().isoformat()

        # Extract verification data
        samples_matched = 0
        samples_expected = 0
        verification_score = 0.0
        if self._last_verify_result:
            details = self._last_verify_result.get("details", {})
            samples_matched = details.get("samples_received", 0)
            verification_score = self._last_verify_result.get("score", 0.0)

            # Extract samples_expected from checkpoint details
            for cp in details.get("checkpoints", []):
                if cp.get("name") == "samples_received":
                    cp_details = cp.get("details", {})
                    samples_expected = cp_details.get("expected", 0)
                    break

        # Build result structure - consistent format across all harnesses
        result = {
            "task_id": task_id,
            "model": self.model or "unknown",
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
            "harness_version": getattr(self, 'harness_version', '1.0.0'),
            "config": {
                "max_iterations": self.max_iterations,
                "total_timeout": self.total_timeout,
                "stagnation_limit": self.stagnation_limit,
            },
            "conversation_log": self._conversation_log,
        }

        # Write JSON file
        safe_model = (self.model or "unknown").replace("/", "_")
        json_filename = f"{task_id}_{safe_model}_{timestamp.replace(':', '-')}.json"
        json_path = self.workspace / json_filename
        with open(json_path, "w") as f:
            json.dump(result, f, indent=2)

        self._log(f"Result JSON: {json_filename}")
        return json_path

    def _build_base_prompt(self, task_prompt: str) -> str:
        """Build prompt with TASK.md and progress context.

        Args:
            task_prompt: Original task prompt

        Returns:
            Enhanced prompt with context
        """
        parts = []

        # Pre-include TASK.md content to ensure the LLM sees requirements first
        task_md = self.workspace / "TASK.md"
        if task_md.exists():
            parts.append("# TASK.md - READ CAREFULLY BEFORE WRITING CODE\n")
            parts.append(task_md.read_text())
            parts.append("\n---\n\n")

        parts.append(task_prompt)

        # Add progress log from previous iterations
        if self._progress_log:
            parts.append("\n\n---\n# Previous Iteration Progress\n")
            # Only include last ~30 entries to avoid prompt bloat
            recent_progress = self._progress_log[-30:]
            if len(self._progress_log) > 30:
                parts.append("(truncated earlier entries...)\n")
            parts.append("\n".join(recent_progress))
            parts.append("\n---\n")
            parts.append("\nFix any issues noted above and complete the task.")

        return "\n".join(parts)

    def _run_verification(self) -> dict[str, Any]:
        """Run verification script.

        Returns:
            Verification result dict with 'success', 'message', 'checkpoints', etc.
        """
        if not self.verify_script or not self.verify_script.exists():
            return {"success": False, "message": "No verification script"}

        self._log(f"Running: python {self.verify_script.name} (timeout: {self.verify_timeout}s)")
        try:
            result = subprocess.run(
                ["python", str(self.verify_script), str(self.workspace)],
                capture_output=True,
                text=True,
                timeout=self.verify_timeout,
                cwd=self.workspace,
            )
            if result.stdout.strip():
                parsed = json.loads(result.stdout.strip())
                self._log(f"Verification result: success={parsed.get('success')}, score={parsed.get('score')}")
                return parsed
            self._log(
                f"No output from verify.py, stderr: {result.stderr[:200] if result.stderr else 'none'}",
                "ERROR"
            )
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

    def _commit_if_changed(self) -> bool:
        """Commit if there are changes.

        Returns:
            True if files changed and were committed
        """
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
                        ["git", "commit", "-m", f"[{self.harness_id}-ralph] Iteration {self.iteration}"],
                        cwd=self.workspace,
                        capture_output=True,
                    )
                    return True
            return False
        except Exception:
            return False

    def _check_stagnation(self, files_changed: bool) -> bool:
        """Check for stagnation and update circuit breaker.

        Args:
            files_changed: Whether files changed in this iteration

        Returns:
            True if circuit breaker should trigger (stop iterations)
        """
        if not files_changed:
            self.stagnation_count += 1
            self._log(
                f"No changes - stagnation count: {self.stagnation_count}/{self.stagnation_limit}",
                "WARN"
            )
            self._progress_log.append(f"No files changed (stagnation: {self.stagnation_count})")
            if self.stagnation_count >= self.stagnation_limit:
                self._log("CIRCUIT BREAKER: Stopping due to stagnation", "ERROR")
                self.log_event(f"{self.harness_id}_ralph_circuit_breaker", {
                    "reason": "stagnation",
                    "iterations_without_change": self.stagnation_count,
                })
                return True
        else:
            self.stagnation_count = 0
        return False

    def _process_verification_failure(self, verify_result: dict[str, Any]) -> None:
        """Log verification failure details for next iteration.

        Args:
            verify_result: Verification result dict
        """
        error_msg = verify_result.get("message", "Unknown error")
        self._log(f"Verification failed: {error_msg}", "WARN")
        self._progress_log.append(f"Iteration {self.iteration} - Verification failed: {error_msg}")

        # Extract checkpoints from nested structure
        details = verify_result.get("details", {})
        checkpoints = details.get("checkpoints", []) or verify_result.get("checkpoints", [])
        for cp in checkpoints:
            if not cp.get("passed", False):
                cp_details = cp.get("details", {})
                error_info = (
                    cp_details.get("stderr", "") or
                    cp_details.get("error", "") or
                    cp.get("message", "")
                )
                if error_info:
                    error_info = error_info.strip()[:1500]
                    cp_msg = f"  FAIL [{cp.get('name')}]: {error_info}"

                    # Add hint for wrong DDS library imports (common hallucination)
                    wrong_dds_libs = ["cyclonedx", "cyclone", "opendds", "fastdds", "fast_dds", "pydds"]
                    if "ModuleNotFoundError" in error_info or "No module named" in error_info:
                        for wrong_lib in wrong_dds_libs:
                            if wrong_lib in error_info.lower():
                                cp_msg += "\n    HINT: For RTI Connext DDS, use 'import rti.connextdds as dds'"
                                break
                    if "module 'dds' has no attribute" in error_info:
                        cp_msg += "\n    HINT: Wrong DDS import. Use 'import rti.connextdds as dds' (not 'import dds')"
                else:
                    cp_msg = f"  FAIL [{cp.get('name')}]: (no details)"
                self._log(cp_msg, "WARN")
                self._progress_log.append(cp_msg)

    def _run_process_with_timeout(
        self,
        cmd: list[str],
        timeout: float,
        env: dict[str, str],
    ) -> tuple[int, str, str]:
        """Run a subprocess with proper timeout and process group handling.

        Args:
            cmd: Command to run
            timeout: Timeout in seconds
            env: Environment variables

        Returns:
            Tuple of (return_code, stdout, stderr)

        Raises:
            TimeoutError: If the process times out
        """
        proc = subprocess.Popen(
            cmd,
            cwd=self.workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            # Start new process group so we can kill all children
            preexec_fn=os.setsid if os.name != 'nt' else None,
        )

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return proc.returncode, stdout, stderr
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
            raise TimeoutError(f"Process timed out after {timeout:.0f}s")

    @abstractmethod
    def _run_harness_command(self, prompt: str, timeout: float) -> tuple[bool, str]:
        """Execute the harness CLI command.

        This is the main method subclasses must implement.

        Args:
            prompt: The prompt to send to the harness
            timeout: Timeout in seconds

        Returns:
            Tuple of (success: bool, reason: str describing outcome)
        """
        pass

    @abstractmethod
    def _get_env(self) -> dict[str, str]:
        """Get environment variables for the harness.

        Must include required API keys.

        Returns:
            Environment dictionary

        Raises:
            EnvironmentError: If required environment variables are missing
        """
        pass

    def execute_task(self, task_prompt: str) -> bool:
        """Execute with Ralph-style while loop.

        State persists in files, not LLM context. Each iteration
        starts fresh but sees prior work via git and progress files.

        Uses TOTAL timeout - iterations share the time budget.

        Generates structured JSON result file with conversation log
        for cross-harness comparison.

        Args:
            task_prompt: The task prompt from TASK.md

        Returns:
            True if verification passed, False otherwise
        """
        self._start_time = time.time()

        # Initialize state files and result tracking
        self._init_state_files()
        self._init_result_tracking(task_prompt)
        self._log(f"{self.harness_id} Ralph loop started: max_iterations={self.max_iterations}, total_timeout={self.total_timeout}s")
        self._log(f"Workspace: {self.workspace}")
        self._log(f"Verify script: {self.verify_script}")
        self._log(f"Model: {self.model}")

        while self.iteration < self.max_iterations:
            # Check total timeout before starting iteration
            remaining = self._time_remaining()
            if remaining <= 0:
                self._log("TOTAL TIMEOUT reached", "ERROR")
                self._progress_log.append("TIMEOUT: Total time limit reached")
                break

            self.iteration += 1
            iter_start = time.time()

            self._log(f"=== ITERATION {self.iteration}/{self.max_iterations} === (remaining: {remaining:.0f}s)")
            self.log_event(f"{self.harness_id}_ralph_iteration_start", {
                "iteration": self.iteration,
                "stagnation_count": self.stagnation_count,
                "time_remaining": remaining,
            })

            # Build prompt with progress context
            self._log("Building prompt...")
            prompt = self._build_base_prompt(task_prompt)
            self._log(f"Prompt length: {len(prompt)} chars")

            # Run harness with remaining time as timeout
            self._log(f"Running {self.harness_id} (timeout: {remaining:.0f}s)...")
            harness_start = time.time()
            harness_success, harness_reason = self._run_harness_command(prompt, timeout=remaining)
            harness_elapsed = time.time() - harness_start
            self._log(f"{self.harness_id} finished: {harness_reason}, elapsed={harness_elapsed:.1f}s")

            # Commit changes
            self._log("Checking for file changes...")
            files_changed = self._commit_if_changed()
            self._log(f"Files changed: {files_changed}")

            # Check stagnation (circuit breaker)
            if self._check_stagnation(files_changed):
                break

            # Run verification
            if self.verify_script and self.verify_script.exists():
                self._log("Running verification...")
                verify_start = time.time()
                verify_result = self._run_verification()
                verify_elapsed = time.time() - verify_start
                self._log(f"Verification finished: elapsed={verify_elapsed:.1f}s")

                # Store for result tracking
                self._last_verify_result = verify_result

                self._update_status(verify_result)

                # Log this iteration to conversation log (after verification so we have results)
                self._log_coder_turn(
                    response=self._last_harness_response,
                    iteration_cost=0.0,  # Subclasses can override to track cost
                    elapsed=harness_elapsed,
                )

                if verify_result.get("success", False):
                    total_elapsed = time.time() - self._start_time
                    self._log(f"VERIFICATION PASSED! Total time: {total_elapsed:.1f}s", "SUCCESS")
                    self._progress_log.append("VERIFICATION PASSED!")
                    self.log_event(f"{self.harness_id}_ralph_success", {"iteration": self.iteration})
                    # Generate result JSON before returning
                    self._generate_result_json(success=True, reason="passed", elapsed_seconds=total_elapsed)
                    return True

                # Log failure details for next iteration prompt
                self._process_verification_failure(verify_result)
            else:
                # No verification script - still log the iteration
                self._log_coder_turn(
                    response=self._last_harness_response,
                    iteration_cost=0.0,
                    elapsed=harness_elapsed,
                )

            iter_elapsed = time.time() - iter_start
            self._log(f"Iteration {self.iteration} complete: {iter_elapsed:.1f}s, remaining: {self._time_remaining():.0f}s")

        total_elapsed = time.time() - self._start_time
        self._log(f"{self.harness_id} Ralph loop finished: iterations={self.iteration}, total_time={total_elapsed:.1f}s", "WARN")
        self.log_event(f"{self.harness_id}_ralph_max_iterations", {"iterations": self.iteration})

        # Generate result JSON for failure case
        reason = "max_iterations" if self.iteration >= self.max_iterations else "timeout"
        if self.stagnation_count >= self.stagnation_limit:
            reason = "stagnation"
        self._generate_result_json(success=False, reason=reason, elapsed_seconds=total_elapsed)

        return False
