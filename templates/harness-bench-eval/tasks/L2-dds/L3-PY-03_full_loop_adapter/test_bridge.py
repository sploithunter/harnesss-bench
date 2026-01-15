#!/usr/bin/env python3
"""Test script for Full Loop Binary Protocol Adapter."""

import ast
import os
import subprocess
import sys
import time
from pathlib import Path

TIMEOUT = 60


def check_syntax(filename):
    if not Path(filename).exists():
        print(f"✗ {filename} not found")
        return False
    try:
        with open(filename) as f:
            ast.parse(f.read())
        return True
    except SyntaxError as e:
        print(f"✗ Syntax error in {filename}: {e}")
        return False


def check_files_exist():
    """Check required files exist."""
    required = ["inbound_adapter.py", "outbound_adapter.py", "protocol.py"]
    missing = [f for f in required if not Path(f).exists()]
    
    if missing:
        print(f"✗ Missing files: {missing}")
        return False
    
    print("✓ All required files exist")
    return True


def check_waitset_usage():
    """Check outbound adapter uses WaitSet."""
    with open("outbound_adapter.py") as f:
        code = f.read()
    
    if "WaitSet" in code and "wait(" in code:
        print("✓ outbound_adapter.py uses WaitSet (async)")
        return True
    else:
        print("✗ outbound_adapter.py should use WaitSet, not polling")
        return False


def check_qos_settings():
    """Check both adapters use proper QoS."""
    ok = True
    for fname in ["inbound_adapter.py", "outbound_adapter.py"]:
        with open(fname) as f:
            code = f.read()
        
        if "TRANSIENT_LOCAL" not in code:
            print(f"✗ {fname} missing TRANSIENT_LOCAL durability")
            ok = False
        if "RELIABLE" not in code:
            print(f"✗ {fname} missing RELIABLE reliability")
            ok = False
    
    if ok:
        print("✓ Both adapters use proper QoS (RELIABLE + TRANSIENT_LOCAL)")
    return ok


def run_full_loop_test():
    """Run the full binary → DDS → binary loop."""
    # Import protocol to generate test data
    sys.path.insert(0, str(Path.cwd()))
    try:
        from protocol import encode_message, decode_message, generate_test_messages
    except ImportError as e:
        print(f"✗ Cannot import protocol: {e}")
        return False
    
    # Generate test input
    test_messages = generate_test_messages(10)
    input_file = Path("test_input.bin")
    output_file = Path("test_output.bin")
    
    with open(input_file, "wb") as f:
        for msg in test_messages:
            f.write(encode_message(msg))
    
    print(f"  Generated {len(test_messages)} test messages")
    
    # Start outbound adapter (subscriber) first
    outbound = subprocess.Popen(
        [sys.executable, "outbound_adapter.py", 
         "--output", str(output_file), "--count", "10", "--timeout", "30"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    
    time.sleep(3)  # Let subscriber start
    
    # Start inbound adapter (publisher)
    inbound = subprocess.Popen(
        [sys.executable, "inbound_adapter.py", "--input", str(input_file)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    
    try:
        inbound.wait(timeout=30)
        outbound.wait(timeout=30)
    except subprocess.TimeoutExpired:
        inbound.kill()
        outbound.kill()
        print("✗ Timeout")
        return False
    
    # Compare files
    if not output_file.exists():
        print("✗ Output file not created")
        return False
    
    with open(input_file, "rb") as f:
        input_data = f.read()
    with open(output_file, "rb") as f:
        output_data = f.read()
    
    # Parse and compare messages
    input_msgs = []
    data = input_data
    while data:
        msg, data = decode_message(data)
        input_msgs.append(msg)
    
    output_msgs = []
    data = output_data
    while data:
        msg, data = decode_message(data)
        output_msgs.append(msg)
    
    if len(output_msgs) >= len(input_msgs):
        print(f"✓ Full loop test passed: {len(output_msgs)}/{len(input_msgs)} messages")
        return True
    else:
        print(f"✗ Only received {len(output_msgs)}/{len(input_msgs)} messages")
        return False


def main():
    print("=" * 50)
    print("Full Loop Binary Protocol Adapter Test")
    print("=" * 50)
    
    tests = [
        ("Files Exist", check_files_exist),
        ("Inbound Syntax", lambda: check_syntax("inbound_adapter.py")),
        ("Outbound Syntax", lambda: check_syntax("outbound_adapter.py")),
        ("WaitSet Usage", check_waitset_usage),
        ("QoS Settings", check_qos_settings),
        ("Full Loop Test", run_full_loop_test),
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

