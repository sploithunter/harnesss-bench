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
