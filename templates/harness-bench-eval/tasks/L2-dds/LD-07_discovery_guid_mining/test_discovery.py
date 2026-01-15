#!/usr/bin/env python3
"""Test script for Discovery GUID Mining task."""

import ast
import json
import subprocess
import sys
import time
from pathlib import Path

TIMEOUT = 60


def check_syntax(filename):
    """Check if file has valid syntax."""
    try:
        with open(filename) as f:
            ast.parse(f.read())
        return True
    except SyntaxError as e:
        print(f"✗ Syntax error in {filename}: {e}")
        return False


def check_task_a_file():
    """Check subscriber_gets_pub_guid.py exists and has required elements."""
    fname = "subscriber_gets_pub_guid.py"
    if not Path(fname).exists():
        print(f"✗ {fname} not found")
        return False
    
    if not check_syntax(fname):
        return False
    
    with open(fname) as f:
        code = f.read()
    
    required = ["publication_handle", "matched_publication_data"]
    for req in required:
        if req not in code:
            print(f"✗ {fname} missing: {req}")
            return False
    
    print(f"✓ {fname} looks correct")
    return True


def check_task_b_file():
    """Check publisher_gets_sub_guids.py exists and has required elements."""
    fname = "publisher_gets_sub_guids.py"
    if not Path(fname).exists():
        print(f"✗ {fname} not found")
        return False
    
    if not check_syntax(fname):
        return False
    
    with open(fname) as f:
        code = f.read()
    
    required = ["matched_subscriptions", "matched_subscription_data"]
    for req in required:
        if req not in code:
            print(f"✗ {fname} missing: {req}")
            return False
    
    print(f"✓ {fname} looks correct")
    return True


def run_task_a_test():
    """Run Task A: subscriber gets publisher GUID."""
    ref_publisher = Path("reference/publisher.py")
    if not ref_publisher.exists():
        # Create a simple publisher for testing
        ref_publisher = Path(__file__).parent / "reference" / "subscriber_gets_pub_guid.py"
    
    # Start subscriber
    sub_proc = subprocess.Popen(
        [sys.executable, "subscriber_gets_pub_guid.py", "--count", "5", "--timeout", "20"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    
    time.sleep(2)
    
    # Create and run a simple publisher with matching QoS
    pub_code = '''
import time, rti.connextdds as dds
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
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    
    try:
        sub_stdout, sub_stderr = sub_proc.communicate(timeout=TIMEOUT)
        pub_proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        sub_proc.kill()
        pub_proc.kill()
        print("✗ Timeout")
        return False
    
    # Check output contains GUIDs
    lines = [l for l in sub_stdout.strip().split("\n") if l.startswith("{")]
    guid_found = False
    for line in lines:
        try:
            data = json.loads(line)
            if "publisher_guid" in data and data["publisher_guid"]:
                guid_found = True
                break
        except:
            pass
    
    if guid_found:
        print(f"✓ Task A: Subscriber correctly extracts publisher GUID")
        return True
    else:
        print(f"✗ Task A: No publisher_guid found in output")
        print(f"  Output: {sub_stdout[:500]}")
        return False


def main():
    print("=" * 50)
    print("Discovery GUID Mining Test")
    print("=" * 50)
    
    tests = [
        ("Task A File", check_task_a_file),
        ("Task B File", check_task_b_file),
        ("Task A Functional", run_task_a_test),
    ]
    
    passed = 0
    for name, test in tests:
        print(f"\n--- {name} ---")
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ Error: {e}")
    
    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("ALL TESTS PASSED")
    
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())

