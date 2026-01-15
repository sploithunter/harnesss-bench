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
