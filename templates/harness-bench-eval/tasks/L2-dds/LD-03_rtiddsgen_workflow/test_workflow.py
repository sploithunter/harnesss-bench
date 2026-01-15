#!/usr/bin/env python3
"""Test script for rtiddsgen workflow."""

import os
import subprocess
import sys
import time
from pathlib import Path

TIMEOUT = 120


def check_idl_file():
    """Check HelloWorld.idl exists and is valid."""
    if not Path("HelloWorld.idl").exists():
        print("✗ HelloWorld.idl not found")
        return False
    
    with open("HelloWorld.idl") as f:
        content = f.read()
    
    if "struct HelloWorld" in content and "message" in content and "count" in content:
        print("✓ HelloWorld.idl looks valid")
        return True
    else:
        print("✗ HelloWorld.idl missing required fields")
        return False


def run_rtiddsgen():
    """Run rtiddsgen to generate Python code."""
    nddshome = os.environ.get("NDDSHOME")
    if not nddshome:
        print("✗ NDDSHOME not set")
        return False
    
    rtiddsgen = Path(nddshome) / "bin" / "rtiddsgen"
    if not rtiddsgen.exists():
        print(f"✗ rtiddsgen not found at {rtiddsgen}")
        return False
    
    result = subprocess.run(
        [str(rtiddsgen), "-language", "python", "-d", ".", "-replace", "HelloWorld.idl"],
        capture_output=True, text=True, timeout=60
    )
    
    if result.returncode == 0 and Path("HelloWorld.py").exists():
        print("✓ rtiddsgen generated HelloWorld.py")
        return True
    else:
        print(f"✗ rtiddsgen failed: {result.stderr}")
        return False


def check_generated_type():
    """Check the generated type is importable."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", "from HelloWorld import HelloWorld; print(HelloWorld)"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("✓ Generated type is importable")
            return True
        else:
            print(f"✗ Import failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def check_pub_sub_files():
    """Check publisher.py and subscriber.py exist."""
    pub_ok = Path("publisher.py").exists()
    sub_ok = Path("subscriber.py").exists()
    
    if pub_ok and sub_ok:
        print("✓ publisher.py and subscriber.py exist")
        return True
    else:
        if not pub_ok:
            print("✗ publisher.py not found")
        if not sub_ok:
            print("✗ subscriber.py not found")
        return False


def check_uses_generated_types():
    """Check that code uses generated types (not DynamicData)."""
    for fname in ["publisher.py", "subscriber.py"]:
        if not Path(fname).exists():
            continue
        with open(fname) as f:
            code = f.read()
        
        # Check for actual DynamicData API usage (not just comments)
        # DynamicData usage: dds.DynamicData.Topic, dds.DynamicData.DataWriter, etc.
        if "dds.DynamicData" in code or "DynamicData.Topic" in code or "DynamicData.DataWriter" in code:
            print(f"✗ {fname} uses DynamicData API instead of generated types")
            return False
        
        if "from HelloWorld import HelloWorld" not in code:
            print(f"✗ {fname} doesn't import generated type")
            return False
    
    print("✓ Code uses generated types (not DynamicData)")
    return True


def run_functional_test():
    """Run publisher and subscriber together."""
    # Start subscriber
    sub_proc = subprocess.Popen(
        [sys.executable, "subscriber.py", "--count", "10", "--timeout", "30"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    
    time.sleep(2)
    
    # Start publisher
    pub_proc = subprocess.Popen(
        [sys.executable, "publisher.py"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    
    try:
        sub_stdout, _ = sub_proc.communicate(timeout=TIMEOUT)
        pub_proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        sub_proc.kill()
        pub_proc.kill()
        print("✗ Timeout")
        return False
    
    lines = [l for l in sub_stdout.strip().split("\n") if l.startswith("{")]
    if len(lines) >= 10:
        print(f"✓ Received {len(lines)} samples")
        return True
    else:
        print(f"✗ Only received {len(lines)} samples")
        return False


def main():
    print("=" * 50)
    print("RTI DDS Gen Workflow Test")
    print("=" * 50)
    
    tests = [
        ("IDL File", check_idl_file),
        ("Run rtiddsgen", run_rtiddsgen),
        ("Generated Type", check_generated_type),
        ("Pub/Sub Files", check_pub_sub_files),
        ("Uses Generated Types", check_uses_generated_types),
        ("Functional Test", run_functional_test),
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

