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
