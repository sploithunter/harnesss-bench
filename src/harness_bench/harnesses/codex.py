"""OpenAI Codex bridge implementation.

OpenAI Codex CLI is OpenAI's terminal-based coding assistant.
This bridge integrates it with the Harness Bench protocol.

Usage:
    bridge = CodexBridge(workspace, model="gpt-4")
    success = bridge.run(task_id="L1-PY-01", run_id="run_abc123")

    # Subscription mode (no API key, uses tmux + session file monitoring):
    bridge = CodexSubscriptionBridge(workspace, model="gpt-5.3-codex")
    success = bridge.run(task_id="metr-hello_world-1", run_id="run_abc123")
"""

from __future__ import annotations

import json
import os
import shlex
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

                # Store response for result tracking
                self._last_harness_response = stdout or ""

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


class CodexSubscriptionBridge(RalphLoopBase):
    """Codex bridge using subscription mode (no API key required).

    Uses tmux to run Codex CLI interactively with a Codex Pro subscription.
    Completion detection uses Codex session file monitoring (~/.codex/sessions/)
    since Codex has no hook system (unlike Claude Code).

    Session files are JSONL with structured events:
    - session_meta: session start with cwd, model info
    - event_msg with payload.type: user_message, agent_reasoning, agent_message, token_count
    - Completion = agent_message event followed by idle period (no new tool events)

    Key differences from CodexRalphLoopBridge:
    - Uses interactive Codex (no exec mode)
    - Runs via tmux session
    - Monitors ~/.codex/sessions/ JSONL for completion
    - Works with Codex subscription instead of API key
    - Captures session JSONL + tmux pane output

    Usage:
        bridge = CodexSubscriptionBridge(workspace, model="gpt-5.3-codex")
        success = bridge.run(task_id="metr-hello_world-1", run_id="run_abc123")
    """

    harness_id = "codex-subscription"
    harness_vendor = "openai"
    harness_version = "1.0.0"

    # OpenAI pricing per million tokens (estimates for subscription models)
    OPENAI_PRICING = {
        # Model: (input_per_mtok, output_per_mtok)
        "gpt-5.3-codex": (2.00, 8.00),
        "gpt-5.2-codex": (2.00, 8.00),
        "gpt-5.2": (2.00, 8.00),
        "o3": (10.00, 40.00),
        "o3-mini": (1.10, 4.40),
        "o4-mini": (1.10, 4.40),
    }

    def __init__(
        self,
        workspace: Path,
        verify_script: Path | str | None = None,
        model: str | None = "gpt-5.3-codex",
        max_iterations: int = 10,
        total_timeout: int = 300,
        stagnation_limit: int = 3,
        verbose: bool = True,
        verify_timeout: int = 300,
        task_id: str | None = None,
        idle_threshold: float = 5.0,
    ):
        """Initialize Codex subscription bridge.

        Args:
            workspace: Path to task workspace
            verify_script: Path to verify.py
            model: Codex model (e.g., 'gpt-5.3-codex')
            max_iterations: Max loop iterations
            total_timeout: TOTAL timeout for entire test (seconds)
            stagnation_limit: Stop after N iterations with no file changes
            verbose: Print real-time progress to stdout
            verify_timeout: Timeout for verification script (seconds)
            task_id: Task identifier for logging
            idle_threshold: Seconds of inactivity after agent_message to consider complete
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
        self._tmux_session: str | None = None
        self._task_id = task_id
        self._idle_threshold = idle_threshold
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0

    @property
    def log_filename(self) -> str:
        """Return the log filename for Codex subscription."""
        return ".codex_subscription_log.txt"

    def _generate_session_id(self) -> str:
        """Generate a unique tmux session ID."""
        import uuid
        return f"codex-bench-{uuid.uuid4().hex[:8]}"

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

    def _send_prompt_to_tmux(self, session_id: str, prompt: str) -> None:
        """Send prompt via load-buffer + paste-buffer (safe for large/complex text).

        Args:
            session_id: tmux session name
            prompt: Text to send
        """
        import secrets

        temp_file = Path(f"/tmp/codex-bench-prompt-{int(time.time())}-{secrets.token_hex(8)}.txt")
        temp_file.write_text(prompt)

        try:
            subprocess.run(
                ["tmux", "load-buffer", str(temp_file)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["tmux", "paste-buffer", "-t", session_id],
                check=True,
                capture_output=True,
            )
            time.sleep(0.1)
            subprocess.run(
                ["tmux", "send-keys", "-t", session_id, "Enter"],
                check=True,
                capture_output=True,
            )
        finally:
            try:
                temp_file.unlink()
            except Exception:
                pass

    def _find_codex_session_file(self, workspace: Path, start_time: float) -> Path | None:
        """Find the Codex session JSONL file for this run.

        Scans ~/.codex/sessions/YYYY/MM/DD/ for files created after start_time
        whose session_meta.cwd matches our workspace.

        Args:
            workspace: The workspace path to match
            start_time: Unix timestamp - only consider files created after this

        Returns:
            Path to session file, or None if not found
        """
        import datetime as dt

        codex_sessions_dir = Path.home() / ".codex" / "sessions"
        if not codex_sessions_dir.exists():
            self._log(f"Codex sessions dir not found: {codex_sessions_dir}", "WARN")
            return None

        workspace_str = str(workspace.resolve())

        # Check today's directory and yesterday's (in case of midnight rollover)
        now = dt.datetime.now()
        date_dirs = [
            codex_sessions_dir / now.strftime("%Y/%m/%d"),
            codex_sessions_dir / (now - dt.timedelta(days=1)).strftime("%Y/%m/%d"),
        ]

        candidates = []
        for date_dir in date_dirs:
            if not date_dir.exists():
                continue
            for session_file in date_dir.glob("rollout-*.jsonl"):
                try:
                    mtime = session_file.stat().st_mtime
                    if mtime < start_time:
                        continue
                    # Check if this session's cwd matches our workspace
                    # Session meta has cwd at payload.cwd
                    with open(session_file) as f:
                        first_line = f.readline()
                        if first_line:
                            meta = json.loads(first_line)
                            if meta.get("type") == "session_meta":
                                payload = meta.get("payload", {})
                                cwd = payload.get("cwd", "")
                                if cwd == workspace_str:
                                    candidates.append((mtime, session_file))
                except (json.JSONDecodeError, OSError):
                    continue

        if not candidates:
            return None

        # Return the most recently modified matching file
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _monitor_session_completion(
        self, session_file: Path, timeout: float, tmux_session_id: str | None = None,
    ) -> bool:
        """Monitor session JSONL for completion.

        Watches for agent_message events. Returns True when Codex finishes
        responding (agent_message followed by idle period with no new tool events).
        Also checks if tmux session ended (codex exec auto-exits).

        Args:
            session_file: Path to the Codex session JSONL file
            timeout: Maximum time to wait in seconds
            tmux_session_id: Optional tmux session to check for exit

        Returns:
            True if completion detected, False if timeout
        """
        start = time.time()
        last_size = 0
        last_agent_msg_time: float | None = None

        while time.time() - start < timeout:
            # Check if process in tmux pane has exited (codex exec auto-exits when done)
            # With remain-on-exit, session persists but pane_dead becomes 1
            if tmux_session_id:
                pane_check = subprocess.run(
                    ["tmux", "display-message", "-t", tmux_session_id, "-p", "#{pane_dead}"],
                    capture_output=True,
                    text=True,
                )
                if pane_check.stdout.strip() == "1":
                    self._log("Codex exec process exited (pane dead)")
                    return True
            try:
                current_size = session_file.stat().st_size
            except OSError:
                time.sleep(1.0)
                continue

            if current_size > last_size:
                # Read new lines from where we left off
                try:
                    with open(session_file) as f:
                        f.seek(last_size)
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                event = json.loads(line)
                                event_type = event.get("type")
                                payload_type = event.get("payload", {}).get("type")

                                # agent_message signals Codex has finished responding
                                if event_type == "event_msg" and payload_type == "agent_message":
                                    last_agent_msg_time = time.time()
                                # Tool calls (function_call) and reasoning mean still working
                                elif event_type == "response_item" and payload_type in ("function_call", "reasoning"):
                                    last_agent_msg_time = None
                                elif event_type == "event_msg" and payload_type == "user_message":
                                    # New user message would reset (shouldn't happen in single-prompt mode)
                                    last_agent_msg_time = None
                            except json.JSONDecodeError:
                                continue
                except OSError:
                    pass
                last_size = current_size

            # If we saw agent_message and no new activity for idle_threshold
            if last_agent_msg_time and (time.time() - last_agent_msg_time > self._idle_threshold):
                return True

            time.sleep(1.0)

        return False  # timeout

    def _extract_cost_from_session(self, session_file: Path) -> float:
        """Extract cost from token_count events in session JSONL.

        Parses the last token_count event for total_token_usage.
        Uses OpenAI pricing for the model.

        Args:
            session_file: Path to session JSONL

        Returns:
            Estimated cost in USD
        """
        if not session_file or not session_file.exists():
            return 0.0

        final_usage = None
        try:
            with open(session_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        if event.get("type") == "event_msg":
                            payload = event.get("payload", {})
                            if payload.get("type") == "token_count":
                                info = payload.get("info") or {}
                                usage = info.get("total_token_usage")
                                if usage:
                                    final_usage = usage
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return 0.0

        if not final_usage:
            self._log("No token_count events found in session file")
            return 0.0

        input_tokens = final_usage.get("input_tokens", 0)
        output_tokens = final_usage.get("output_tokens", 0)
        cached_input = final_usage.get("cached_input_tokens", 0)
        reasoning_output = final_usage.get("reasoning_output_tokens", 0)

        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

        # Get pricing for model
        model_key = self.model or "gpt-5.3-codex"
        pricing = self.OPENAI_PRICING.get(model_key)
        if not pricing:
            for key in self.OPENAI_PRICING:
                if key in model_key or model_key in key:
                    pricing = self.OPENAI_PRICING[key]
                    break
        if not pricing:
            pricing = (2.00, 8.00)  # Default estimate

        input_per_mtok, output_per_mtok = pricing
        input_cost = (input_tokens / 1_000_000) * input_per_mtok
        output_cost = (output_tokens / 1_000_000) * output_per_mtok
        total_cost = input_cost + output_cost

        self._log(f"Token usage: input={input_tokens}, output={output_tokens}, "
                 f"cached={cached_input}, reasoning={reasoning_output}")
        self._log(f"Estimated cost: ${total_cost:.4f} (model={model_key})")

        return total_cost

    def _run_harness_command(self, prompt: str, timeout: float) -> tuple[bool, str]:
        """Run Codex via tmux with subscription (no API key required).

        Uses `codex exec` (non-interactive mode) inside tmux for output capture.
        Codex exec reads the prompt, executes the task, and exits automatically.
        Session file monitoring provides completion detection + token tracking.

        Flow:
        1. Create tmux session in workspace directory
        2. Start Codex exec: codex exec --dangerously-bypass-approvals-and-sandbox -m {model}
        3. Find session file in ~/.codex/sessions/
        4. Monitor session file for completion (agent_message + idle)
        5. Capture tmux pane output + copy session JSONL
        6. Extract cost from token_count events
        7. Kill tmux session

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds

        Returns:
            Tuple of (success: bool, reason: str)
        """
        if not self._check_tmux_available():
            self._log("ERROR: tmux is required for subscription mode but not found", "ERROR")
            self._log("Install tmux: brew install tmux (macOS) or apt install tmux (Linux)", "ERROR")
            raise RuntimeError("tmux is required for CodexSubscriptionBridge but was not found")

        workspace_abs = self.workspace.resolve()
        session_id = self._generate_session_id()
        self._tmux_session = session_id
        run_start_time = time.time()

        # Create tmux session in workspace directory
        # Set remain-on-exit so pane stays after codex exec finishes (for output capture)
        try:
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_id, "-c", str(workspace_abs)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["tmux", "set-option", "-t", session_id, "remain-on-exit", "on"],
                capture_output=True,
            )
            self._log(f"Created tmux session: {session_id}")
        except subprocess.CalledProcessError as e:
            self._log(f"Failed to create tmux session: {e}", "ERROR")
            return False, f"tmux_create_failed: {e}"

        # Save prompt to temp file for reliable delivery via stdin
        prompt_file = workspace_abs / ".harness_prompt.txt"
        prompt_file.write_text(prompt)

        # Create conversation log file
        conversation_log = workspace_abs / f".codex_conversation_iter{self.iteration}.txt"

        try:
            # Step 1: Build codex exec command
            # Use exec mode (non-interactive) - reads prompt from stdin, auto-exits when done
            codex_args = [
                "codex", "exec",
                "--dangerously-bypass-approvals-and-sandbox",  # Full automation
            ]
            if self.model:
                codex_args.extend(["-m", self.model])

            # Use runner script to avoid tmux line buffer issues
            prompt_file_abs = prompt_file.resolve()
            full_cmd = shlex.join(codex_args) + f" < {shlex.quote(str(prompt_file_abs))}"
            runner_script = workspace_abs / ".harness_runner.sh"
            runner_script.write_text(f"#!/bin/bash\n{full_cmd}\n")
            runner_script.chmod(0o755)
            runner_script_abs = runner_script.resolve()
            self._log(f"Starting Codex: {shlex.join(codex_args)} (timeout: {timeout:.0f}s)")

            subprocess.run(
                ["tmux", "send-keys", "-t", session_id, str(runner_script_abs), "Enter"],
                check=True,
                capture_output=True,
            )
            self._log("Started Codex with prompt")

            # Step 2: Wait for session file to appear
            session_file = None
            session_wait_start = time.time()
            SESSION_FILE_TIMEOUT = 30.0  # Allow 30s for Codex to start and create session

            while time.time() - session_wait_start < SESSION_FILE_TIMEOUT:
                session_file = self._find_codex_session_file(workspace_abs, run_start_time)
                if session_file:
                    self._log(f"Found session file: {session_file.name}")
                    break
                time.sleep(2.0)

            if not session_file:
                self._log("No session file found - falling back to tmux polling", "WARN")
                # Fallback: poll tmux session existence with timeout
                while time.time() - run_start_time < timeout:
                    result = subprocess.run(
                        ["tmux", "has-session", "-t", session_id],
                        capture_output=True,
                    )
                    if result.returncode != 0:
                        self._log("tmux session ended (no session file found)")
                        break
                    time.sleep(5.0)
            else:
                # Step 3: Monitor session file for completion
                # Also checks if tmux session ended (codex exec auto-exits)
                remaining = timeout - (time.time() - run_start_time)
                if remaining > 0:
                    completed = self._monitor_session_completion(
                        session_file, remaining, tmux_session_id=session_id,
                    )
                    if completed:
                        self._log("Completion detected via session/tmux monitoring")
                    else:
                        self._log("Session monitoring timed out", "WARN")

            elapsed = time.time() - run_start_time
            timed_out = elapsed >= timeout

            # Brief wait for final output to flush before capturing
            time.sleep(1.0)

            # Step 4: Capture final pane output (may fail if tmux session already closed)
            pane_output = ""
            try:
                capture_result = subprocess.run(
                    ["tmux", "capture-pane", "-t", session_id, "-p", "-S", "-10000"],
                    capture_output=True,
                    text=True,
                )
                pane_output = capture_result.stdout
                if capture_result.returncode != 0:
                    self._log(f"tmux capture-pane returned {capture_result.returncode} (session may have ended)", "WARN")
                conversation_log.write_text(pane_output)
                self._log(f"Conversation log saved: {conversation_log.name} ({len(pane_output)} chars)")

                # Also save structured JSONL
                jsonl_log = workspace_abs / f".codex_conversation_iter{self.iteration}.jsonl"
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

                self._last_harness_response = pane_output

            except Exception as e:
                self._log(f"Failed to capture pane: {e}", "WARN")

            # Step 5: Copy session JSONL and extract cost
            iteration_cost = 0.0
            if session_file and session_file.exists():
                try:
                    import shutil
                    dest = workspace_abs / f".codex_session_iter{self.iteration}.jsonl"
                    shutil.copy2(session_file, dest)
                    self._log(f"Copied session file: {dest.name}")
                except Exception as e:
                    self._log(f"Failed to copy session file: {e}", "WARN")

                iteration_cost = self._extract_cost_from_session(session_file)
                self.total_cost_usd += iteration_cost

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
            # Send exit command to Codex
            try:
                subprocess.run(
                    ["tmux", "send-keys", "-t", session_id, "C-c", ""],
                    capture_output=True,
                )
                time.sleep(1.0)
            except Exception:
                pass

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
            for temp_file in [prompt_file]:
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception:
                    pass

    def _get_env(self) -> dict[str, str]:
        """Get environment variables.

        No API key needed for subscription mode.
        """
        return os.environ.copy()
