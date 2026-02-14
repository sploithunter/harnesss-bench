#!/usr/bin/env python3
"""Verification script for LD-03_rtiddsgen_workflow.

Model creates HelloWorld.idl, publisher.py, and subscriber.py using rtiddsgen.
The code MUST use generated IDL types (not DynamicData).

PRIVATE - This file is in the eval repo and should never be in the workspace.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from harness_bench.evaluation import preflight_check, check_syntax, check_dds_shmem


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

    # Check for HelloWorld.idl
    idl_file = workspace / "HelloWorld.idl"
    if not idl_file.exists():
        results["message"] = "HelloWorld.idl not found"
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "idl_exists", "passed": True})

    # Validate IDL content
    with open(idl_file) as f:
        idl_content = f.read()

    idl_valid = (
        "struct HelloWorld" in idl_content
        and "message" in idl_content
        and "count" in idl_content
    )
    checkpoints.append({
        "name": "idl_valid",
        "passed": idl_valid,
        "details": {"has_struct": "struct HelloWorld" in idl_content}
    })

    if not idl_valid:
        results["message"] = "HelloWorld.idl missing required fields (struct HelloWorld, message, count)"
        results["details"]["checkpoints"] = checkpoints
        return results

    # Run rtiddsgen to generate Python code
    nddshome = os.environ.get("NDDSHOME")
    if not nddshome:
        results["message"] = "NDDSHOME not set - cannot run rtiddsgen"
        checkpoints.append({"name": "rtiddsgen_env", "passed": False})
        results["details"]["checkpoints"] = checkpoints
        return results

    rtiddsgen = Path(nddshome) / "bin" / "rtiddsgen"
    if not rtiddsgen.exists():
        results["message"] = f"rtiddsgen not found at {rtiddsgen}"
        checkpoints.append({"name": "rtiddsgen_exists", "passed": False})
        results["details"]["checkpoints"] = checkpoints
        return results

    # Run rtiddsgen
    proc = subprocess.run(
        [str(rtiddsgen), "-language", "python", "-d", str(workspace), "-replace", str(idl_file)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=workspace,
    )

    generated_file = workspace / "HelloWorld.py"
    rtiddsgen_ok = proc.returncode == 0 and generated_file.exists()
    checkpoints.append({
        "name": "rtiddsgen_runs",
        "passed": rtiddsgen_ok,
        "details": {"stderr": proc.stderr[:500] if proc.stderr else None}
    })

    if not rtiddsgen_ok:
        results["message"] = f"rtiddsgen failed: {proc.stderr}"
        results["details"]["checkpoints"] = checkpoints
        return results

    # Check generated type is importable
    proc = subprocess.run(
        [sys.executable, "-c", "from HelloWorld import HelloWorld; print(HelloWorld)"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=workspace,
    )

    type_importable = proc.returncode == 0
    checkpoints.append({
        "name": "type_importable",
        "passed": type_importable,
        "details": {"stderr": proc.stderr[:200] if proc.stderr else None}
    })

    if not type_importable:
        results["message"] = f"Generated type not importable: {proc.stderr}"
        results["details"]["checkpoints"] = checkpoints
        return results

    # Check publisher.py and subscriber.py exist
    publisher_file = workspace / "publisher.py"
    subscriber_file = workspace / "subscriber.py"

    pub_exists = publisher_file.exists()
    sub_exists = subscriber_file.exists()
    checkpoints.append({
        "name": "pubsub_files",
        "passed": pub_exists and sub_exists,
        "details": {"publisher": pub_exists, "subscriber": sub_exists}
    })

    if not (pub_exists and sub_exists):
        results["message"] = f"Missing files: publisher.py={pub_exists}, subscriber.py={sub_exists}"
        results["details"]["checkpoints"] = checkpoints
        return results

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
    passed, error = preflight_check(publisher_file, [], cwd=workspace)
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

    # Check that code uses generated types (NOT DynamicData)
    uses_generated_types = True
    for name, filepath in [("publisher", publisher_file), ("subscriber", subscriber_file)]:
        with open(filepath) as f:
            code = f.read()

        # Check for DynamicData API usage (not just comments)
        if "dds.DynamicData" in code or "DynamicData.Topic" in code or "DynamicData.DataWriter" in code:
            uses_generated_types = False
            checkpoints.append({
                "name": "uses_generated_types",
                "passed": False,
                "details": {"file": name, "error": "Uses DynamicData API instead of generated types"}
            })
            results["message"] = f"{name}.py uses DynamicData API instead of generated types"
            results["details"]["checkpoints"] = checkpoints
            return results

        # Check for import of generated type
        if "from HelloWorld import HelloWorld" not in code and "from HelloWorld import *" not in code:
            uses_generated_types = False
            checkpoints.append({
                "name": "uses_generated_types",
                "passed": False,
                "details": {"file": name, "error": "Doesn't import generated type"}
            })
            results["message"] = f"{name}.py doesn't import generated type"
            results["details"]["checkpoints"] = checkpoints
            return results

    checkpoints.append({"name": "uses_generated_types", "passed": True})

    # Functional test: run publisher and subscriber together
    try:
        # Start subscriber
        sub_proc = subprocess.Popen(
            [sys.executable, str(subscriber_file), "--count", "10", "--timeout", "30"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=workspace,
        )

        time.sleep(2)  # Wait for subscriber to start

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
            sub_stdout, sub_stderr = sub_proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            sub_proc.kill()
            sub_stdout, sub_stderr = sub_proc.communicate()

        checkpoints.append({
            "name": "publisher_runs",
            "passed": pub_proc.returncode == 0,
            "details": {"stderr": pub_proc.stderr[:500] if pub_proc.stderr else None}
        })

        # Count samples received
        lines = [l for l in sub_stdout.strip().split("\n") if l.startswith("{")]
        samples_received = len(lines)

        checkpoints.append({
            "name": "samples_received",
            "passed": samples_received >= 10,
            "details": {"received": samples_received, "expected": 10}
        })

        # Pass/fail based on all critical checkpoints
        all_critical_passed = all(
            cp.get("passed") for cp in checkpoints
            if cp.get("name") in ["idl_valid", "rtiddsgen_runs", "type_importable",
                                   "pubsub_files", "uses_generated_types", "samples_received"]
        )

        results["success"] = all_critical_passed
        results["score"] = 1.0 if results["success"] else 0.0
        results["message"] = f"Received {samples_received}/10 samples using generated IDL types"
        results["details"]["samples_received"] = samples_received
        results["details"]["checkpoints"] = checkpoints

    except subprocess.TimeoutExpired:
        results["message"] = "Functional test timed out"
        results["score"] = 0.0
    except Exception as e:
        results["message"] = f"Error: {e}"
        results["score"] = 0.0

    return results


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
