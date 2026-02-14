"""Preflight checks for verification scripts.

Quick execution checks to catch runtime errors early before running full tests.
This gives models clear error feedback without confusing logic-based errors.
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional


def preflight_check(
    script: Path,
    args: list[str],
    timeout: float = 3.0,
    early_crash_window: float = 1.5,
    cwd: Optional[Path] = None,
) -> tuple[bool, Optional[str]]:
    """Run a script briefly to catch runtime errors early.

    The goal is to catch early errors (imports, argparse, initialization)
    while ignoring late errors (cleanup, logic in main loop).

    Args:
        script: Path to the Python script to check
        args: Command line arguments to pass
        timeout: Max seconds to wait (default 3)
        early_crash_window: Only report crashes within this time window (default 1.5s)
        cwd: Working directory (default: script's parent)

    Returns:
        (passed, error_message) - passed is True if no crash detected,
        error_message contains stderr if crashed early
    """
    if cwd is None:
        cwd = script.parent

    import time
    start_time = time.time()

    try:
        proc = subprocess.Popen(
            [sys.executable, str(script)] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            elapsed = time.time() - start_time
        except subprocess.TimeoutExpired:
            # Process ran until timeout - it's probably fine
            proc.terminate()
            try:
                proc.communicate(timeout=1)
            except:
                proc.kill()
            return True, None

        stderr_str = stderr.decode() if stderr else ""

        # Only care about crashes that happen quickly (early errors)
        # Late crashes (cleanup, logic) are caught by the full test
        if elapsed > early_crash_window:
            return True, None

        # Check for crash indicators
        crashed = proc.returncode != 0 and (
            "Traceback" in stderr_str or
            "error:" in stderr_str.lower() or
            "Error:" in stderr_str
        )

        if crashed:
            return False, stderr_str[:1500]

        return True, None

    except Exception as e:
        return False, f"Preflight error: {e}"


def preflight_scripts(
    scripts: list[tuple[str, Path, list[str]]],
    cwd: Optional[Path] = None,
    timeout: float = 3.0,
) -> list[dict]:
    """Run preflight checks on multiple scripts.

    Args:
        scripts: List of (name, script_path, args) tuples
        cwd: Working directory for all scripts
        timeout: Max seconds per script

    Returns:
        List of checkpoint dicts with name, passed, and details
    """
    checkpoints = []

    for name, script, args in scripts:
        passed, error = preflight_check(script, args, timeout=timeout, cwd=cwd)

        checkpoint = {
            "name": f"{name}_preflight",
            "passed": passed,
        }

        if not passed and error:
            checkpoint["details"] = {"stderr": error}

        checkpoints.append(checkpoint)

    return checkpoints


def _count_shmem_segments() -> tuple[int, list[tuple[str, str]]]:
    """Count System V shared memory segments and return (count, [(shmid, cpid), ...]).

    Returns:
        Tuple of (segment_count, list of (shmid, creator_pid) tuples).
    """
    try:
        # Use ipcs -a for full details including CPID (creator PID)
        proc = subprocess.run(
            ["ipcs", "-a"], capture_output=True, text=True, timeout=5,
        )
        segments = []
        in_shm_section = False
        for line in proc.stdout.strip().splitlines():
            stripped = line.strip()
            if "Shared Memory:" in stripped:
                in_shm_section = True
                continue
            if in_shm_section and stripped.startswith(("Semaphores:", "Message Queues:")):
                in_shm_section = False
                continue
            if in_shm_section and stripped.startswith("m "):
                # macOS format: m <shmid> <key> <mode> <owner> <group> <creator> <cgroup> <nattch> <segsz> <cpid> <lpid> ...
                parts = stripped.split()
                if len(parts) >= 11:
                    shmid, cpid = parts[1], parts[10]
                    segments.append((shmid, cpid))
        return len(segments), segments
    except Exception:
        return 0, []


def cleanup_dds_shmem() -> dict:
    """Kill orphaned DDS processes and remove their shared memory segments.

    RTI Connext DDS uses System V shared memory for its shmem transport.
    On macOS, orphaned segments accumulate across runs and are never released
    automatically. This function:

    1. Kills orphaned DDS-related processes (rtiddsspy, etc.)
    2. Removes shared memory segments whose creator process is dead

    Returns:
        Dict with cleanup results including segments before/after and actions taken.
    """
    import os
    import signal
    import time

    result = {
        "segments_before": 0,
        "segments_after": 0,
        "processes_killed": [],
        "segments_removed": 0,
        "segments_failed": 0,
        "errors": [],
    }

    count_before, segments = _count_shmem_segments()
    result["segments_before"] = count_before

    if count_before == 0:
        return result

    # Step 1: Kill orphaned DDS processes (rtiddsspy, etc.)
    dds_process_names = {"rtiddsspy", "rtiddsping", "rtimonitor", "rtiroutingservice"}
    try:
        ps_proc = subprocess.run(
            ["ps", "-eo", "pid,comm"], capture_output=True, text=True, timeout=5,
        )
        for line in ps_proc.stdout.strip().splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                pid_str, comm = parts
                comm_base = os.path.basename(comm)
                if comm_base in dds_process_names:
                    try:
                        pid = int(pid_str)
                        os.kill(pid, signal.SIGTERM)
                        result["processes_killed"].append({"pid": pid, "name": comm_base})
                    except (ValueError, OSError):
                        pass
    except Exception as e:
        result["errors"].append(f"Process scan failed: {e}")

    # Give killed processes a moment to release segments
    if result["processes_killed"]:
        time.sleep(1.0)

    # Step 2: Remove segments whose creator PID is dead
    _, segments = _count_shmem_segments()  # Re-scan after kills
    for shmid, cpid in segments:
        try:
            pid = int(cpid)
            # Check if creator process is alive
            try:
                os.kill(pid, 0)  # signal 0 = check existence
                continue  # Process alive, skip this segment
            except OSError:
                pass  # Process dead, try to remove segment

            rm_proc = subprocess.run(
                ["ipcrm", "-m", shmid],
                capture_output=True, text=True, timeout=5,
            )
            if rm_proc.returncode == 0:
                result["segments_removed"] += 1
            else:
                result["segments_failed"] += 1
        except (ValueError, Exception):
            result["segments_failed"] += 1

    # Final count
    count_after, _ = _count_shmem_segments()
    result["segments_after"] = count_after

    return result


def check_dds_shmem(warn_threshold: int = 60, auto_cleanup: bool = True) -> dict:
    """Check System V shared memory segment count for DDS health.

    RTI Connext DDS uses System V shared memory for its shmem transport.
    On macOS, orphaned segments accumulate across runs and are never released
    automatically. When the system limit is reached, DDS cannot create new
    participants and all DDS operations silently fail (ENOSPC).

    When auto_cleanup is True and the threshold is exceeded, this function
    will attempt to clean up by killing orphaned DDS processes and removing
    segments whose creator processes are dead.

    Args:
        warn_threshold: Number of segments above which to warn/clean (default 60).
            macOS default kern.sysv.shmmni is typically 64-128.
        auto_cleanup: If True, attempt cleanup when threshold is exceeded.

    Returns:
        Dict with keys:
          - ok: bool — True if segment count is below threshold (after cleanup)
          - segment_count: int — current number of shared memory segments
          - warning: str | None — warning message if count is still high
          - cleanup: dict | None — cleanup results if cleanup was attempted
    """
    import platform

    result = {"ok": True, "segment_count": 0, "warning": None, "cleanup": None}

    count, _ = _count_shmem_segments()
    result["segment_count"] = count

    if count < warn_threshold:
        return result

    # Threshold exceeded — attempt cleanup if enabled
    if auto_cleanup:
        cleanup_result = cleanup_dds_shmem()
        result["cleanup"] = cleanup_result
        result["segment_count"] = cleanup_result["segments_after"]
        count = cleanup_result["segments_after"]

    if count >= warn_threshold:
        result["ok"] = False
        is_mac = platform.system() == "Darwin"
        reboot_note = " A reboot may be required to clear them on macOS." if is_mac else ""
        cleanup_note = ""
        if result["cleanup"]:
            cr = result["cleanup"]
            cleanup_note = (
                f"\nCleanup attempted: killed {len(cr['processes_killed'])} DDS processes, "
                f"removed {cr['segments_removed']} segments, "
                f"{cr['segments_failed']} could not be removed."
            )
        result["warning"] = (
            f"*** DDS SHARED MEMORY EXHAUSTION ***\n"
            f"System has {count} shared memory segments (threshold: {warn_threshold}).\n"
            f"DDS shmem transport will fail with ENOSPC.{reboot_note}"
            f"{cleanup_note}\n"
            f"DDS verification results are UNRELIABLE until this is resolved."
        )
    else:
        # Cleanup worked!
        if result["cleanup"]:
            cr = result["cleanup"]
            result["warning"] = (
                f"DDS shmem cleanup succeeded: {cr['segments_before']} -> {cr['segments_after']} segments "
                f"(killed {len(cr['processes_killed'])} processes, removed {cr['segments_removed']} segments)."
            )

    return result


def check_syntax(script: Path) -> tuple[bool, Optional[str]]:
    """Check Python syntax without executing.

    Args:
        script: Path to Python script

    Returns:
        (passed, error_message)
    """
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(script)],
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        return False, proc.stderr

    return True, None
