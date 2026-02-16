#!/usr/bin/env python3
"""
Proof of Concept: CAB WebSocket Stability Issues

This script demonstrates WebSocket connection stability problems observed
when using coding-agent-bridge for automated testing.

Issues observed:
1. WebSocket disconnects mid-session with error: "fin=1 opcode=8 data=b''"
2. Sessions go "offline" prematurely (~50s) before task completion
3. Session not found (404) when attempting cleanup after disconnect

To reproduce:
1. Start CAB server: cd vendor/coding-agent-bridge && node bin/cli.js server
2. Run this script: python scripts/cab_websocket_stability_test.py

Environment:
- coding-agent-bridge server running on localhost:4003
- Multiple sessions may accumulate over time (check with /sessions endpoint)
"""

import json
import time
import threading
import requests
import websocket

CAB_URL = "http://127.0.0.1:4003"
WS_URL = "ws://127.0.0.1:4003"


def check_server():
    """Check if CAB server is running."""
    try:
        resp = requests.get(f"{CAB_URL}/health", timeout=5)
        data = resp.json()
        print(f"Server status: {data.get('status')}")
        print(f"Sessions: {data.get('sessions', 0)}")
        return True
    except Exception as e:
        print(f"Server not running: {e}")
        return False


def get_session_stats():
    """Get session statistics."""
    try:
        resp = requests.get(f"{CAB_URL}/sessions", timeout=10)
        sessions = resp.json()
        if isinstance(sessions, dict):
            sessions = sessions.get("sessions", [])

        stats = {}
        for s in sessions:
            status = s.get("status", "unknown")
            stats[status] = stats.get(status, 0) + 1

        return len(sessions), stats
    except Exception as e:
        return 0, {"error": str(e)}


def create_session(name: str, cwd: str = "/tmp") -> dict | None:
    """Create a new CAB session."""
    try:
        resp = requests.post(
            f"{CAB_URL}/sessions",
            json={"name": name, "cwd": cwd, "agent": "claude"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        # Handle both response formats
        if "session" in data:
            return data["session"]
        return data
    except Exception as e:
        print(f"Failed to create session: {e}")
        return None


def delete_session(session_id: str) -> bool:
    """Delete a session."""
    try:
        resp = requests.delete(f"{CAB_URL}/sessions/{session_id}", timeout=30)
        resp.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        print(f"Delete failed (HTTP {e.response.status_code}): {e}")
        return False
    except Exception as e:
        print(f"Delete failed: {e}")
        return False


class WebSocketMonitor:
    """Monitor WebSocket connection stability."""

    def __init__(self):
        self.events = []
        self.errors = []
        self.connected = False
        self.disconnected_at = None
        self.disconnect_reason = None

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            event_type = data.get("type", "unknown")
            self.events.append({
                "time": time.time(),
                "type": event_type,
            })
        except Exception as e:
            self.errors.append(f"Message parse error: {e}")

    def on_error(self, ws, error):
        self.errors.append(str(error))
        self.disconnect_reason = f"error: {error}"

    def on_close(self, ws, close_status_code, close_msg):
        self.disconnected_at = time.time()
        self.disconnect_reason = f"close: status={close_status_code}, msg={close_msg}"
        self.connected = False

    def on_open(self, ws):
        self.connected = True


def test_websocket_stability(duration: int = 60):
    """Test WebSocket connection stability over time."""
    print(f"\n=== WebSocket Stability Test ({duration}s) ===")

    monitor = WebSocketMonitor()

    ws = websocket.WebSocketApp(
        WS_URL,
        on_message=monitor.on_message,
        on_error=monitor.on_error,
        on_close=monitor.on_close,
        on_open=monitor.on_open,
    )

    ws_thread = threading.Thread(target=ws.run_forever, daemon=True)
    ws_thread.start()

    start_time = time.time()

    # Wait for connection
    time.sleep(1)
    if not monitor.connected:
        print("Failed to connect to WebSocket")
        return

    print(f"WebSocket connected")

    # Monitor for duration
    while time.time() - start_time < duration:
        if not monitor.connected:
            elapsed = time.time() - start_time
            print(f"WebSocket disconnected after {elapsed:.1f}s")
            print(f"Reason: {monitor.disconnect_reason}")
            break
        time.sleep(1)

    ws.close()

    # Report
    print(f"\nResults:")
    print(f"  Duration: {time.time() - start_time:.1f}s")
    print(f"  Events received: {len(monitor.events)}")
    print(f"  Errors: {len(monitor.errors)}")
    if monitor.errors:
        for err in monitor.errors[:5]:
            print(f"    - {err}")
    print(f"  Final state: {'connected' if monitor.connected else 'disconnected'}")
    if monitor.disconnect_reason:
        print(f"  Disconnect reason: {monitor.disconnect_reason}")


def test_session_lifecycle():
    """Test session creation, monitoring, and cleanup."""
    print("\n=== Session Lifecycle Test ===")

    # Create session
    session = create_session("stability-test")
    if not session:
        print("Failed to create session")
        return

    session_id = session.get("id")
    print(f"Created session: {session_id}")
    print(f"Initial status: {session.get('status')}")

    # Monitor session status
    start_time = time.time()
    last_status = session.get("status")

    for i in range(30):  # Check for 30 seconds
        time.sleep(1)
        try:
            resp = requests.get(f"{CAB_URL}/sessions/{session_id}", timeout=5)
            if resp.status_code == 404:
                print(f"Session disappeared after {time.time() - start_time:.1f}s")
                return

            data = resp.json()
            status = data.get("status")
            if status != last_status:
                print(f"Status changed: {last_status} -> {status} at {time.time() - start_time:.1f}s")
                last_status = status

            if status == "offline":
                print(f"Session went offline after {time.time() - start_time:.1f}s")
                break
        except Exception as e:
            print(f"Error checking session: {e}")
            break

    # Cleanup
    print(f"\nAttempting cleanup...")
    if delete_session(session_id):
        print("Session deleted successfully")
    else:
        print("Session deletion failed")


def main():
    print("CAB WebSocket Stability Test")
    print("=" * 50)

    if not check_server():
        print("\nPlease start the CAB server first:")
        print("  cd vendor/coding-agent-bridge && node bin/cli.js server")
        return

    total, stats = get_session_stats()
    print(f"\nCurrent sessions: {total}")
    for status, count in stats.items():
        print(f"  {status}: {count}")

    if stats.get("offline", 0) > 10:
        print(f"\nWARNING: {stats['offline']} offline sessions detected")
        print("This may cause stability issues. Consider cleaning up.")

    # Run tests
    test_session_lifecycle()
    test_websocket_stability(duration=30)

    print("\n" + "=" * 50)
    print("Test complete. Check results above for stability issues.")


if __name__ == "__main__":
    main()
