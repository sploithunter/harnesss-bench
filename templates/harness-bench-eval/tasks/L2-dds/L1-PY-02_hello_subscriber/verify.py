#!/usr/bin/env python3
"""Verification script for L1-PY-02_hello_subscriber.

This script verifies the task completion by running the generated subscriber
against reference publishers (both DynamicData and IDL approaches).

For foundational tasks, we accept EITHER type approach from the model.
The verification tries DynamicData publisher first, then IDL publisher.

PRIVATE - This file is in the eval repo and should never be in the workspace.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from harness_bench.evaluation import preflight_check, check_syntax


def run_with_publisher(
    subscriber_file: Path,
    publisher_file: Path,
    workspace: Path,
    output_file: str,
    domain: int = 0,  # Match task spec
    expected_count: int = 10,
) -> tuple[int, bool]:
    """Run subscriber with a specific publisher.

    Returns (samples_received, subscriber_ran_ok)
    """
    # Start subscriber first (it needs to be ready to receive)
    sub_proc = subprocess.Popen(
        [sys.executable, str(subscriber_file)],
        stdout=open(output_file, 'w'),
        stderr=subprocess.PIPE,
        text=True,
        cwd=workspace,
    )

    time.sleep(3)  # Wait for subscriber to be ready for DDS discovery

    # Run publisher
    pub_proc = subprocess.run(
        [sys.executable, str(publisher_file),
         "--domain", str(domain), "--count", str(expected_count)],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Wait for subscriber to finish receiving
    time.sleep(3)

    # Terminate subscriber gracefully
    sub_proc.terminate()
    try:
        sub_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        sub_proc.kill()

    # Count samples received
    try:
        with open(output_file) as f:
            samples = [line for line in f if line.strip()]
        return len(samples), True
    except Exception:
        return 0, False


def verify() -> dict:
    """Run verification and return results."""
    workspace = Path.cwd()
    eval_dir = Path(os.environ.get("EVAL_DIR", Path(__file__).parent))

    results = {
        "success": False,
        "score": 0.0,
        "message": "",
        "details": {},
    }

    checkpoints = []

    # Look for subscriber.py (model creates subscriber)
    subscriber_file = workspace / "subscriber.py"
    if not subscriber_file.exists():
        results["message"] = "subscriber.py not found"
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "file_exists", "passed": True})

    # Check syntax
    passed, error = check_syntax(subscriber_file)
    if not passed:
        results["message"] = f"Syntax error: {error}"
        checkpoints.append({"name": "syntax_valid", "passed": False, "details": {"error": error}})
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "syntax_valid", "passed": True})

    # Preflight check - run subscriber briefly to catch early errors
    passed, error = preflight_check(subscriber_file, [], cwd=workspace)
    if not passed:
        results["message"] = f"Subscriber crashed during preflight: {error}"
        checkpoints.append({"name": "preflight", "passed": False, "details": {"stderr": error}})
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "preflight", "passed": True})

    # Reference publishers - try both approaches
    ref_dynamic = eval_dir / "reference" / "publisher_dynamic.py"
    ref_idl = eval_dir / "reference" / "publisher_idl.py"
    expected_count = 10

    # Create temp file for output
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        output_file = f.name

    try:
        samples_received = 0
        publisher_used = None

        # Try DynamicData publisher first
        if ref_dynamic.exists():
            samples_received, ok = run_with_publisher(
                subscriber_file, ref_dynamic, workspace, output_file,
                domain=0, expected_count=expected_count  # Match task spec (domain 0)
            )
            if samples_received > 0:
                publisher_used = "dynamic"

        # If no samples, try IDL publisher
        if samples_received == 0 and ref_idl.exists():
            samples_received, ok = run_with_publisher(
                subscriber_file, ref_idl, workspace, output_file,
                domain=0, expected_count=expected_count  # Match task spec (domain 0)
            )
            if samples_received > 0:
                publisher_used = "idl"

        checkpoints.append({
            "name": "subscriber_runs",
            "passed": samples_received > 0,
            "details": {"publisher_type": publisher_used}
        })

        checkpoints.append({
            "name": "samples_received",
            "passed": samples_received > 0,  # Any samples = subscriber works
            "details": {"received": samples_received, "expected": expected_count}
        })

        # Validate JSONL format if samples received
        if samples_received > 0:
            try:
                with open(output_file) as f:
                    valid_json = 0
                    for line in f:
                        if line.strip():
                            try:
                                data = json.loads(line)
                                # Check for expected fields
                                if "message" in data or "count" in data or "data" in data:
                                    valid_json += 1
                            except json.JSONDecodeError:
                                pass

                    jsonl_valid = valid_json >= samples_received * 0.9
                    checkpoints.append({
                        "name": "jsonl_format",
                        "passed": jsonl_valid,
                        "details": {"valid_lines": valid_json, "total_samples": samples_received}
                    })
            except Exception:
                checkpoints.append({"name": "jsonl_format", "passed": False})

        # Calculate score - pass/fail based on correctness
        all_critical_passed = all(
            cp.get("passed") for cp in checkpoints
            if cp.get("name") in ["file_exists", "syntax_valid", "preflight", "samples_received"]
        )

        results["success"] = all_critical_passed and samples_received > 0  # Any samples = pass
        results["score"] = 1.0 if results["success"] else 0.0
        results["message"] = f"Received {samples_received}/{expected_count} samples"
        if publisher_used:
            results["message"] += f" (using {publisher_used} publisher)"
        results["details"]["samples_received"] = samples_received
        results["details"]["publisher_type"] = publisher_used
        results["details"]["checkpoints"] = checkpoints

    except subprocess.TimeoutExpired:
        results["message"] = "Subscriber timed out"
        results["score"] = 0.0
    except Exception as e:
        results["message"] = f"Error: {e}"
        results["score"] = 0.0
    finally:
        Path(output_file).unlink(missing_ok=True)

    return results


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
