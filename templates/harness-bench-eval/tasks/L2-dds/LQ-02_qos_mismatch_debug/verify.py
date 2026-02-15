#!/usr/bin/env python3
"""Verification script for LQ-02_qos_mismatch_debug.

Model must fix the QoS incompatibility between publisher (BEST_EFFORT)
and subscriber (RELIABLE). The fix is to make reliability compatible.

Test workflow:
- Check syntax and preflight for both files
- Verify reliability QoS is compatible (either both RELIABLE or both BEST_EFFORT)
- Run multiple communication tests to verify data flows

PRIVATE - This file is in the eval repo and should never be in the workspace.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from harness_bench.evaluation import preflight_check, check_syntax, check_dds_shmem


EXPECTED_SAMPLES = 10
NUM_RUNS = 3
TIMEOUT = 15


def check_reliability_compatible(pub_code: str, sub_code: str) -> tuple[bool, str]:
    """Check if reliability QoS is compatible between pub and sub.

    Compatible combinations:
    - Both RELIABLE
    - Both BEST_EFFORT
    - Publisher RELIABLE, Subscriber BEST_EFFORT (works but not ideal)

    Incompatible:
    - Publisher BEST_EFFORT, Subscriber RELIABLE (won't communicate)
    """
    # Look for reliability settings
    pub_reliable = "RELIABLE" in pub_code and "reliability" in pub_code.lower()
    pub_best_effort = "BEST_EFFORT" in pub_code and "reliability" in pub_code.lower()

    sub_reliable = "RELIABLE" in sub_code and "reliability" in sub_code.lower()
    sub_best_effort = "BEST_EFFORT" in sub_code and "reliability" in sub_code.lower()

    # Check for the specific incompatible pattern
    if pub_best_effort and sub_reliable and not pub_reliable:
        return False, "Publisher uses BEST_EFFORT but subscriber requires RELIABLE - they won't match"

    # If both have matching reliability or compatible settings
    if (pub_reliable and sub_reliable) or \
       (pub_best_effort and sub_best_effort) or \
       (pub_reliable and sub_best_effort):
        return True, "Reliability QoS is compatible"

    # Default - let the functional test decide
    return True, "Reliability settings unclear - will verify with functional test"


def run_communication_test(
    publisher_file: Path,
    subscriber_file: Path,
    workspace: Path,
    run_num: int,
) -> tuple[bool, int]:
    """Run a single communication test.

    Returns (passed, samples_received)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "output.jsonl"

        # Start subscriber first
        sub_proc = subprocess.Popen(
            [sys.executable, str(subscriber_file),
             "--count", str(EXPECTED_SAMPLES),
             "--timeout", str(TIMEOUT)],
            stdout=open(output_file, "w"),
            stderr=subprocess.PIPE,
            cwd=workspace,
        )

        # Small delay, then start publisher
        time.sleep(0.5)

        pub_proc = subprocess.Popen(
            [sys.executable, str(publisher_file), "--count", str(EXPECTED_SAMPLES)],
            stderr=subprocess.PIPE,
            cwd=workspace,
        )

        # Wait for both to finish
        try:
            pub_proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            pub_proc.kill()

        try:
            sub_proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            sub_proc.kill()

        # Check results
        if not output_file.exists():
            return False, 0

        with open(output_file) as f:
            lines = f.readlines()

        samples = []
        for line in lines:
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                pass

        passed = len(samples) >= EXPECTED_SAMPLES
        return passed, len(samples)


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

    # Check for required files
    publisher_file = workspace / "publisher.py"
    subscriber_file = workspace / "subscriber.py"

    if not publisher_file.exists():
        results["message"] = "publisher.py not found"
        results["details"]["checkpoints"] = checkpoints
        return results

    if not subscriber_file.exists():
        results["message"] = "subscriber.py not found"
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "files_exist", "passed": True})

    # Check syntax for both files
    for name, filepath in [("publisher", publisher_file), ("subscriber", subscriber_file)]:
        passed, error = check_syntax(filepath)
        if not passed:
            results["message"] = f"Syntax error in {name}.py: {error}"
            checkpoints.append({"name": f"{name}_syntax", "passed": False, "details": {"error": error}})
            results["details"]["checkpoints"] = checkpoints
            return results
        checkpoints.append({"name": f"{name}_syntax", "passed": True})

    # Preflight checks
    passed, error = preflight_check(publisher_file, ["--count", "1"], cwd=workspace)
    if not passed:
        results["message"] = f"publisher.py crashed during preflight: {error}"
        checkpoints.append({"name": "publisher_preflight", "passed": False, "details": {"stderr": error}})
        results["details"]["checkpoints"] = checkpoints
        return results
    checkpoints.append({"name": "publisher_preflight", "passed": True})

    passed, error = preflight_check(subscriber_file, ["--count", "1", "--timeout", "2"], cwd=workspace)
    if not passed:
        results["message"] = f"subscriber.py crashed during preflight: {error}"
        checkpoints.append({"name": "subscriber_preflight", "passed": False, "details": {"stderr": error}})
        results["details"]["checkpoints"] = checkpoints
        return results
    checkpoints.append({"name": "subscriber_preflight", "passed": True})

    # Check for QoS compatibility in code
    with open(publisher_file) as f:
        pub_code = f.read()
    with open(subscriber_file) as f:
        sub_code = f.read()

    qos_compatible, qos_message = check_reliability_compatible(pub_code, sub_code)
    checkpoints.append({
        "name": "qos_compatibility",
        "passed": qos_compatible,
        "details": {"message": qos_message}
    })

    # Run communication tests
    run_results = []
    passed_count = 0

    try:
        for i in range(NUM_RUNS):
            passed, samples = run_communication_test(
                publisher_file, subscriber_file, workspace, i + 1
            )
            run_results.append({
                "run": i + 1,
                "passed": passed,
                "samples": samples
            })
            if passed:
                passed_count += 1

        checkpoints.append({
            "name": "communication_tests",
            "passed": passed_count == NUM_RUNS,
            "details": {
                "passed": passed_count,
                "total": NUM_RUNS,
                "runs": run_results
            }
        })

        # Pass/fail based on all critical checkpoints
        all_critical_passed = all(
            cp.get("passed") for cp in checkpoints
            if cp.get("name") in ["files_exist", "publisher_syntax", "subscriber_syntax",
                                   "publisher_preflight", "subscriber_preflight",
                                   "communication_tests"]
        )

        results["success"] = all_critical_passed and passed_count == NUM_RUNS
        results["score"] = 1.0 if results["success"] else 0.0
        results["message"] = f"QoS compatibility fix: {passed_count}/{NUM_RUNS} communication tests passed"
        results["details"]["passed_runs"] = passed_count
        results["details"]["total_runs"] = NUM_RUNS
        results["details"]["checkpoints"] = checkpoints

    except Exception as e:
        results["message"] = f"Error: {e}"
        results["score"] = 0.0

    return results


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
