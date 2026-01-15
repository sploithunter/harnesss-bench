"""OpenAI Codex bridge implementation.

OpenAI Codex CLI is OpenAI's terminal-based coding assistant.
This bridge integrates it with the Harness Bench protocol.

Usage:
    bridge = CodexBridge(workspace, model="gpt-4")
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


class CodexBridge(HarnessBridge):
    """Bridge for OpenAI Codex CLI.

    Note: This is a placeholder implementation. The actual Codex CLI
    interface may differ. Update this when the official CLI is available.
    """

    harness_id = "codex"
    harness_vendor = "openai"
    harness_version = "1.0.0"

    def __init__(
        self,
        workspace: Path,
        model: str | None = "gpt-4",
        max_turns: int = 20,
        timeout: int = 300,
        approval_mode: str = "auto",  # auto, suggest, full-auto
    ):
        """Initialize Codex bridge.

        Args:
            workspace: Path to task workspace
            model: OpenAI model to use
            max_turns: Maximum conversation turns
            timeout: Total timeout in seconds
            approval_mode: How to handle approvals (auto, suggest, full-auto)
        """
        super().__init__(workspace, model)
        self.max_turns = max_turns
        self.timeout = timeout
        self.approval_mode = approval_mode

    def execute_task(self, task_prompt: str) -> bool:
        """Execute task using Codex CLI.

        Args:
            task_prompt: The task prompt from TASK.md

        Returns:
            True if task completed successfully
        """
        cmd = self._build_command(task_prompt)

        self.log_event("codex_start", {
            "model": self.model,
            "approval_mode": self.approval_mode,
        })

        try:
            start_time = time.time()

            # Run Codex CLI
            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=self._get_env(),
            )

            elapsed = time.time() - start_time

            # Commit any changes made
            if self._has_uncommitted_changes():
                self.commit_edit("Codex generated code")

            self.log_event("codex_complete", {
                "exit_code": result.returncode,
                "elapsed": elapsed,
            })

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            self.log_event("codex_timeout", {"timeout": self.timeout})
            return False
        except FileNotFoundError:
            # Codex CLI not installed
            self.log_event("codex_not_found", {
                "message": "Codex CLI not found. Install with: pip install openai-codex"
            })
            return False
        except Exception as e:
            self.log_event("codex_error", {"error": str(e)})
            return False

    def _build_command(self, task_prompt: str) -> list[str]:
        """Build Codex CLI command.

        Note: This is based on expected CLI interface. Update when official.

        Args:
            task_prompt: Task prompt

        Returns:
            Command list
        """
        cmd = [
            "codex",  # Or "openai-codex" depending on installation
        ]

        # Model selection
        if self.model:
            cmd.extend(["--model", self.model])

        # Approval mode
        cmd.extend(["--approval-mode", self.approval_mode])

        # Working directory
        cmd.extend(["--writable-root", str(self.workspace)])

        # The prompt/instruction
        cmd.extend(["--prompt", task_prompt])

        return cmd

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for Codex.

        Returns:
            Environment dictionary
        """
        env = os.environ.copy()

        if "OPENAI_API_KEY" not in env:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        return env

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


class CodexRalphLoopBridge(HarnessBridge):
    """Ralph Wiggum-style while loop bridge for OpenAI Codex CLI.

    Semi-dumb loop that tracks state in files/git, not LLM context.
    Each iteration gets fresh context but can see prior work via files.

    Key features:
    - No session continuation: Fresh context each iteration
    - State in files: progress.txt, .ralph_status.json
    - Circuit breaker: Stops on stagnation (no file changes)
    - Simple feedback: Dumps error output for next iteration
    - TOTAL timeout for entire test, not per iteration

    Usage:
        bridge = CodexRalphLoopBridge(workspace, verify_script="verify.py")
        success = bridge.run(task_id="L1-PY-01", run_id="run_abc123")
    """

    harness_id = "codex"
    harness_vendor = "openai"
    harness_version = "1.0.0"

    def __init__(
        self,
        workspace: Path,
        verify_script: Path | str | None = None,
        model: str | None = "o3-mini",
        max_iterations: int = 10,
        total_timeout: int = 300,
        stagnation_limit: int = 3,
        verbose: bool = True,
        verify_timeout: int = 300,
        sandbox_mode: str = "workspace-write",
    ):
        """Initialize Codex Ralph loop bridge.

        Args:
            workspace: Path to task workspace
            verify_script: Path to verify.py
            model: OpenAI model (default: o3-mini)
            max_iterations: Max loop iterations
            total_timeout: TOTAL timeout for entire test (seconds)
            stagnation_limit: Stop after N iterations with no file changes
            verbose: Print real-time progress to stdout
            verify_timeout: Timeout for verification script (seconds)
            sandbox_mode: Codex sandbox policy (read-only, workspace-write, danger-full-access)
        """
        super().__init__(workspace, model)
        self.verify_script = Path(verify_script).resolve() if verify_script else None
        self.max_iterations = max_iterations
        self.total_timeout = total_timeout
        self.stagnation_limit = stagnation_limit
        self.verify_timeout = verify_timeout
        self.verbose = verbose
        self.sandbox_mode = sandbox_mode
        self.iteration = 0
        self.stagnation_count = 0
        self.last_file_hash = ""
        self._start_time = None
        self.total_cost_usd = 0.0
        self._progress_log: list[str] = []

    def _log(self, message: str, level: str = "INFO") -> None:
        """Log message to stdout and progress log."""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}"
        if self.verbose:
            print(log_line, flush=True)
        # Also append to a detailed log file
        log_file = self.workspace / ".codex_ralph_log.txt"
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
        self._log(f"Codex Ralph loop started: max_iterations={self.max_iterations}, total_timeout={self.total_timeout}s")
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
            self.log_event("codex_ralph_iteration_start", {
                "iteration": self.iteration,
                "stagnation_count": self.stagnation_count,
                "time_remaining": remaining,
            })

            # Build prompt with progress context embedded
            self._log("Building prompt...")
            prompt = self._build_ralph_prompt(task_prompt)
            self._log(f"Prompt length: {len(prompt)} chars")

            # Run Codex with remaining time as timeout
            self._log(f"Running Codex (timeout: {remaining:.0f}s)...")
            codex_start = time.time()
            codex_success, codex_reason = self._run_codex(prompt, timeout=remaining)
            codex_elapsed = time.time() - codex_start
            self._log(f"Codex finished: {codex_reason}, elapsed={codex_elapsed:.1f}s")

            # Commit changes
            self._log("Checking for file changes...")
            files_changed = self._commit_if_changed()
            self._log(f"Files changed: {files_changed}")

            # Check stagnation (circuit breaker)
            if not files_changed:
                self.stagnation_count += 1
                self._log(f"No changes - stagnation count: {self.stagnation_count}/{self.stagnation_limit}", "WARN")
                self._progress_log.append(f"No files changed (stagnation: {self.stagnation_count})")
                if self.stagnation_count >= self.stagnation_limit:
                    self._log("CIRCUIT BREAKER: Stopping due to stagnation", "ERROR")
                    self.log_event("codex_ralph_circuit_breaker", {
                        "reason": "stagnation",
                        "iterations_without_change": self.stagnation_count,
                    })
                    break
            else:
                self.stagnation_count = 0

            # Run verification
            if self.verify_script and self.verify_script.exists():
                self._log("Running verification...")
                verify_start = time.time()
                verify_result = self._run_verification()
                verify_elapsed = time.time() - verify_start
                self._log(f"Verification finished: elapsed={verify_elapsed:.1f}s")

                if verify_result.get("success", False):
                    total_elapsed = time.time() - self._start_time
                    self._log(f"VERIFICATION PASSED! Total time: {total_elapsed:.1f}s", "SUCCESS")
                    self._progress_log.append("VERIFICATION PASSED!")
                    self.log_event("codex_ralph_success", {"iteration": self.iteration})
                    return True

                # Log failure details for next iteration prompt
                error_msg = verify_result.get("message", "Unknown error")
                self._log(f"Verification failed: {error_msg}", "WARN")
                self._progress_log.append(f"Iteration {self.iteration} - Verification failed: {error_msg}")

                # Extract checkpoints from nested structure
                details = verify_result.get("details", {})
                checkpoints = details.get("checkpoints", []) or verify_result.get("checkpoints", [])
                for cp in checkpoints:
                    if not cp.get("passed", False):
                        cp_details = cp.get("details", {})
                        error_info = cp_details.get("stderr", "") or cp_details.get("error", "") or cp.get("message", "")
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

            iter_elapsed = time.time() - iter_start
            self._log(f"Iteration {self.iteration} complete: {iter_elapsed:.1f}s, remaining: {self._time_remaining():.0f}s")

        total_elapsed = time.time() - self._start_time
        self._log(f"Codex Ralph loop finished: iterations={self.iteration}, total_time={total_elapsed:.1f}s", "WARN")
        self.log_event("codex_ralph_max_iterations", {"iterations": self.iteration})
        return False

    def _init_state_files(self) -> None:
        """Initialize Ralph state files."""
        progress_file = self.workspace / "progress.txt"
        if not progress_file.exists():
            progress_file.write_text("# Codex Ralph Loop Progress\n\n")

        status_file = self.workspace / ".ralph_status.json"
        if not status_file.exists():
            status_file.write_text(json.dumps({
                "iteration": 0,
                "status": "running",
                "last_verification": None,
            }, indent=2))

    def _build_ralph_prompt(self, original_prompt: str) -> str:
        """Build prompt with progress context embedded.

        Unlike Claude Code's Ralph which relies on reading progress.txt,
        this version includes progress directly in the prompt.
        """
        parts = [original_prompt]

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

    def _run_codex(self, prompt: str, timeout: float | None = None) -> tuple[bool, str]:
        """Run Codex CLI (fresh context each time).

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds

        Returns:
            Tuple of (success: bool, reason: str)
        """
        import signal

        cmd = [
            "codex", "exec",
            "--dangerously-bypass-approvals-and-sandbox",  # For automation
            "--json",  # JSONL output for parsing
            "-C", str(self.workspace),  # Working directory
        ]

        if self.model:
            cmd.extend(["-m", self.model])

        # Add the prompt as the last argument
        cmd.append(prompt)

        effective_timeout = timeout if timeout else self.total_timeout
        self._log(f"Command: codex exec -m {self.model} -C {self.workspace} ... (timeout: {effective_timeout:.0f}s)")

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.workspace,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._get_env(),
                preexec_fn=os.setsid if os.name != 'nt' else None,
            )

            try:
                stdout, stderr = proc.communicate(timeout=effective_timeout)
                returncode = proc.returncode

                # Try to extract cost from Codex JSONL output
                # Each line is a JSON event, look for cost info
                if stdout:
                    for line in stdout.strip().split('\n'):
                        try:
                            event = json.loads(line)
                            # Codex may emit usage/cost info in various formats
                            if 'usage' in event:
                                # Estimate cost from tokens (rough estimate)
                                usage = event['usage']
                                input_tokens = usage.get('input_tokens', 0)
                                output_tokens = usage.get('output_tokens', 0)
                                # Rough pricing for o3-mini (adjust as needed)
                                cost_usd = (input_tokens * 0.001 + output_tokens * 0.002) / 1000
                                self.total_cost_usd += cost_usd
                        except json.JSONDecodeError:
                            continue

                self._log(f"Codex exit={returncode}, estimated_cost=${self.total_cost_usd:.4f}")

                if returncode != 0 and stderr:
                    self._log(f"Stderr: {stderr[:500]}", "ERROR")

                if returncode == 0:
                    return True, "completed"
                else:
                    return False, f"exit_code={returncode}"

            except subprocess.TimeoutExpired:
                self._log(f"TIMEOUT after {effective_timeout:.0f}s - killing process group", "WARN")
                if os.name != 'nt':
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    proc.kill()
                proc.wait()
                return False, "timeout"

        except FileNotFoundError:
            self._log("Codex CLI not found. Install with: npm install -g @openai/codex", "ERROR")
            return False, "codex_not_found"
        except Exception as e:
            self._log(f"Exception: {str(e)}", "ERROR")
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
                current_hash = hash(result.stdout.strip())
                if current_hash != self.last_file_hash:
                    self.last_file_hash = current_hash
                    subprocess.run(
                        ["git", "add", "-A"],
                        cwd=self.workspace,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["git", "commit", "-m", f"[codex-ralph] Iteration {self.iteration}"],
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
                cwd=self.workspace,
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
        """Get environment variables for Codex."""
        env = os.environ.copy()

        if "OPENAI_API_KEY" not in env:
            raise ValueError("OPENAI_API_KEY not set")

        return env


class CodexAPIBridge(HarnessBridge):
    """Bridge that uses OpenAI API directly instead of Codex CLI.

    This is an alternative approach that uses the OpenAI API
    to generate code completions, useful when CLI is not available.
    """

    harness_id = "codex-api"
    harness_vendor = "openai"

    def __init__(
        self,
        workspace: Path,
        model: str | None = "gpt-4",
        max_iterations: int = 10,
        timeout: int = 300,
    ):
        """Initialize API-based Codex bridge.

        Args:
            workspace: Path to task workspace
            model: OpenAI model to use
            max_iterations: Maximum improvement iterations
            timeout: Total timeout in seconds
        """
        super().__init__(workspace, model)
        self.max_iterations = max_iterations
        self.timeout = timeout

    def execute_task(self, task_prompt: str) -> bool:
        """Execute task using OpenAI API.

        Args:
            task_prompt: The task prompt

        Returns:
            True if successful
        """
        try:
            import openai
        except ImportError:
            self.log_event("openai_not_installed", {
                "message": "Install openai package: pip install openai"
            })
            return False

        client = openai.OpenAI()

        self.log_event("codex_api_start", {"model": self.model})

        try:
            start_time = time.time()

            # Initial code generation
            system_prompt = self._build_system_prompt()
            response = client.chat.completions.create(
                model=self.model or "gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": task_prompt},
                ],
                max_tokens=4096,
            )

            # Extract code from response
            content = response.choices[0].message.content
            code = self._extract_code(content)

            if code:
                # Write the code
                self._write_code(code)
                self.commit_edit("Initial code generation")

            elapsed = time.time() - start_time
            self.log_event("codex_api_complete", {
                "elapsed": elapsed,
                "tokens": response.usage.total_tokens if response.usage else 0,
            })

            return bool(code)

        except Exception as e:
            self.log_event("codex_api_error", {"error": str(e)})
            return False

    def _build_system_prompt(self) -> str:
        """Build system prompt for code generation."""
        return """You are an expert programmer. Generate clean, working code based on the task description.

Output your code in markdown code blocks with the filename as a comment at the top:
```python
# filename: src/solution.py
... code here ...
```

Focus on:
- Correctness and functionality
- Clean, readable code
- Proper error handling
- Following best practices"""

    def _extract_code(self, content: str) -> dict[str, str]:
        """Extract code blocks from response.

        Args:
            content: Response content

        Returns:
            Dict mapping filename to code
        """
        import re

        code_blocks = {}

        # Find all code blocks
        pattern = r"```(\w+)?\n(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)

        for lang, code in matches:
            # Try to extract filename from first line comment
            lines = code.strip().split("\n")
            filename = None

            if lines and lines[0].startswith("# filename:"):
                filename = lines[0].replace("# filename:", "").strip()
                code = "\n".join(lines[1:])
            else:
                # Default filename based on language
                ext = {"python": ".py", "javascript": ".js", "typescript": ".ts"}.get(lang, ".txt")
                filename = f"src/solution{ext}"

            code_blocks[filename] = code

        return code_blocks

    def _write_code(self, code_blocks: dict[str, str]) -> None:
        """Write code blocks to files.

        Args:
            code_blocks: Dict mapping filename to code
        """
        for filename, code in code_blocks.items():
            filepath = self.workspace / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(code)
