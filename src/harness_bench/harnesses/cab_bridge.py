"""
Coding Agent Bridge (CAB) Harness - Uses coding-agent-bridge for session management.

This bridge delegates session management to coding-agent-bridge via REST API,
which handles tmux, hooks, and event streaming.
"""

import json
import time
import subprocess
import threading
import websocket
from pathlib import Path
from typing import Any, Callable

import requests

from .ralph_base import RalphLoopBase


class CodingAgentBridge(RalphLoopBase):
    """Harness bridge using coding-agent-bridge for session management.

    Instead of managing tmux sessions directly, this bridge calls the
    coding-agent-bridge REST API which provides:
    - Unified session management for Claude, Codex, etc.
    - Real-time event streaming via WebSocket
    - Standardized hook handling

    Prerequisites:
    - coding-agent-bridge server running (default: http://127.0.0.1:4003)
    - Run: coding-agent-bridge setup && coding-agent-bridge server
    """

    harness_id = "cab"  # Coding Agent Bridge
    harness_vendor = "coding-agent-bridge"
    harness_version = "0.1.0"

    def __init__(
        self,
        workspace: Path,
        agent: str = "claude",
        verify_script: Path | str | None = None,
        model: str | None = None,
        max_iterations: int = 10,
        total_timeout: int = 300,
        stagnation_limit: int = 3,
        verbose: bool = True,
        verify_timeout: int = 300,
        cab_url: str = "http://127.0.0.1:4003",
        on_event: Callable[[dict], None] | None = None,
    ):
        """Initialize CAB bridge.

        Args:
            workspace: Path to task workspace
            agent: Agent to use ('claude' or 'codex')
            verify_script: Path to verify.py
            model: Model to use (passed to agent)
            max_iterations: Max loop iterations
            total_timeout: Total timeout for entire test (seconds)
            stagnation_limit: Stop after N iterations with no file changes
            verbose: Print real-time progress
            verify_timeout: Timeout for verification script (seconds)
            cab_url: URL of coding-agent-bridge server
            on_event: Callback for real-time events
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
        self.agent = agent
        self.cab_url = cab_url.rstrip("/")
        self.on_event = on_event
        self._session_id: str | None = None
        self._ws: websocket.WebSocketApp | None = None
        self._ws_thread: threading.Thread | None = None
        self._events: list[dict] = []
        self._stop_event = threading.Event()

    def _get_env(self) -> dict[str, str]:
        """Get environment for harness. Not used directly since CAB handles this."""
        return {}

    def _check_server(self) -> bool:
        """Check if coding-agent-bridge server is running."""
        try:
            resp = requests.get(f"{self.cab_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def _start_websocket(self) -> None:
        """Start WebSocket connection for real-time events."""
        ws_url = self.cab_url.replace("http://", "ws://").replace("https://", "wss://")

        def on_message(ws, message):
            try:
                data = json.loads(message)
                self._events.append(data)

                # Log events if verbose
                if self.verbose and data.get("type") == "event":
                    event_data = data.get("data", {})
                    event_type = event_data.get("type", "unknown")
                    self._log(f"Event: {event_type}")

                # Call user callback
                if self.on_event:
                    self.on_event(data)

                # Check for completion
                if data.get("type") == "event":
                    event_data = data.get("data", {})
                    if event_data.get("type") in ("stop", "session_end"):
                        self._stop_event.set()

            except Exception as e:
                self._log(f"WebSocket message error: {e}", "WARN")

        def on_error(ws, error):
            self._log(f"WebSocket error: {error}", "WARN")

        def on_close(ws, close_status_code, close_msg):
            self._log("WebSocket closed")

        def on_open(ws):
            self._log("WebSocket connected")

        self._ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )

        self._ws_thread = threading.Thread(target=self._ws.run_forever, daemon=True)
        self._ws_thread.start()

    def _stop_websocket(self) -> None:
        """Stop WebSocket connection."""
        if self._ws:
            self._ws.close()
            self._ws = None

    def _create_session(self, prompt: str) -> str | None:
        """Create a new session via CAB API.

        Returns:
            Session ID if successful, None otherwise
        """
        workspace_abs = self.workspace.resolve()

        payload = {
            "name": workspace_abs.name,
            "cwd": str(workspace_abs),
            "agent": self.agent,
        }

        # Add model if specified
        if self.model:
            payload["model"] = self.model

        try:
            resp = requests.post(
                f"{self.cab_url}/sessions",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            # CAB API may return:
            # - {"ok": true, "session": {"id": "...", ...}} or
            # - {"id": "...", ...} directly
            if "session" in data:
                return data["session"].get("id")
            return data.get("id")
        except Exception as e:
            self._log(f"Failed to create session: {e}", "ERROR")
            return None

    def _send_prompt(self, session_id: str, prompt: str) -> bool:
        """Send prompt to session.

        Returns:
            True if successful
        """
        try:
            resp = requests.post(
                f"{self.cab_url}/sessions/{session_id}/prompt",
                json={"prompt": prompt},
                timeout=30,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            self._log(f"Failed to send prompt: {e}", "ERROR")
            return False

    def _get_session(self, session_id: str) -> dict | None:
        """Get session info."""
        try:
            resp = requests.get(f"{self.cab_url}/sessions/{session_id}", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def _delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        try:
            resp = requests.delete(f"{self.cab_url}/sessions/{session_id}", timeout=30)
            resp.raise_for_status()
            return True
        except Exception as e:
            self._log(f"Failed to delete session: {e}", "WARN")
            return False

    def _run_harness_command(self, prompt: str, timeout: int) -> tuple[bool, str]:
        """Run the harness via coding-agent-bridge.

        Args:
            prompt: The task prompt
            timeout: Timeout in seconds

        Returns:
            Tuple of (success: bool, reason: str)
        """
        # Check server is running
        if not self._check_server():
            self._log("ERROR: coding-agent-bridge server not running", "ERROR")
            self._log(f"Start it with: cd vendor/coding-agent-bridge && node bin/cli.js server", "ERROR")
            raise RuntimeError("coding-agent-bridge server not running")

        # Start WebSocket for event streaming
        self._start_websocket()
        self._stop_event.clear()
        self._events = []

        try:
            # Create session
            self._log(f"Creating {self.agent} session via CAB...")
            session_id = self._create_session(prompt)
            if not session_id:
                return False, "failed_to_create_session"

            self._session_id = session_id
            self._log(f"Session created: {session_id}")

            # Wait for agent TUI to be ready
            # TODO: CAB should provide a readiness signal (e.g., via SessionStart hook)
            self._log("Waiting for agent to start...")
            time.sleep(5)  # Give Claude time to fully initialize

            # Send the prompt
            self._log("Sending prompt...")
            if not self._send_prompt(session_id, prompt):
                return False, "failed_to_send_prompt"

            self._log("Prompt sent, waiting for completion...")

            # Wait for completion or timeout
            start_time = time.time()
            while time.time() - start_time < timeout:
                # Check if stop event received via WebSocket
                if self._stop_event.wait(timeout=2.0):
                    self._log("Stop event received")
                    break

                # Check session status
                session = self._get_session(session_id)
                if session:
                    status = session.get("status")
                    if status == "idle":
                        self._log("Session became idle")
                        break
                    elif status == "offline":
                        self._log("Session went offline", "WARN")
                        break

                # Progress logging
                elapsed = time.time() - start_time
                if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                    self._log(f"Still running... ({elapsed:.0f}s elapsed)")

            elapsed = time.time() - start_time
            timed_out = elapsed >= timeout and not self._stop_event.is_set()

            if timed_out:
                self._log(f"TIMEOUT after {timeout}s", "WARN")

            self._log(f"{'Timed out' if timed_out else 'Completed'} in {elapsed:.1f}s")

            # Save events log
            events_file = self.workspace / f".cab_events_iter{self.iteration}.jsonl"
            with open(events_file, "w") as f:
                for event in self._events:
                    f.write(json.dumps(event) + "\n")
            self._log(f"Saved {len(self._events)} events to {events_file.name}")

            # Capture tmux conversation BEFORE cleanup
            self._capture_conversation(session_id)

            if timed_out:
                return True, "timeout"
            return True, "completed"

        finally:
            # Cleanup
            self._stop_websocket()

            # Delete session
            if self._session_id:
                self._delete_session(self._session_id)
                self._session_id = None

    def _capture_conversation(self, session_id: str) -> None:
        """Capture the full tmux conversation before cleanup."""
        try:
            # Get session info to find tmux session name
            session = self._get_session(session_id)
            if not session:
                self._log("Cannot capture conversation: session not found", "WARN")
                return

            tmux_session = session.get("tmuxSession")
            if not tmux_session:
                self._log("Cannot capture conversation: no tmux session", "WARN")
                return

            # Capture tmux pane content (full scroll history)
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", tmux_session, "-p", "-S", "-10000"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                # Save conversation log
                conv_file = self.workspace / f".cab_conversation_iter{self.iteration}.txt"
                conv_file.write_text(result.stdout)
                self._log(f"Captured conversation: {conv_file.name} ({len(result.stdout)} chars)")

                # Also save as JSONL for consistency
                jsonl_file = self.workspace / f".cab_conversation_iter{self.iteration}.jsonl"
                with open(jsonl_file, "w") as f:
                    f.write(json.dumps({
                        "type": "cab_session",
                        "iteration": self.iteration,
                        "timestamp": time.time(),
                        "tmux_session": tmux_session,
                        "content": result.stdout,
                    }) + "\n")
            else:
                self._log(f"Failed to capture tmux pane: {result.stderr}", "WARN")

        except Exception as e:
            self._log(f"Error capturing conversation: {e}", "WARN")


class ClaudeCabBridge(CodingAgentBridge):
    """Claude Code via coding-agent-bridge."""

    harness_id = "claude-cab"
    harness_vendor = "anthropic"

    def __init__(self, workspace: Path, **kwargs):
        kwargs["agent"] = "claude"
        super().__init__(workspace, **kwargs)


class CodexCabBridge(CodingAgentBridge):
    """OpenAI Codex via coding-agent-bridge."""

    harness_id = "codex-cab"
    harness_vendor = "openai"

    def __init__(self, workspace: Path, **kwargs):
        kwargs["agent"] = "codex"
        super().__init__(workspace, **kwargs)
