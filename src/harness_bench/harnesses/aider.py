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
from .ralph_base import RalphLoopBase


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


class AiderRalphLoopBridge(RalphLoopBase):
    """Ralph Wiggum-style while loop bridge for Aider.

    Adapts the Ralph pattern for Aider's less-agentic nature:
    - State in prompt (not files): Aider doesn't auto-read workspace files
    - Uses --read to specify key files for context
    - Same stagnation detection and circuit breaker logic
    - Total timeout for entire run, not per iteration

    Unlike Claude Code's Ralph which relies on the LLM reading progress.txt,
    this version includes progress directly in the --message prompt.

    Usage:
        bridge = AiderRalphLoopBridge(workspace, verify_script="verify.py")
        success = bridge.run(task_id="L1-PY-01", run_id="run_abc123")
    """

    harness_id = "aider"
    harness_vendor = "aider"
    harness_version = "0.50.0"

    def __init__(
        self,
        workspace: Path,
        verify_script: Path | str | None = None,
        model: str | None = "anthropic/claude-sonnet-4-20250514",
        max_iterations: int = 10,
        total_timeout: int = 300,
        stagnation_limit: int = 3,
        verbose: bool = True,
        verify_timeout: int = 300,
        auto_test: bool = False,
    ):
        """Initialize Aider Ralph loop bridge.

        Args:
            workspace: Path to task workspace
            verify_script: Path to verify.py
            model: Model in aider format (e.g., anthropic/claude-sonnet-4-20250514)
            max_iterations: Max loop iterations
            total_timeout: TOTAL timeout for entire test (seconds)
            stagnation_limit: Stop after N iterations with no file changes
            verbose: Print real-time progress to stdout
            verify_timeout: Timeout for verification script (seconds)
            auto_test: Use Aider's --auto-test with verify.py as test command
        """
        super().__init__(
            workspace=workspace,
            verify_script=verify_script,
            model=model,
            max_iterations=max_iterations,
            total_timeout=total_timeout,
            stagnation_limit=stagnation_limit,
            verbose=verbose,
            verify_timeout=verify_timeout,
        )
        self.auto_test = auto_test

    def _find_key_files(self) -> list[Path]:
        """Find key files in workspace that Aider should know about."""
        key_files = []
        extensions = [".py", ".cpp", ".cxx", ".hpp", ".h", ".yaml", ".json", ".md"]

        # Look for task file
        task_file = self.workspace / "TASK.md"
        if task_file.exists():
            key_files.append(task_file)

        # Always search workspace root, plus src/ if it exists
        search_dirs = [self.workspace]
        src_dir = self.workspace / "src"
        if src_dir.exists():
            search_dirs.append(src_dir)

        for search_dir in search_dirs:
            for ext in extensions:
                for f in search_dir.glob(f"*{ext}"):
                    if f.is_file() and f.stat().st_size < 50000:  # Skip huge files
                        if f not in key_files:  # Avoid duplicates
                            key_files.append(f)

        return key_files[:10]  # Limit total files

    def _run_harness_command(self, prompt: str, timeout: float) -> tuple[bool, str]:
        """Run Aider (fresh context each time - no session continuation).

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds

        Returns:
            Tuple of (success: bool, reason: str)
        """
        import signal

        cmd = [
            "aider",
            "--yes",  # Auto-confirm changes
            "--no-git",  # We handle git ourselves
            "--no-pretty",  # Clean output
            "--no-check-update",  # Don't check for updates
            "--no-fancy-input",  # Disable fancy input for automation
            "--no-stream",  # Don't stream output
            "--edit-format", "whole",  # Force complete file replacement (not append)
            "--auto-lint",  # Run linter after edits
            "--lint-cmd", "python -m py_compile",  # Basic syntax check
        ]

        if self.model:
            cmd.extend(["--model", self.model])

            # Codex models don't support temperature parameter - use custom settings
            if "codex" in self.model.lower():
                codex_settings = Path(__file__).parent.parent.parent.parent / "config" / "codex-model-settings.yml"
                if codex_settings.exists():
                    cmd.extend(["--model-settings-file", str(codex_settings)])
                    self._log(f"Using codex model settings: {codex_settings}")

            # Claude 4.5 models need custom settings (not in aider's default config yet)
            elif "sonnet-4-5" in self.model or "opus-4-5" in self.model or "haiku-4-5" in self.model:
                claude45_settings = Path(__file__).parent.parent.parent.parent / "config" / "claude45-model-settings.yml"
                if claude45_settings.exists():
                    cmd.extend(["--model-settings-file", str(claude45_settings)])
                    self._log(f"Using Claude 4.5 model settings: {claude45_settings}")

        # Use --auto-test if enabled and we have a verify script
        if self.auto_test and self.verify_script and self.verify_script.exists():
            cmd.extend(["--auto-test", "--test-cmd", f"python {self.verify_script}"])

        # Add workspace files to Aider's context
        # Use --read for reference files (TASK.md, task.yaml, etc.)
        # Use --file for source files so Aider can see and edit them
        key_files = self._find_key_files()
        for f in key_files[:8]:
            fname = f.name.lower()
            if fname in ("task.md", "task.yaml", "readme.md"):
                cmd.extend(["--read", str(f)])  # Read-only reference
            elif fname.endswith(".py"):
                cmd.extend(["--file", str(f)])  # Editable source files
            else:
                cmd.extend(["--read", str(f)])  # Other files as read-only

        # Add the prompt via --message
        cmd.extend(["--message", prompt])

        self._log(f"Command: aider --model {self.model} ... (timeout: {timeout:.0f}s)")

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.workspace,
                stdin=subprocess.DEVNULL,  # No stdin for automation
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._get_env(),
                preexec_fn=os.setsid if os.name != 'nt' else None,
            )

            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                returncode = proc.returncode

                # Try to extract cost from Aider output
                # Aider outputs cost info like "Tokens: X sent, Y received. Cost: $0.XX"
                cost_match = re.search(r'Cost:\s*\$?([\d.]+)', stdout or "")
                if cost_match:
                    cost_usd = float(cost_match.group(1))
                    self.total_cost_usd += cost_usd
                    self._log(f"Iteration cost: ${cost_usd:.4f}, Total cost: ${self.total_cost_usd:.4f}")

                self._log(f"Aider exit={returncode}")

                if returncode != 0 and stderr:
                    self._log(f"Stderr: {stderr[:500]}", "ERROR")

                if returncode == 0:
                    return True, "completed"
                else:
                    return False, f"exit_code={returncode}"

            except subprocess.TimeoutExpired:
                self._log(f"TIMEOUT after {timeout:.0f}s - killing process group", "WARN")
                if os.name != 'nt':
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    proc.kill()
                proc.wait()
                return False, "timeout"

        except Exception as e:
            self._log(f"Exception: {str(e)}", "ERROR")
            return False, f"error: {str(e)}"

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for Aider.

        Returns:
            Environment dictionary

        Raises:
            EnvironmentError: If required API key is not set
        """
        from ..exceptions import EnvironmentError

        env = os.environ.copy()

        # Aider needs API keys based on model
        if self.model:
            if "anthropic" in self.model.lower():
                if "ANTHROPIC_API_KEY" not in env:
                    raise EnvironmentError("ANTHROPIC_API_KEY not set")
            elif "openai" in self.model.lower() or "gpt" in self.model.lower():
                if "OPENAI_API_KEY" not in env:
                    raise EnvironmentError("OPENAI_API_KEY not set")

        return env
