#!/usr/bin/env python3
"""Verification script for LD-01_content_filtered_topic.

Model creates a subscriber using ContentFilteredTopic.
We test it with reference publishers (both DynamicData and IDL).

The filter should be: "id > 50 AND value > 75.0"
Publisher sends 1000 samples (100 sensors x 10 readings each)
Subscriber should receive only ~125 matching samples

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
    domain: int = 0,
    timeout: float = 30.0,
) -> tuple[int, list[dict]]:
    """Run subscriber with a specific publisher.

    Returns (samples_received, samples_data)
    """
    # Start subscriber first
    sub_proc = subprocess.Popen(
        [sys.executable, str(subscriber_file)],
        stdout=open(output_file, 'w'),
        stderr=subprocess.PIPE,
        text=True,
        cwd=workspace,
    )

    time.sleep(2)  # Wait for subscriber to start

    # Run publisher (sends 1000 samples)
    pub_proc = subprocess.run(
        [sys.executable, str(publisher_file), "--domain", str(domain)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Wait for subscriber to process
    time.sleep(5)

    # Terminate subscriber
    sub_proc.terminate()
    try:
        sub_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        sub_proc.kill()

    # Read samples
    samples = []
    try:
        with open(output_file) as f:
            for line in f:
                if line.strip():
                    try:
                        samples.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        pass

    return len(samples), samples


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

    # Model creates subscriber.py
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

    # Preflight check
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

    # Create temp file for output
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        output_file = f.name

    try:
        samples_received = 0
        samples_data = []
        publisher_used = None

        # Try DynamicData publisher first
        if ref_dynamic.exists():
            samples_received, samples_data = run_with_publisher(
                subscriber_file, ref_dynamic, workspace, output_file,
                domain=0  # Match starter publisher.py
            )
            if samples_received > 0:
                publisher_used = "dynamic"

        # If no samples, try IDL publisher
        if samples_received == 0 and ref_idl.exists():
            samples_received, samples_data = run_with_publisher(
                subscriber_file, ref_idl, workspace, output_file,
                domain=0  # Match starter publisher.py
            )
            if samples_received > 0:
                publisher_used = "idl"

        checkpoints.append({
            "name": "subscriber_runs",
            "passed": samples_received > 0,
            "details": {"publisher_type": publisher_used}
        })

        # Expected: ~125 samples out of 1000 (filter: id > 50 AND value > 75.0)
        min_expected = 50  # Very lenient minimum
        max_expected = 500  # Should NOT receive all 1000

        filter_working = min_expected <= samples_received <= max_expected
        checkpoints.append({
            "name": "filter_applied",
            "passed": filter_working,
            "details": {
                "received": samples_received,
                "expected_range": f"{min_expected}-{max_expected}",
                "total_published": 1000
            }
        })

        # Verify filter criteria on received samples
        if samples_data:
            violations = 0
            for sample in samples_data:
                data = sample.get("data", sample)
                sensor_id = data.get("id", data.get("sensor_id", 0))
                value = data.get("value", 0)

                # Check filter: id > 50 AND value > 75.0
                if sensor_id <= 50 or value <= 75.0:
                    violations += 1

            filter_correct = violations == 0
            checkpoints.append({
                "name": "filter_correct",
                "passed": filter_correct,
                "details": {
                    "violations": violations,
                    "samples_checked": len(samples_data)
                }
            })

        # Pass/fail based on correctness
        all_critical_passed = all(
            cp.get("passed") for cp in checkpoints
            if cp.get("name") in ["file_exists", "syntax_valid", "preflight", "filter_applied"]
        )

        results["success"] = all_critical_passed and filter_working
        results["score"] = 1.0 if results["success"] else 0.0
        results["message"] = f"Received {samples_received} samples (filter working: {filter_working})"
        if publisher_used:
            results["message"] += f" using {publisher_used} publisher"
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
