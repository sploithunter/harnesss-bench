#!/usr/bin/env python3
"""Verification script for L1-PY-01_hello_publisher.

This script verifies the task completion by running the generated publisher
against reference subscribers (both DynamicData and IDL approaches).

For foundational tasks, we accept EITHER type approach from the model.
The verification tries DynamicData subscriber first, then IDL subscriber.

PRIVATE - This file is in the eval repo and should never be in the workspace.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from harness_bench.evaluation import preflight_check, check_syntax, check_dds_shmem


def run_with_subscriber(
    publisher_file: Path,
    subscriber_file: Path,
    workspace: Path,
    output_file: str,
    domain: int = 85,
    expected_count: int = 10,
) -> tuple[int, bool]:
    """Run publisher with a specific subscriber.

    Returns (samples_received, publisher_ran_ok)
    """
    # Start subscriber first (needs to be ready)
    sub_proc = subprocess.Popen(
        [sys.executable, str(subscriber_file),
         "--domain", str(domain), "--count", str(expected_count), "--timeout", "30",
         "--output", output_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    time.sleep(3)  # Wait for subscriber to be ready for DDS discovery

    # Run publisher
    pub_proc = subprocess.run(
        [sys.executable, str(publisher_file)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=workspace,
    )

    # Wait for subscriber
    try:
        sub_proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        sub_proc.kill()

    # Count samples received
    try:
        with open(output_file) as f:
            samples = [line for line in f if line.strip()]
        return len(samples), pub_proc.returncode == 0
    except Exception:
        return 0, pub_proc.returncode == 0


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

    # Check DDS shared memory health (auto-cleans orphaned segments)
    shmem = check_dds_shmem()
    if shmem.get("cleanup"):
        results["details"]["dds_shmem_cleanup"] = shmem["cleanup"]
    if not shmem["ok"]:
        results["message"] = shmem["warning"]
        results["details"]["dds_shmem"] = shmem
        checkpoints.append({"name": "dds_shmem", "passed": False, "details": shmem})
        results["details"]["checkpoints"] = checkpoints
        return results

    # Look for publisher.py
    publisher_file = workspace / "publisher.py"
    if not publisher_file.exists():
        results["message"] = "publisher.py not found"
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "file_exists", "passed": True})

    # Check syntax
    passed, error = check_syntax(publisher_file)
    if not passed:
        results["message"] = f"Syntax error: {error}"
        checkpoints.append({"name": "syntax_valid", "passed": False, "details": {"error": error}})
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "syntax_valid", "passed": True})

    # Preflight check - run publisher briefly to catch early errors
    passed, error = preflight_check(publisher_file, [], cwd=workspace)
    if not passed:
        results["message"] = f"Publisher crashed during preflight: {error}"
        checkpoints.append({"name": "preflight", "passed": False, "details": {"stderr": error}})
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "preflight", "passed": True})

    # Reference subscribers - try both approaches
    ref_dynamic = eval_dir / "reference" / "subscriber_dynamic.py"
    ref_idl = eval_dir / "reference" / "subscriber_idl.py"
    expected_output = eval_dir / "expected" / "output.jsonl"
    expected_count = 10  # Expected samples (but any samples = pass for publisher test)

    # Create temp file for output
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        output_file = f.name

    try:
        samples_received = 0
        subscriber_used = None
        publisher_ran = False

        # Try DynamicData subscriber first
        if ref_dynamic.exists():
            samples_received, publisher_ran = run_with_subscriber(
                publisher_file, ref_dynamic, workspace, output_file,
                domain=85, expected_count=expected_count  # Match task spec (domain 85)
            )
            if samples_received > 0:
                subscriber_used = "dynamic"

        # If no samples, try IDL subscriber
        if samples_received == 0 and ref_idl.exists():
            samples_received, publisher_ran = run_with_subscriber(
                publisher_file, ref_idl, workspace, output_file,
                domain=85, expected_count=expected_count  # Match task spec (domain 85)
            )
            if samples_received > 0:
                subscriber_used = "idl"

        checkpoints.append({
            "name": "publisher_runs",
            "passed": publisher_ran,
            "details": {"subscriber_type": subscriber_used}
        })

        checkpoints.append({
            "name": "samples_received",
            "passed": samples_received > 0,  # Any samples = publisher works
            "details": {"received": samples_received, "expected": expected_count}
        })

        # Compare with expected output if available
        if expected_output.exists() and samples_received > 0:
            try:
                with open(expected_output) as f:
                    expected_samples = [json.loads(line) for line in f if line.strip()]

                with open(output_file) as f:
                    actual_samples = [json.loads(line) for line in f if line.strip()]

                matches = 0
                for exp, act in zip(expected_samples, actual_samples):
                    if exp.get("data") == act.get("data"):
                        matches += 1

                match_ratio = matches / len(expected_samples) if expected_samples else 0
                checkpoints.append({
                    "name": "data_correct",
                    "passed": match_ratio >= 0.9,
                    "details": {"match_ratio": match_ratio}
                })
            except Exception:
                pass

        # Calculate score - pass/fail based on correctness
        all_critical_passed = all(
            cp.get("passed") for cp in checkpoints
            if cp.get("name") in ["file_exists", "syntax_valid", "preflight", "samples_received"]
        )

        results["success"] = all_critical_passed and samples_received > 0  # Any samples = pass
        results["score"] = 1.0 if results["success"] else 0.0
        results["message"] = f"Received {samples_received}/{expected_count} samples"
        if subscriber_used:
            results["message"] += f" (using {subscriber_used} subscriber)"
        results["details"]["samples_received"] = samples_received
        results["details"]["subscriber_type"] = subscriber_used
        results["details"]["checkpoints"] = checkpoints

    except subprocess.TimeoutExpired:
        results["message"] = "Publisher timed out"
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
