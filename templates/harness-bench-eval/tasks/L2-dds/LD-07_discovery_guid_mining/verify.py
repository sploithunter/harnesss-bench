#!/usr/bin/env python3
"""Verification script for LD-07_discovery_guid_mining.

Model creates:
- subscriber_gets_pub_guid.py (Task A): Subscriber extracts publisher's GUID
- publisher_gets_sub_guids.py (Task B): Publisher extracts subscribers' GUIDs

PRIVATE - This file is in the eval repo and should never be in the workspace.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from harness_bench.evaluation import preflight_check, check_syntax


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

    # Task A: subscriber_gets_pub_guid.py
    task_a_file = workspace / "subscriber_gets_pub_guid.py"
    if not task_a_file.exists():
        results["message"] = "subscriber_gets_pub_guid.py not found"
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "task_a_exists", "passed": True})

    # Check Task A syntax
    passed, error = check_syntax(task_a_file)
    if not passed:
        results["message"] = f"Syntax error in subscriber_gets_pub_guid.py: {error}"
        checkpoints.append({"name": "task_a_syntax", "passed": False, "details": {"error": error}})
        results["details"]["checkpoints"] = checkpoints
        return results
    checkpoints.append({"name": "task_a_syntax", "passed": True})

    # Preflight Task A
    passed, error = preflight_check(task_a_file, ["--count", "1", "--timeout", "2"], cwd=workspace)
    if not passed:
        results["message"] = f"subscriber_gets_pub_guid.py crashed during preflight: {error}"
        checkpoints.append({"name": "task_a_preflight", "passed": False, "details": {"stderr": error}})
        results["details"]["checkpoints"] = checkpoints
        return results
    checkpoints.append({"name": "task_a_preflight", "passed": True})

    # Check Task A contains required API elements
    with open(task_a_file) as f:
        task_a_code = f.read()

    required_a = ["publication_handle", "matched_publication_data"]
    missing_a = [req for req in required_a if req not in task_a_code]
    checkpoints.append({
        "name": "task_a_apis",
        "passed": len(missing_a) == 0,
        "details": {"missing": missing_a if missing_a else None}
    })

    # Task B: publisher_gets_sub_guids.py
    task_b_file = workspace / "publisher_gets_sub_guids.py"
    if not task_b_file.exists():
        results["message"] = "publisher_gets_sub_guids.py not found"
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "task_b_exists", "passed": True})

    # Check Task B syntax
    passed, error = check_syntax(task_b_file)
    if not passed:
        results["message"] = f"Syntax error in publisher_gets_sub_guids.py: {error}"
        checkpoints.append({"name": "task_b_syntax", "passed": False, "details": {"error": error}})
        results["details"]["checkpoints"] = checkpoints
        return results
    checkpoints.append({"name": "task_b_syntax", "passed": True})

    # Preflight Task B
    passed, error = preflight_check(task_b_file, [], cwd=workspace)
    if not passed:
        results["message"] = f"publisher_gets_sub_guids.py crashed during preflight: {error}"
        checkpoints.append({"name": "task_b_preflight", "passed": False, "details": {"stderr": error}})
        results["details"]["checkpoints"] = checkpoints
        return results
    checkpoints.append({"name": "task_b_preflight", "passed": True})

    # Check Task B contains required API elements
    with open(task_b_file) as f:
        task_b_code = f.read()

    required_b = ["matched_subscriptions", "matched_subscription_data"]
    missing_b = [req for req in required_b if req not in task_b_code]
    checkpoints.append({
        "name": "task_b_apis",
        "passed": len(missing_b) == 0,
        "details": {"missing": missing_b if missing_b else None}
    })

    # Functional Test: Task A - subscriber gets publisher GUID
    guid_found = False
    try:
        # Start subscriber
        sub_proc = subprocess.Popen(
            [sys.executable, str(task_a_file), "--count", "5", "--timeout", "20"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=workspace,
        )

        time.sleep(2)

        # Create inline publisher with matching QoS
        pub_code = '''
import time
import rti.connextdds as dds

t = dds.StructType("HelloWorld")
t.add_member(dds.Member("message", dds.StringType(256)))
t.add_member(dds.Member("count", dds.Int32Type()))

p = dds.DomainParticipant(0)
topic = dds.DynamicData.Topic(p, "HelloWorld", t)

qos = dds.DataWriterQos()
qos.reliability.kind = dds.ReliabilityKind.RELIABLE
qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL

w = dds.DynamicData.DataWriter(dds.Publisher(p), topic, qos)
time.sleep(2)

for i in range(5):
    s = dds.DynamicData(t)
    s["message"] = f"Hello {i}"
    s["count"] = i
    w.write(s)
    time.sleep(0.3)

time.sleep(1)
'''

        pub_proc = subprocess.Popen(
            [sys.executable, "-c", pub_code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=workspace,
        )

        try:
            sub_stdout, sub_stderr = sub_proc.communicate(timeout=30)
            pub_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            sub_proc.kill()
            pub_proc.kill()
            sub_stdout, _ = sub_proc.communicate()

        # Check output contains publisher_guid
        lines = [l for l in sub_stdout.strip().split("\n") if l.startswith("{")]
        for line in lines:
            try:
                data = json.loads(line)
                if "publisher_guid" in data and data["publisher_guid"]:
                    guid_found = True
                    break
            except json.JSONDecodeError:
                pass

        checkpoints.append({
            "name": "task_a_functional",
            "passed": guid_found,
            "details": {"guid_found": guid_found, "output_lines": len(lines)}
        })

    except Exception as e:
        checkpoints.append({
            "name": "task_a_functional",
            "passed": False,
            "details": {"error": str(e)}
        })

    # Pass/fail based on all critical checkpoints
    all_critical_passed = all(
        cp.get("passed") for cp in checkpoints
        if cp.get("name") in ["task_a_exists", "task_a_syntax", "task_a_preflight", "task_a_apis",
                               "task_b_exists", "task_b_syntax", "task_b_preflight", "task_b_apis",
                               "task_a_functional"]
    )

    results["success"] = all_critical_passed
    results["score"] = 1.0 if results["success"] else 0.0

    if guid_found:
        results["message"] = "GUID extraction working correctly"
    else:
        results["message"] = "GUID extraction not working - no publisher_guid in output"

    results["details"]["checkpoints"] = checkpoints
    return results


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
