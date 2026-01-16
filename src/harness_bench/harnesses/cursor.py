"""Cursor IDE and GUI harness bridges.

This module provides bridges for GUI-based AI coding assistants like Cursor,
Windsurf, and other visual IDEs. Since these tools don't have a CLI interface,
we use file system watching to detect changes and commit them automatically.

The bridge monitors a workspace directory for file changes and periodically
commits them following the harness-bench protocol. Completion is signaled
either by creating a `.harness-bench/complete` file or via timeout.

Example:
    from harness_bench.harnesses.cursor import CursorBridge

    bridge = CursorBridge(
        workspace=Path("./workspaces/HELLO-01_cursor_run_abc"),
        commit_interval=10,  # Commit every 10 seconds
    )

    # Start monitoring (blocks until completion)
    success = bridge.run(
        task_id="HELLO-01",
        run_id="run_abc",
        task_name="Hello World",
    )
"""

from __future__ import annotations

import hashlib
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Any

from ..core.bridge import HarnessBridge
from ..core.protocol import CommitAction

# Try to import watchdog for file system monitoring
try:
    from watchdog.observers import Observer
    from watchdog.events import (
        FileSystemEventHandler,
        FileModifiedEvent,
        FileCreatedEvent,
        FileDeletedEvent,
        FileMovedEvent,
    )

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # Stub classes for type hints
    Observer = None
    FileSystemEventHandler = object


class FileChangeHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """Handles file system events for GUI bridges.

    Detects file changes and deduplicates events to avoid
    multiple triggers for the same logical change.
    """

    def __init__(
        self,
        workspace: Path,
        callback: Callable[[Path, str], None],
    ):
        """Initialize the handler.

        Args:
            workspace: Workspace directory to monitor
            callback: Function to call when files change (path, change_type)
        """
        if WATCHDOG_AVAILABLE:
            super().__init__()
        self.workspace = workspace
        self.callback = callback
        self.file_hashes: dict[str, str] = {}
        self._initialize_hashes()

    def _initialize_hashes(self) -> None:
        """Initialize file hashes for change detection."""
        for file in self.workspace.rglob("*"):
            if file.is_file() and not self._should_ignore(file):
                self.file_hashes[str(file)] = self._hash_file(file)

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored."""
        path_str = str(path)
        ignore_patterns = [
            ".git",
            ".harness-bench",
            "__pycache__",
            ".pyc",
            ".pyo",
            ".DS_Store",
            ".swp",
            ".swo",
            "~",
            ".idea",
            ".vscode",
            "node_modules",
            ".env",
            ".venv",
            "venv",
        ]
        return any(pattern in path_str for pattern in ignore_patterns)

    def _hash_file(self, path: Path) -> str:
        """Calculate file hash."""
        try:
            return hashlib.md5(path.read_bytes()).hexdigest()
        except (OSError, IOError):
            return ""

    def _process_event(self, path: Path, event_type: str) -> None:
        """Process a file system event."""
        if self._should_ignore(path):
            return

        # For modifications, check if content actually changed
        if event_type == "modified" and path.is_file():
            new_hash = self._hash_file(path)
            old_hash = self.file_hashes.get(str(path), "")

            if new_hash == old_hash:
                return  # No actual change

            self.file_hashes[str(path)] = new_hash

        # For new files, add to hash tracking
        elif event_type == "created" and path.is_file():
            self.file_hashes[str(path)] = self._hash_file(path)

        # For deleted files, remove from tracking
        elif event_type == "deleted":
            self.file_hashes.pop(str(path), None)

        # Get relative path for callback
        try:
            rel_path = path.relative_to(self.workspace)
            self.callback(rel_path, event_type)
        except ValueError:
            pass  # Path not in workspace

    def on_modified(self, event) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return
        self._process_event(Path(event.src_path), "modified")

    def on_created(self, event) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return
        self._process_event(Path(event.src_path), "created")

    def on_deleted(self, event) -> None:
        """Handle file deletion events."""
        if event.is_directory:
            return
        self._process_event(Path(event.src_path), "deleted")

    def on_moved(self, event) -> None:
        """Handle file move events."""
        if event.is_directory:
            return
        self._process_event(Path(event.src_path), "deleted")
        self._process_event(Path(event.dest_path), "created")


class CursorBridge(HarnessBridge):
    """Bridge for Cursor IDE and similar GUI-based assistants.

    This bridge monitors file system changes rather than controlling
    the harness directly. It's designed for manual intervention scenarios
    where the user operates a GUI-based AI assistant.

    Workflow:
    1. Initialize workspace: `harness-bench task init ... --harness cursor`
    2. Start monitoring: `harness-bench run gui --workspace ...`
    3. User operates Cursor IDE manually
    4. Bridge auto-commits changes periodically
    5. Signal completion via `.harness-bench/complete` file

    Example:
        bridge = CursorBridge(
            workspace=Path("./workspace"),
            commit_interval=10,
            idle_timeout=60,
        )
        success = bridge.run(task_id="HELLO-01", run_id="run_123")
    """

    harness_id = "cursor"
    harness_vendor = "cursor"
    harness_version = "auto-detected"

    def __init__(
        self,
        workspace: Path,
        model: str | None = None,
        commit_interval: int = 10,
        idle_timeout: int = 0,
        manual_completion: bool = True,
        show_banner: bool = True,
    ):
        """Initialize the Cursor bridge.

        Args:
            workspace: Path to task workspace
            model: Optional model identifier
            commit_interval: Seconds between auto-commits (default: 10)
            idle_timeout: Seconds of inactivity before auto-complete (0 = disabled)
            manual_completion: Require manual completion signal (default: True)
            show_banner: Show status banner in terminal (default: True)
        """
        super().__init__(workspace, model)
        self.commit_interval = commit_interval
        self.idle_timeout = idle_timeout
        self.manual_completion = manual_completion
        self.show_banner = show_banner

        self._observer = None
        self._pending_changes: list[tuple[Path, str]] = []
        self._last_activity = time.time()
        self._running = False
        self._lock = threading.Lock()

    def execute_task(self, task_prompt: str) -> bool:
        """Monitor file system for changes.

        This runs until:
        1. Manual completion signal (if manual_completion=True)
        2. Idle timeout exceeded (if idle_timeout > 0)
        3. External termination (Ctrl+C)

        Args:
            task_prompt: Task prompt (displayed to user)

        Returns:
            True if completed successfully, False otherwise
        """
        if not WATCHDOG_AVAILABLE:
            raise RuntimeError(
                "watchdog package required for GUI bridges. "
                "Install with: pip install watchdog"
            )

        self.log_event(
            "gui_bridge_start",
            {
                "commit_interval": self.commit_interval,
                "idle_timeout": self.idle_timeout,
                "manual_completion": self.manual_completion,
            },
        )

        # Setup file watcher
        handler = FileChangeHandler(self.workspace, self._on_file_change)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.workspace), recursive=True)
        self._observer.start()
        self._running = True

        if self.show_banner:
            self._print_banner()

        try:
            while self._running:
                # Check for manual completion signal
                completion_file = self.workspace / ".harness-bench" / "complete"
                if completion_file.exists():
                    content = completion_file.read_text().strip().lower()
                    success = content in ("success", "true", "1", "yes", "")
                    completion_file.unlink()
                    self._commit_pending_changes()
                    return success

                # Commit pending changes periodically
                with self._lock:
                    should_commit = (
                        self._pending_changes
                        and time.time() - self._last_activity >= self.commit_interval
                    )

                if should_commit:
                    self._commit_pending_changes()

                # Check for idle timeout (non-manual mode)
                if not self.manual_completion and self.idle_timeout > 0:
                    with self._lock:
                        idle_time = time.time() - self._last_activity
                        no_pending = not self._pending_changes

                    if idle_time > self.idle_timeout and no_pending:
                        if self.show_banner:
                            print("\nIdle timeout reached, completing...")
                        return True

                time.sleep(1)

        except KeyboardInterrupt:
            if self.show_banner:
                print("\n\nInterrupted by user")
            self._commit_pending_changes()
            return len(self._pending_changes) == 0

        finally:
            self._running = False
            if self._observer:
                self._observer.stop()
                self._observer.join()

            # Commit any remaining changes
            self._commit_pending_changes()

        return True

    def _print_banner(self) -> None:
        """Print status banner to terminal."""
        print(f"\n{'=' * 60}")
        print("GUI Bridge Active (Cursor)")
        print(f"{'=' * 60}")
        print(f"Workspace: {self.workspace}")
        print(f"Commit interval: {self.commit_interval}s")
        if self.idle_timeout:
            print(f"Idle timeout: {self.idle_timeout}s")
        print(f"\nMonitoring for file changes...")
        print(f"\nTo complete:")
        print(f"  - Create .harness-bench/complete with 'success' or 'failure'")
        print(f"  - Or press Ctrl+C")
        print(f"{'=' * 60}\n")

    def _on_file_change(self, path: Path, change_type: str) -> None:
        """Handle detected file change."""
        with self._lock:
            self._pending_changes.append((path, change_type))
            self._last_activity = time.time()

        self.log_event(
            "file_change_detected",
            {
                "path": str(path),
                "type": change_type,
            },
        )

        if self.show_banner:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"  [{timestamp}] [{change_type}] {path}")

    def _commit_pending_changes(self) -> None:
        """Commit accumulated changes."""
        with self._lock:
            if not self._pending_changes:
                return
            changes = self._pending_changes.copy()
            self._pending_changes.clear()

        # Group changes for commit message
        created = [str(p) for p, t in changes if t == "created"]
        modified = [str(p) for p, t in changes if t == "modified"]
        deleted = [str(p) for p, t in changes if t == "deleted"]

        # Create meaningful commit message
        parts = []
        if created:
            parts.append(f"add {len(created)} file(s)")
        if modified:
            parts.append(f"modify {len(modified)} file(s)")
        if deleted:
            parts.append(f"delete {len(deleted)} file(s)")

        description = ", ".join(parts) if parts else "changes"

        # Build body with file list
        body_parts = []
        if created:
            body_parts.append("Added:")
            body_parts.extend(f"  + {f}" for f in created[:10])
            if len(created) > 10:
                body_parts.append(f"  ... and {len(created) - 10} more")
        if modified:
            body_parts.append("Modified:")
            body_parts.extend(f"  * {f}" for f in modified[:10])
            if len(modified) > 10:
                body_parts.append(f"  ... and {len(modified) - 10} more")
        if deleted:
            body_parts.append("Deleted:")
            body_parts.extend(f"  - {f}" for f in deleted[:10])
            if len(deleted) > 10:
                body_parts.append(f"  ... and {len(deleted) - 10} more")

        body = "\n".join(body_parts) if body_parts else None

        try:
            self.commit_edit(description, body)
            if self.show_banner:
                print(f"  [committed] {description}")
        except Exception as e:
            if self.show_banner:
                print(f"  [error] Failed to commit: {e}")

    def stop(self) -> None:
        """Stop the file watcher and complete."""
        self._running = False


class GenericGUIBridge(CursorBridge):
    """Generic bridge for any GUI-based coding assistant.

    Use this when a specific bridge doesn't exist for your tool.

    Example:
        bridge = GenericGUIBridge(
            workspace=Path("./workspace"),
            harness_name="windsurf",
        )
    """

    harness_id = "generic-gui"
    harness_vendor = "unknown"

    def __init__(
        self,
        workspace: Path,
        harness_name: str = "unknown",
        **kwargs,
    ):
        """Initialize generic GUI bridge.

        Args:
            workspace: Path to task workspace
            harness_name: Name of the harness being used
            **kwargs: Additional arguments passed to CursorBridge
        """
        super().__init__(workspace, **kwargs)
        self.harness_id = f"gui/{harness_name}"
        self.harness_vendor = harness_name


class PollingBridge(HarnessBridge):
    """Fallback bridge using polling instead of watchdog.

    Use this when watchdog is not available or doesn't work
    with your file system.
    """

    harness_id = "polling-gui"
    harness_vendor = "harness-bench"

    def __init__(
        self,
        workspace: Path,
        model: str | None = None,
        poll_interval: int = 5,
        commit_interval: int = 10,
        idle_timeout: int = 0,
        manual_completion: bool = True,
    ):
        """Initialize polling bridge.

        Args:
            workspace: Path to task workspace
            model: Optional model identifier
            poll_interval: Seconds between file system polls
            commit_interval: Seconds between auto-commits
            idle_timeout: Seconds of inactivity before auto-complete (0 = disabled)
            manual_completion: Require manual completion signal
        """
        super().__init__(workspace, model)
        self.poll_interval = poll_interval
        self.commit_interval = commit_interval
        self.idle_timeout = idle_timeout
        self.manual_completion = manual_completion

        self._file_states: dict[str, tuple[float, int]] = {}
        self._pending_changes: list[tuple[Path, str]] = []
        self._last_activity = time.time()
        self._last_commit = time.time()

    def execute_task(self, task_prompt: str) -> bool:
        """Monitor file system using polling."""
        self._initialize_file_states()

        print(f"\n{'=' * 60}")
        print("GUI Bridge Active (Polling)")
        print(f"{'=' * 60}")
        print(f"Workspace: {self.workspace}")
        print(f"Poll interval: {self.poll_interval}s")
        print(f"Commit interval: {self.commit_interval}s")
        print(f"\nTo complete: Create .harness-bench/complete")
        print(f"{'=' * 60}\n")

        try:
            while True:
                # Check for completion signal
                completion_file = self.workspace / ".harness-bench" / "complete"
                if completion_file.exists():
                    content = completion_file.read_text().strip().lower()
                    success = content in ("success", "true", "1", "yes", "")
                    completion_file.unlink()
                    self._commit_pending_changes()
                    return success

                # Poll for changes
                self._poll_changes()

                # Commit if needed
                if time.time() - self._last_commit >= self.commit_interval:
                    self._commit_pending_changes()
                    self._last_commit = time.time()

                # Check idle timeout
                if not self.manual_completion and self.idle_timeout > 0:
                    if (
                        time.time() - self._last_activity > self.idle_timeout
                        and not self._pending_changes
                    ):
                        print("\nIdle timeout reached")
                        return True

                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            self._commit_pending_changes()
            return True

    def _initialize_file_states(self) -> None:
        """Initialize file state tracking."""
        for file in self.workspace.rglob("*"):
            if file.is_file() and not self._should_ignore(file):
                stat = file.stat()
                self._file_states[str(file)] = (stat.st_mtime, stat.st_size)

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored."""
        path_str = str(path)
        ignore = [".git", ".harness-bench", "__pycache__", ".pyc", ".DS_Store"]
        return any(p in path_str for p in ignore)

    def _poll_changes(self) -> None:
        """Poll for file changes."""
        current_files: dict[str, tuple[float, int]] = {}

        for file in self.workspace.rglob("*"):
            if file.is_file() and not self._should_ignore(file):
                try:
                    stat = file.stat()
                    current_files[str(file)] = (stat.st_mtime, stat.st_size)
                except OSError:
                    pass

        # Detect changes
        for path_str, state in current_files.items():
            if path_str not in self._file_states:
                # New file
                rel_path = Path(path_str).relative_to(self.workspace)
                self._pending_changes.append((rel_path, "created"))
                self._last_activity = time.time()
                print(f"  [created] {rel_path}")
            elif self._file_states[path_str] != state:
                # Modified file
                rel_path = Path(path_str).relative_to(self.workspace)
                self._pending_changes.append((rel_path, "modified"))
                self._last_activity = time.time()
                print(f"  [modified] {rel_path}")

        # Detect deletions
        for path_str in self._file_states:
            if path_str not in current_files:
                rel_path = Path(path_str).relative_to(self.workspace)
                self._pending_changes.append((rel_path, "deleted"))
                self._last_activity = time.time()
                print(f"  [deleted] {rel_path}")

        self._file_states = current_files

    def _commit_pending_changes(self) -> None:
        """Commit accumulated changes."""
        if not self._pending_changes:
            return

        changes = self._pending_changes.copy()
        self._pending_changes.clear()

        files_changed = [str(p) for p, _ in changes]
        description = (
            f"Edit {files_changed[0]}"
            if len(files_changed) == 1
            else f"Edit {len(files_changed)} files"
        )

        try:
            self.commit_edit(description)
            print(f"  [committed] {description}")
        except Exception as e:
            print(f"  [error] Failed to commit: {e}")


def create_gui_bridge(
    workspace: Path,
    harness_name: str = "cursor",
    **kwargs,
) -> HarnessBridge:
    """Factory function to create an appropriate GUI bridge.

    Args:
        workspace: Path to task workspace
        harness_name: Name of the GUI harness
        **kwargs: Additional arguments for the bridge

    Returns:
        Appropriate bridge instance
    """
    harness_lower = harness_name.lower()

    if harness_lower == "cursor":
        return CursorBridge(workspace, **kwargs)
    elif WATCHDOG_AVAILABLE:
        return GenericGUIBridge(workspace, harness_name=harness_name, **kwargs)
    else:
        return PollingBridge(workspace, **kwargs)


class CursorRalphLoopBridge(HarnessBridge):
    """Ralph Wiggum-style while loop bridge for Cursor Agent CLI.

    Uses cursor-agent CLI (released August 2025) for headless automation.
    Semi-dumb loop that tracks state in files/git, not LLM context.
    Each iteration gets fresh context but can see prior work via files.

    Key features:
    - No session continuation: Fresh context each iteration
    - State in files: progress.txt, .ralph_status.json
    - Circuit breaker: Stops on stagnation (no file changes)
    - Simple feedback: Dumps error output for next iteration
    - TOTAL timeout for entire test, not per iteration

    Usage:
        bridge = CursorRalphLoopBridge(workspace, verify_script="verify.py")
        success = bridge.execute_task(task_prompt)
    """

    harness_id = "cursor"
    harness_vendor = "cursor"
    harness_version = "1.0.0"

    # Model name mapping: our names -> Cursor CLI model strings
    # Available: opus-4.5, sonnet-4.5, sonnet-4.5-thinking, gpt-5.2, gpt-5.2-codex, etc.
    MODEL_MAP = {
        # Claude models
        "anthropic/claude-opus-4-5-20251101": "opus-4.5",
        "claude-opus-4-5-20251101": "opus-4.5",
        "claude-opus-4-5": "opus-4.5",
        "anthropic/claude-sonnet-4-5-20250929": "sonnet-4.5",
        "claude-sonnet-4-5-20250929": "sonnet-4.5",
        "claude-sonnet-4-5": "sonnet-4.5",
        "anthropic/claude-haiku-4-5-20251001": "sonnet-4.5",  # No haiku, use sonnet
        "claude-haiku-4-5-20251001": "sonnet-4.5",
        "claude-haiku-4-5": "sonnet-4.5",
        # OpenAI models
        "openai/gpt-5.2": "gpt-5.2",
        "gpt-5.2": "gpt-5.2",
        "openai/gpt-5.2-codex": "gpt-5.2-codex",
        "gpt-5.2-codex": "gpt-5.2-codex",
        # Google models
        "gemini-3-pro": "gemini-3-pro",
        "gemini-3-flash": "gemini-3-flash",
        "openrouter/google/gemini-3-pro-preview": "gemini-3-pro",
        # xAI models
        "grok": "grok",
        "grok-4": "grok",
        "openrouter/x-ai/grok-4": "grok",
        # Cursor's own model
        "composer": "composer-1",
    }

    # MCP server for DDS assistance (requires VPN)
    MCP_SERVER_URL = "https://sandbox-chatbot.rti.com/mcp"
    MCP_SERVER_NAME = "ConnextAI"

    def __init__(
        self,
        workspace: Path,
        verify_script: Path | str | None = None,
        model: str | None = "claude-4-sonnet",
        max_iterations: int = 10,
        total_timeout: int = 300,
        stagnation_limit: int = 3,
        verbose: bool = True,
        verify_timeout: int = 300,
        enable_mcp: bool = False,
    ):
        """Initialize Cursor Ralph loop bridge.

        Args:
            workspace: Path to task workspace
            verify_script: Path to verify.py
            model: Model to use (mapped to Cursor model names)
            max_iterations: Max loop iterations
            total_timeout: TOTAL timeout for entire test (seconds)
            stagnation_limit: Stop after N iterations with no file changes
            verbose: Print real-time progress to stdout
            verify_timeout: Timeout for verification script (seconds)
            enable_mcp: Enable MCP tools (ConnextAI for DDS help)
        """
        super().__init__(workspace, model)
        self.verify_script = Path(verify_script).resolve() if verify_script else None
        self.max_iterations = max_iterations
        self.total_timeout = total_timeout
        self.stagnation_limit = stagnation_limit
        self.verify_timeout = verify_timeout
        self.verbose = verbose
        self.enable_mcp = enable_mcp
        self.iteration = 0
        self.stagnation_count = 0
        self.last_file_hash = ""
        self._start_time = None
        self.total_cost_usd = 0.0
        self._progress_log: list[str] = []
        self._mcp_available = False

        # Map model name to Cursor's model string
        self.cursor_model = self._map_model(model)

    def _map_model(self, model: str | None) -> str:
        """Map model name to Cursor CLI model string."""
        if not model:
            return "sonnet-4.5"

        # Check direct mapping
        if model in self.MODEL_MAP:
            return self.MODEL_MAP[model]

        # Check if it's already a Cursor model name
        cursor_models = {"opus-4.5", "sonnet-4.5", "sonnet-4.5-thinking", "gpt-5.2",
                        "gpt-5.2-codex", "composer-1", "auto"}
        if model in cursor_models:
            return model

        # Fallback: try to infer from model name
        model_lower = model.lower()
        if "opus" in model_lower:
            return "opus-4.5"
        elif "sonnet" in model_lower or "claude" in model_lower or "haiku" in model_lower:
            return "sonnet-4.5"
        elif "codex" in model_lower:
            return "gpt-5.2-codex"
        elif "gpt" in model_lower:
            return "gpt-5.2"

        # Default
        return "sonnet-4.5"

    def _check_mcp_available(self) -> bool:
        """Check if ConnextAI MCP server is accessible (requires VPN).

        Returns:
            True if MCP server is reachable, False otherwise.
        """
        import subprocess

        try:
            # Quick connectivity check with 3 second timeout
            result = subprocess.run(
                [
                    "curl", "-s", "--connect-timeout", "3",
                    "-X", "POST",
                    "-H", "Content-Type: application/json",
                    "-H", "Accept: application/json",
                    "-d", '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"harness-bench","version":"1.0"}}}',
                    self.MCP_SERVER_URL,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and "protocolVersion" in result.stdout:
                return True
            return False

        except Exception:
            return False

    def _log(self, message: str, level: str = "INFO") -> None:
        """Log message to stdout and progress log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}"
        if self.verbose:
            print(log_line, flush=True)
        # Also append to a detailed log file
        log_file = self.workspace / ".cursor_ralph_log.txt"
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
        import json
        import os
        import subprocess

        self._start_time = time.time()

        # Initialize state files
        self._init_state_files()
        self._log(f"Cursor Ralph loop started: max_iterations={self.max_iterations}, total_timeout={self.total_timeout}s")
        self._log(f"Workspace: {self.workspace}")
        self._log(f"Verify script: {self.verify_script}")
        self._log(f"Model: {self.model} -> Cursor model: {self.cursor_model}")

        # Check MCP availability (requires VPN)
        if self.enable_mcp:
            self._mcp_available = self._check_mcp_available()
            if self._mcp_available:
                self._log(f"MCP server ({self.MCP_SERVER_NAME}) is available - DDS assistance enabled")
            else:
                self._log(f"MCP server ({self.MCP_SERVER_NAME}) not reachable - VPN may be required. Proceeding without DDS assistance.", "WARN")

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
            self.log_event("cursor_ralph_iteration_start", {
                "iteration": self.iteration,
                "stagnation_count": self.stagnation_count,
                "time_remaining": remaining,
            })

            # Build prompt with progress context embedded
            self._log("Building prompt...")
            prompt = self._build_ralph_prompt(task_prompt)
            self._log(f"Prompt length: {len(prompt)} chars")

            # Run Cursor with remaining time as timeout
            self._log(f"Running Cursor Agent (timeout: {remaining:.0f}s)...")
            cursor_start = time.time()
            cursor_success, cursor_reason = self._run_cursor(prompt, timeout=remaining)
            cursor_elapsed = time.time() - cursor_start
            self._log(f"Cursor finished: {cursor_reason}, elapsed={cursor_elapsed:.1f}s")

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
                    self.log_event("cursor_ralph_circuit_breaker", {
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
                    self.log_event("cursor_ralph_success", {"iteration": self.iteration})
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
        self._log(f"Cursor Ralph loop finished: iterations={self.iteration}, total_time={total_elapsed:.1f}s", "WARN")
        self.log_event("cursor_ralph_max_iterations", {"iterations": self.iteration})
        return False

    def _init_state_files(self) -> None:
        """Initialize Ralph state files."""
        import json

        progress_file = self.workspace / "progress.txt"
        if not progress_file.exists():
            progress_file.write_text("# Cursor Ralph Loop Progress\n\n")

        status_file = self.workspace / ".ralph_status.json"
        if not status_file.exists():
            status_file.write_text(json.dumps({
                "iteration": 0,
                "status": "running",
                "last_verification": None,
            }, indent=2))

    def _build_ralph_prompt(self, original_prompt: str) -> str:
        """Build prompt with progress context embedded.

        CRITICAL: We pre-include TASK.md content because Cursor Agent CLI
        doesn't automatically read it before generating code.
        """
        parts = []

        # Pre-include TASK.md content to ensure the LLM sees requirements first
        task_md = self.workspace / "TASK.md"
        if task_md.exists():
            parts.append("# TASK.md - READ CAREFULLY BEFORE WRITING CODE\n")
            parts.append(task_md.read_text())
            parts.append("\n---\n\n")

        parts.append(original_prompt)

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

    def _run_cursor(self, prompt: str, timeout: float | None = None) -> tuple[bool, str]:
        """Run Cursor Agent CLI (fresh context each time).

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds

        Returns:
            Tuple of (success: bool, reason: str)
        """
        import json
        import os
        import signal
        import subprocess

        cmd = [
            "cursor-agent",
            "-p",  # Print mode (non-interactive)
            "--force",  # Auto-approve file modifications
            "--output-format", "json",
            "--workspace", str(self.workspace),
            "--model", self.cursor_model,
        ]

        # Enable MCP tools if available (auto-approve for headless mode)
        if self.enable_mcp and self._mcp_available:
            cmd.append("--approve-mcps")

        cmd.append(prompt)

        effective_timeout = timeout if timeout else self.total_timeout
        mcp_flag = " --approve-mcps" if (self.enable_mcp and self._mcp_available) else ""
        self._log(f"Command: cursor-agent -p --force{mcp_flag} --model {self.cursor_model} --workspace {self.workspace} ... (timeout: {effective_timeout:.0f}s)")

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

                # Save full output to conversation log file
                conversation_log_file = self.workspace / f".cursor_conversation_iter{self.iteration}.json"
                with open(conversation_log_file, 'w') as log_f:
                    log_f.write(stdout if stdout else "")
                self._log(f"Conversation log saved to: {conversation_log_file.name}")

                # Try to extract stats from Cursor JSON output
                if stdout:
                    try:
                        output = json.loads(stdout)
                        stats = output.get("stats", {})
                        lines_created = stats.get("lines_created", 0)
                        lines_read = stats.get("lines_read", 0)
                        duration_ms = stats.get("duration_ms", 0)
                        self._log(f"Cursor stats: lines_created={lines_created}, lines_read={lines_read}, duration_ms={duration_ms}")

                        # Estimate cost (rough estimate based on lines)
                        estimated_tokens = (lines_read * 50) + (lines_created * 100)
                        if "opus" in self.cursor_model:
                            cost_per_1k = 0.015
                        elif "sonnet" in self.cursor_model:
                            cost_per_1k = 0.003
                        elif "haiku" in self.cursor_model:
                            cost_per_1k = 0.00025
                        elif "gpt" in self.cursor_model:
                            cost_per_1k = 0.002
                        else:
                            cost_per_1k = 0.003

                        iteration_cost = (estimated_tokens / 1000) * cost_per_1k
                        self.total_cost_usd += iteration_cost
                    except json.JSONDecodeError:
                        pass

                self._log(f"Cursor exit={returncode}, estimated_cost=${self.total_cost_usd:.4f}")

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
            self._log("Cursor Agent CLI not found. Install with: curl https://cursor.com/install -fsSL | bash", "ERROR")
            return False, "cursor_not_found"
        except Exception as e:
            self._log(f"Exception: {str(e)}", "ERROR")
            return False, f"error: {str(e)}"

    def _commit_if_changed(self) -> bool:
        """Commit if there are changes. Returns True if files changed."""
        import subprocess

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
                        ["git", "commit", "-m", f"[cursor-ralph] Iteration {self.iteration}"],
                        cwd=self.workspace,
                        capture_output=True,
                    )
                    return True
            return False
        except Exception:
            return False

    def _run_verification(self) -> dict[str, Any]:
        """Run verification script."""
        import json
        import subprocess

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
        """Get environment variables for Cursor."""
        import os

        env = os.environ.copy()

        # Ensure cursor-agent is in PATH
        home = os.path.expanduser("~")
        local_bin = os.path.join(home, ".local", "bin")
        if local_bin not in env.get("PATH", ""):
            env["PATH"] = local_bin + ":" + env.get("PATH", "")

        if "CURSOR_API_KEY" not in env:
            raise ValueError("CURSOR_API_KEY not set. Get one from https://cursor.com/settings")

        return env
