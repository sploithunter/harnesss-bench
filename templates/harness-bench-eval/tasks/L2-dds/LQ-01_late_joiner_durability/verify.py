#!/usr/bin/env python3
"""Verification script for LQ-01_late_joiner_durability.

Model creates publisher.py and subscriber.py with proper durability QoS
so that late joiners receive historical samples.

Test workflow:
- Run multiple tests with RANDOM startup order
- Publisher starts before subscriber (late joiner case)
- Subscriber starts before publisher (normal case)
- All samples should be received in both cases

PRIVATE - This file is in the eval repo and should never be in the workspace.
"""

import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from harness_bench.evaluation import preflight_check, check_syntax


EXPECTED_SAMPLES = 10
NUM_RUNS = 5
TIMEOUT = 15


def run_single_test(
    publisher_file: Path,
    subscriber_file: Path,
    workspace: Path,
    run_num: int,
    pub_first: bool,
) -> tuple[bool, int]:
    """Run a single test with specified startup order.

    Returns (passed, samples_received)
    """
    delay = random.uniform(0.5, 2.0)  # Random delay between 0.5-2 seconds

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "output.jsonl"

        if pub_first:
            # Publisher starts first (late joiner case)
            pub_proc = subprocess.Popen(
                [sys.executable, str(publisher_file), "--count", str(EXPECTED_SAMPLES)],
                stderr=subprocess.PIPE,
                cwd=workspace,
            )

            # Delay before starting subscriber (simulating late join)
            time.sleep(delay)

            sub_proc = subprocess.Popen(
                [sys.executable, str(subscriber_file),
                 "--count", str(EXPECTED_SAMPLES),
                 "--timeout", str(TIMEOUT)],
                stdout=open(output_file, "w"),
                stderr=subprocess.PIPE,
                cwd=workspace,
            )
        else:
            # Subscriber starts first (normal case)
            sub_proc = subprocess.Popen(
                [sys.executable, str(subscriber_file),
                 "--count", str(EXPECTED_SAMPLES),
                 "--timeout", str(TIMEOUT)],
                stdout=open(output_file, "w"),
                stderr=subprocess.PIPE,
                cwd=workspace,
            )

            # Delay before starting publisher
            time.sleep(delay)

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

    # Check for durability QoS in code
    with open(publisher_file) as f:
        pub_code = f.read()
    with open(subscriber_file) as f:
        sub_code = f.read()

    durability_in_pub = "durability" in pub_code.lower() or "TRANSIENT_LOCAL" in pub_code
    durability_in_sub = "durability" in sub_code.lower() or "TRANSIENT_LOCAL" in sub_code

    checkpoints.append({
        "name": "durability_qos",
        "passed": durability_in_pub and durability_in_sub,
        "details": {"publisher": durability_in_pub, "subscriber": durability_in_sub}
    })

    # Run multiple tests with random startup order
    run_results = []
    passed_count = 0

    try:
        for i in range(NUM_RUNS):
            pub_first = random.choice([True, False])
            passed, samples = run_single_test(
                publisher_file, subscriber_file, workspace, i + 1, pub_first
            )
            run_results.append({
                "run": i + 1,
                "pub_first": pub_first,
                "passed": passed,
                "samples": samples
            })
            if passed:
                passed_count += 1

        checkpoints.append({
            "name": "durability_tests",
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
                                   "durability_tests"]
        )

        results["success"] = all_critical_passed and passed_count == NUM_RUNS
        results["score"] = 1.0 if results["success"] else 0.0
        results["message"] = f"Late joiner durability: {passed_count}/{NUM_RUNS} tests passed"
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
