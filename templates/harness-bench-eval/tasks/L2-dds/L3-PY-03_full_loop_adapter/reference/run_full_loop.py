#!/usr/bin/env python3
"""Full Loop Test: Binary → DDS → Binary.

This script demonstrates the complete pipeline:
1. Generate test binary messages
2. Inbound adapter: Binary → DDS
3. Outbound adapter: DDS → Binary
4. Compare input vs output

Usage:
    python run_full_loop.py [--count N] [--domain D] [--verbose]
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Add reference dir to path
REFERENCE_DIR = Path(__file__).parent
sys.path.insert(0, str(REFERENCE_DIR))

from protocol import generate_test_messages, encode_message, decode_message


def main():
    parser = argparse.ArgumentParser(description="Full Loop DDS Test")
    parser.add_argument("--count", "-c", type=int, default=10, help="Number of messages")
    parser.add_argument("--domain", "-d", type=int, default=0, help="DDS domain ID")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--timeout", "-t", type=float, default=30.0, help="Timeout")
    args = parser.parse_args()
    
    print("=" * 60)
    print("FULL LOOP TEST: Binary → DDS → Binary")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        input_file = Path(tmpdir) / "input.bin"
        output_file = Path(tmpdir) / "output.bin"
        
        # Step 1: Generate test messages
        print("\n[1] Generating test messages...")
        messages = generate_test_messages(args.count)
        
        with open(input_file, "wb") as f:
            for msg in messages:
                f.write(encode_message(msg))
        
        print(f"    Generated {len(messages)} messages ({input_file.stat().st_size} bytes)")
        
        if args.verbose:
            for i, msg in enumerate(messages):
                print(f"    [{i+1}] {msg}")
        
        # Step 2: Start outbound adapter (subscriber) first
        print("\n[2] Starting outbound adapter (DDS → Binary)...")
        outbound_proc = subprocess.Popen(
            [
                sys.executable,
                str(REFERENCE_DIR / "outbound_adapter.py"),
                "--output", str(output_file),
                "--domain", str(args.domain),
                "--count", str(args.count),
                "--timeout", str(args.timeout),
            ] + (["--verbose"] if args.verbose else []),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        
        # Give subscriber time to discover and register
        time.sleep(2.0)
        
        # Step 3: Run inbound adapter (publisher)
        print("\n[3] Running inbound adapter (Binary → DDS)...")
        inbound_result = subprocess.run(
            [
                sys.executable,
                str(REFERENCE_DIR / "inbound_adapter.py"),
                "--input", str(input_file),
                "--domain", str(args.domain),
            ] + (["--verbose"] if args.verbose else []),
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if inbound_result.returncode != 0:
            print(f"    ERROR: Inbound adapter failed")
            print(inbound_result.stderr)
            return 1
        
        print(f"    {inbound_result.stderr.strip()}")
        
        # Step 4: Wait for outbound adapter
        print("\n[4] Waiting for outbound adapter...")
        try:
            stdout, stderr = outbound_proc.communicate(timeout=args.timeout)
            print(f"    {stderr.decode().strip()}")
        except subprocess.TimeoutExpired:
            outbound_proc.kill()
            print("    ERROR: Outbound adapter timed out")
            return 1
        
        # Step 5: Compare results
        print("\n[5] Comparing results...")
        
        if not output_file.exists():
            print("    ERROR: Output file not created")
            return 1
        
        with open(output_file, "rb") as f:
            output_data = f.read()
        
        # Decode output messages
        output_messages = []
        data = output_data
        while data:
            msg, data = decode_message(data)
            output_messages.append(msg)
        
        # Compare
        print(f"    Input:  {len(messages)} messages")
        print(f"    Output: {len(output_messages)} messages")
        
        if len(messages) != len(output_messages):
            print("    FAILED: Message count mismatch")
            return 1
        
        # Sort by seq/id for comparison (order may differ)
        def get_id(msg):
            if hasattr(msg, 'seq'):
                return msg.seq
            return msg.id
        
        input_sorted = sorted(messages, key=get_id)
        output_sorted = sorted(output_messages, key=get_id)
        
        mismatches = 0
        for i, (inp, out) in enumerate(zip(input_sorted, output_sorted)):
            # Compare type
            if type(inp) != type(out):
                print(f"    Mismatch [{i}]: type {type(inp).__name__} vs {type(out).__name__}")
                mismatches += 1
                continue
            
            # Compare values (excluding timestamp which may drift)
            inp_dict = inp.to_dict()
            out_dict = out.to_dict()
            
            # For heartbeats, skip timestamp comparison
            if inp_dict.get("type") == "heartbeat":
                del inp_dict["timestamp"]
                del out_dict["timestamp"]
            
            if inp_dict != out_dict:
                print(f"    Mismatch [{i}]: {inp_dict} vs {out_dict}")
                mismatches += 1
        
        if mismatches > 0:
            print(f"    FAILED: {mismatches} mismatches")
            return 1
        
        print("\n" + "=" * 60)
        print("✓ FULL LOOP TEST PASSED")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())

