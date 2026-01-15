#!/usr/bin/env python3
"""Verification script for HELLO-01.

This script verifies that the submission correctly implements
the Hello World task.

PRIVATE - This file is in the private eval repo and should never
be exposed to harnesses.
"""

import json
import subprocess
import sys
from pathlib import Path

from harness_bench.evaluation import preflight_check, check_syntax


def verify() -> dict:
    """Run verification and return results.

    Returns:
        dict with keys: success, score, message, details
    """
    workspace = Path.cwd()
    target_file = workspace / "src" / "hello.py"

    checkpoints = []

    # Check if file exists
    if not target_file.exists():
        return {
            "success": False,
            "score": 0.0,
            "message": "Target file src/hello.py not found",
            "details": {"checkpoints": checkpoints},
        }

    checkpoints.append({"name": "file_exists", "passed": True})

    # Check syntax
    passed, error = check_syntax(target_file)
    if not passed:
        checkpoints.append({"name": "syntax_valid", "passed": False, "details": {"error": error}})
        return {
            "success": False,
            "score": 0.0,
            "message": f"Syntax error: {error}",
            "details": {"checkpoints": checkpoints},
        }

    checkpoints.append({"name": "syntax_valid", "passed": True})

    # Preflight check
    passed, error = preflight_check(target_file, [], cwd=workspace)
    if not passed:
        checkpoints.append({"name": "preflight", "passed": False, "details": {"stderr": error}})
        return {
            "success": False,
            "score": 0.0,
            "message": f"Script crashed during preflight: {error}",
            "details": {"checkpoints": checkpoints},
        }

    checkpoints.append({"name": "preflight", "passed": True})

    # Run the script
    try:
        result = subprocess.run(
            [sys.executable, str(target_file)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=workspace,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "score": 0.0,
            "message": "Script timed out",
            "details": {"timeout": 10, "checkpoints": checkpoints},
        }
    except Exception as e:
        return {
            "success": False,
            "score": 0.0,
            "message": f"Failed to run script: {e}",
            "details": {"checkpoints": checkpoints},
        }

    # Check output
    expected = "Hello, World!\n"
    actual = result.stdout

    if actual == expected:
        checkpoints.append({"name": "output_correct", "passed": True})
        return {
            "success": True,
            "score": 1.0,
            "message": "Output matches expected",
            "details": {"output": actual, "checkpoints": checkpoints},
        }

    # Partial credit for close matches
    if actual.strip() == expected.strip():
        checkpoints.append({"name": "output_correct", "passed": True, "details": {"whitespace_diff": True}})
        return {
            "success": True,
            "score": 0.9,
            "message": "Output matches (whitespace difference)",
            "details": {"output": actual, "expected": expected, "checkpoints": checkpoints},
        }

    if "hello" in actual.lower() and "world" in actual.lower():
        checkpoints.append({"name": "output_correct", "passed": False, "details": {"partial_match": True}})
        return {
            "success": False,
            "score": 0.5,
            "message": "Contains hello and world but wrong format",
            "details": {"output": actual, "expected": expected, "checkpoints": checkpoints},
        }

    checkpoints.append({"name": "output_correct", "passed": False})
    return {
        "success": False,
        "score": 0.0,
        "message": "Output does not match expected",
        "details": {
            "output": actual,
            "expected": expected,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "checkpoints": checkpoints,
        },
    }


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
