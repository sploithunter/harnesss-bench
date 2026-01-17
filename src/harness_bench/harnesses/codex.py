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
from .ralph_base import RalphLoopBase


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


class CodexRalphLoopBridge(RalphLoopBase):
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
        self.sandbox_mode = sandbox_mode

    def _run_harness_command(self, prompt: str, timeout: float) -> tuple[bool, str]:
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

        self._log(f"Command: codex exec -m {self.model} -C {self.workspace} ... (timeout: {timeout:.0f}s)")

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
                stdout, stderr = proc.communicate(timeout=timeout)
                returncode = proc.returncode

                # Save full JSONL output to conversation log file
                conversation_log_file = self.workspace / f".codex_conversation_iter{self.iteration}.jsonl"
                with open(conversation_log_file, 'w') as log_f:
                    log_f.write(stdout if stdout else "")
                self._log(f"Conversation log saved to: {conversation_log_file.name}")

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

        except FileNotFoundError:
            self._log("Codex CLI not found. Install with: npm install -g @openai/codex", "ERROR")
            return False, "codex_not_found"
        except Exception as e:
            self._log(f"Exception: {str(e)}", "ERROR")
            return False, f"error: {str(e)}"

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for Codex.

        Returns:
            Environment dictionary

        Raises:
            EnvironmentError: If OPENAI_API_KEY is not set
        """
        from ..exceptions import EnvironmentError

        env = os.environ.copy()

        if "OPENAI_API_KEY" not in env:
            raise EnvironmentError("OPENAI_API_KEY not set")

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
